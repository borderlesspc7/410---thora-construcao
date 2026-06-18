from fastapi import FastAPI, UploadFile, File, HTTPException, Depends, Request, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from datetime import datetime
import asyncio
import uuid
import os
import logging
from pathlib import Path
from typing import List, Dict, Tuple, Any
import json
import re
import base64
import fitz

import httpx
from pydantic import BaseModel, Field, model_validator

from config import (
    FRONTEND_URLS,
    CORS_ORIGIN_REGEX,
    IS_VERCEL,
    API_TITLE,
    API_VERSION,
    API_DESCRIPTION,
    UPLOAD_FOLDER,
    MAX_FILE_SIZE,
    TEMP_FOLDER,
    BASE_DIR,
    CACHE_FOLDER,
    DETECT_TABLES_MAX_CANDIDATES,
    DETECT_TABLES_CACHE_VERSION,
    DETECT_TABLES_MAX_PAGES,
    DETECT_TABLES_THUMB_SCALE,
    ENVIRONMENT,
    GEMINI_API_KEY,
    GEMINI_MODEL,
    OPENROUTER_API_KEY,
    OPENROUTER_MODEL,
    GROQ_API_KEY,
    GROQ_MODEL,
    OPENAI_API_KEY,
    OPENAI_MODEL,
    OPENAI_ORCAMENTO_MODEL,
    OLLAMA_ENABLED,
    OLLAMA_BASE_URL,
    OLLAMA_MODEL,
    OLLAMA_TIMEOUT_SECONDS,
    AI_PROVIDER_TIMEOUT_SECONDS,
    ENABLE_MULTI_PROVIDER_CHAIN,
)
from firebase_service import OrcamentoFirestore, OrcamentoEnterpriseFirestore
from budget_parser import BudgetParser
from firebase_admin import auth as firebase_auth
from services.openai_service import (
    identify_tables,
    process_selected_table,
    generate_report_chat,
    OpenAIServiceError,
    _coerce_bdi,
    _coerce_number,
)
from services.analitico_job import (
    clear_job,
    get_job,
    init_job,
)
from services.analitico_queue import (
    AnaliticoQueueJob,
    enqueue_analitico_job,
    get_queue_position,
    is_celery_queue_enabled,
    start_queue_worker,
)
from services.analitico_runner import process_queued_analitico_job
from services.abc_job import (
    get_job as get_abc_job,
    get_user_jobs,
    init_job as init_abc_job,
    update_job as update_abc_job,
)
from services.abc_queue import AbcQueueJob, enqueue_abc_job, start_abc_queue_worker
from services.abc_runner import process_abc_queue_job
from services.storage_service import (
    download_pdf_bytes_async,
    is_storage_available,
    upload_pdf_bytes_async,
)
from services.cloud_upload import wait_for_cloud_upload
from services.upload_meta import load_upload_meta as _load_upload_meta_service
from services.upload_meta import save_upload_meta as _save_upload_meta_service
from services.report_pdf import build_analysis_pdf_bytes
from services.ai_audit_logger import log_ai_exchange
from services.xlsx_export import save_export_workbook
from services.analitico_normalize import normalize_hierarchical_analitico
from services.hybrid_extraction import merge_parser_as_primary

try:
    import pdfplumber
except ImportError:
    pdfplumber = None

try:
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
except ImportError:
    Workbook = None

# Configuração de logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

_camelot_module = None


def _get_camelot():
    """Import tardio — Camelot/OpenCV deixam o boot lento e pesado no Render free tier."""
    global _camelot_module
    if _camelot_module is None:
        import camelot as camelot_module

        _camelot_module = camelot_module
    return _camelot_module


_GEMINI_CANDIDATE_MODELS = [
    GEMINI_MODEL,
    "gemini-2.0-flash",
    "gemini-2.0-flash-lite",
    "gemini-1.5-flash-latest",
    "gemini-1.5-pro-latest",
    "gemini-pro",
]


class AIProviderError(Exception):
    def __init__(self, provider: str, details: str):
        super().__init__(details)
        self.provider = provider
        self.details = details


def _clean_json_text(raw_text: str) -> str:
    text = raw_text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?", "", text, count=1).strip()
        text = re.sub(r"```$", "", text).strip()
    return text


def _normalize_unit(unit: str) -> str:
    if not unit:
        return "un"

    value = unit.strip().lower().replace("²", "2").replace("³", "3")
    aliases = {
        "und": "un",
        "unid": "un",
        "unidade": "un",
        "m²": "m2",
        "m2": "m2",
        "m³": "m3",
        "m3": "m3",
        "mt": "m",
        "metro": "m",
        "metros": "m",
        "litro": "l",
        "litros": "l",
        "ton": "t",
        "tonelada": "t",
        "toneladas": "t",
    }
    return aliases.get(value, value)


def _local_standardize_items(items: List[Dict]) -> List[Dict]:
    standardized = []
    for item in items:
        descricao = str(item.get("descricao", "")).strip()
        standardized.append(
            {
                "descricao": " ".join(descricao.split()).upper(),
                "quantidade": item.get("quantidade", 0),
                "unidade": _normalize_unit(str(item.get("unidade", ""))),
                "valor_unitario": item.get("valor_unitario", 0),
                "valor_total": item.get("valor_total", 0),
            }
        )
    return standardized


def _local_budget_analysis(upload_data: Dict) -> Dict:
    source_items = upload_data.get("items") or []
    items = _local_standardize_items(source_items)

    analyzed_items = []
    for index, item in enumerate(items, start=1):
        quantidade = float(item.get("quantidade", 0) or 0)
        valor_unitario = float(item.get("valor_unitario", 0) or 0)
        valor_total = float(item.get("valor_total", 0) or quantidade * valor_unitario)

        analyzed_items.append(
            {
                "id": f"item_{index}",
                "descricao": item.get("descricao", ""),
                "quantidade": quantidade,
                "unidade": item.get("unidade", "un"),
                "valor_unitario": valor_unitario,
                "valor_total": valor_total,
                "validado": True,
                "notas": "Padronização local aplicada",
            }
        )

    valor_total_geral = sum(float(item.get("valor_total", 0) or 0) for item in analyzed_items)

    return {
        "structure": {
            "coluna_descricao": 0,
            "coluna_quantidade": 1,
            "coluna_unidade": 2,
            "coluna_valor_unitario": 3,
            "confianca": 0.6,
        },
        "items": analyzed_items,
        "resumo": {
            "total_items": len(analyzed_items),
            "valor_total": valor_total_geral,
            "confianca_analise": 0.6,
            "avisos": [
                "Análise local utilizada por indisponibilidade de IA remota",
            ],
        },
    }


async def _call_gemini_generate_content(request_body: dict, timeout_seconds: float = 45.0) -> Tuple[str, str]:
    attempted_models = []
    last_error_body = ""

    models_to_try = []
    for model in _GEMINI_CANDIDATE_MODELS:
        if model and model not in models_to_try:
            models_to_try.append(model)

    async with httpx.AsyncClient(timeout=timeout_seconds) as client:
        for model in models_to_try:
            attempted_models.append(model)
            url = (
                f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
                f"?key={GEMINI_API_KEY}"
            )
            try:
                response = await client.post(url, json=request_body)
            except httpx.HTTPError as exc:
                raise AIProviderError("gemini", f"Falha de conexão: {exc}") from exc

            if response.status_code < 400:
                logger.info(f"✅ Gemini respondeu com modelo: {model}")
                response_data = response.json()
                content = response_data["candidates"][0]["content"]["parts"][0]["text"].strip()
                return content, f"gemini:{model}"

            last_error_body = response.text
            logger.warning(
                f"⚠️ Gemini falhou com modelo {model} (status {response.status_code})."
            )

            if response.status_code == 404:
                continue

            if response.status_code in (404, 429, 500, 502, 503, 504):
                continue

            raise AIProviderError("gemini", f"Erro não recuperável (status {response.status_code}): {response.text}")

    raise AIProviderError(
        "gemini",
        (
            "Nenhum modelo Gemini compatível respondeu ao generateContent. "
            f"Modelos tentados: {', '.join(attempted_models)}. "
            f"Último erro: {last_error_body}"
        ),
    )


async def _call_openai_compatible_generate_content(
    provider: str,
    base_url: str,
    api_key: str,
    model: str,
    system_message: str,
    user_message: Dict,
    timeout_seconds: float = 45.0,
) -> Tuple[str, str]:
    if not api_key:
        raise AIProviderError(provider, "API key ausente")

    url = f"{base_url.rstrip('/')}/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    body = {
        "model": model,
        "temperature": 0.1,
        "messages": [
            {"role": "system", "content": system_message},
            {"role": "user", "content": json.dumps(user_message, ensure_ascii=False)},
        ],
    }

    try:
        async with httpx.AsyncClient(timeout=timeout_seconds) as client:
            response = await client.post(url, headers=headers, json=body)
    except httpx.HTTPError as exc:
        raise AIProviderError(provider, f"Falha de conexão: {exc}") from exc

    if response.status_code >= 400:
        if response.status_code in (401, 403):
            raise AIProviderError(provider, f"Chave inválida ou sem permissão ({response.status_code})")
        raise AIProviderError(provider, f"Erro HTTP {response.status_code}: {response.text}")

    data = response.json()
    choices = data.get("choices") or []
    if not choices:
        raise AIProviderError(provider, "Resposta sem choices")

    message = choices[0].get("message") or {}
    content = (message.get("content") or "").strip()
    if not content:
        raise AIProviderError(provider, "Resposta sem content")

    return content, f"{provider}:{model}"


async def _call_ollama_generate_content(
    system_message: str,
    user_message: Dict,
    timeout_seconds: float = 45.0,
) -> Tuple[str, str]:
    if not OLLAMA_ENABLED:
        raise AIProviderError("ollama", "Ollama desativado por configuração")

    url = f"{OLLAMA_BASE_URL.rstrip('/')}/api/chat"
    body = {
        "model": OLLAMA_MODEL,
        "stream": False,
        "format": "json",
        "options": {"temperature": 0.1},
        "messages": [
            {"role": "system", "content": system_message},
            {"role": "user", "content": json.dumps(user_message, ensure_ascii=False)},
        ],
    }

    try:
        async with httpx.AsyncClient(timeout=timeout_seconds) as client:
            response = await client.post(url, json=body)
    except httpx.HTTPError as exc:
        raise AIProviderError("ollama", f"Falha de conexão: {exc}") from exc

    if response.status_code >= 400:
        raise AIProviderError("ollama", f"Erro HTTP {response.status_code}: {response.text}")

    data = response.json()
    message = data.get("message") or {}
    content = (message.get("content") or "").strip()
    if not content:
        raise AIProviderError("ollama", "Resposta sem content")

    return content, f"ollama:{OLLAMA_MODEL}"

# Cache em memória para modo offline (dados temporários)
_OFFLINE_CACHE = {}

# ============== HELPERS & DEPENDENCIES ==============

def _decode_firebase_uid_from_jwt(token: str) -> str | None:
    """Extrai UID do payload JWT (fallback quando Admin SDK não está disponível)."""
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return None
        payload_b64 = parts[1]
        padding = (-len(payload_b64)) % 4
        payload = json.loads(
            base64.urlsafe_b64decode(payload_b64 + ("=" * padding))
        )
        uid = payload.get("user_id") or payload.get("sub")
        return str(uid) if uid else None
    except Exception:
        return None


def _resolve_uid_from_bearer_token(token: str) -> str | None:
    token = token.strip()
    if not token:
        return None
    try:
        decoded = firebase_auth.verify_id_token(token)
        uid = decoded.get("uid")
        return str(uid) if uid else None
    except Exception:
        if ENVIRONMENT == "development":
            return _decode_firebase_uid_from_jwt(token)
        return None


def _assert_upload_access(user_id: str, expected_user: str | None) -> None:
    """Garante que o usuário autenticado pode acessar o upload."""
    if not expected_user:
        if ENVIRONMENT != "development":
            raise HTTPException(status_code=403, detail="Acesso negado")
        return
    if str(expected_user) == str(user_id):
        return
    if ENVIRONMENT == "development":
        logger.warning(
            "⚠️  Dev: ignorando mismatch de userId (legado=%s, atual=%s)",
            expected_user,
            user_id,
        )
        return
    raise HTTPException(status_code=403, detail="Acesso negado")


async def get_current_user_id(request: Request) -> str:
    """Extrai UID do Firebase a partir do Bearer token ou headers de fallback."""
    anonymous_user_id = request.headers.get("X-Anonymous-User", "").strip()
    auth_header = request.headers.get("Authorization", "").strip()
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]
        uid = _resolve_uid_from_bearer_token(token)
        if uid:
            return uid
        logger.warning("⚠️ Bearer token presente, mas UID não pôde ser resolvido")

    if anonymous_user_id:
        return anonymous_user_id

    if ENVIRONMENT == "development":
        return "dev-user-" + str(uuid.uuid4())[:8]

    raise HTTPException(status_code=401, detail="Não autenticado")


def _resolve_user_name_from_request(request: Request, fallback: str | None = None) -> str:
    """Extrai nome do usuário a partir do token Firebase ou fallback."""
    auth_header = request.headers.get("Authorization", "").strip()
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]
        try:
            decoded = firebase_auth.verify_id_token(token)
            return (
                decoded.get("name")
                or decoded.get("email")
                or decoded.get("uid")
                or fallback
                or "Usuário"
            )
        except Exception:
            if ENVIRONMENT == "development":
                payload = _decode_firebase_uid_from_jwt(token)
                if payload:
                    return payload
    return fallback or "Usuário"


def _assert_project_access(project_id: str, user_id: str) -> None:
    """Valida upload_id e permissão de acesso ao projeto."""
    project_id = _validate_upload_id(project_id)
    meta = _load_upload_meta(project_id)
    _assert_upload_access(user_id, meta.get("userId"))


def _meta_path_for_upload_id(upload_id: str) -> Path:
    """Retorna caminho de arquivo de metadados para um upload_id"""
    return UPLOAD_FOLDER / f".meta_{upload_id}.json"


def _save_upload_meta(upload_id: str, meta_dict: Dict) -> None:
    """Salva metadados do upload em arquivo JSON."""
    _save_upload_meta_service(upload_id, meta_dict)


def _load_upload_meta(upload_id: str) -> Dict:
    """Carrega metadados do upload de arquivo JSON."""
    return _load_upload_meta_service(upload_id)


def _validate_upload_id(upload_id: str) -> str:
    """Valida formato de upload_id (UUID)"""
    try:
        uuid.UUID(upload_id)
        return upload_id
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"❌ Upload ID inválido: {upload_id}"
        )


def _cache_path_for_upload_id(upload_id: str) -> Path:
    """Retorna caminho de arquivo de cache para um upload_id"""
    return CACHE_FOLDER / f"{upload_id}.json"


def _save_extracted_cache(upload_id: str, data: Dict) -> None:
    """Persiste dados extraídos em arquivo JSON para acesso offline"""
    try:
        cache_path = _cache_path_for_upload_id(upload_id)
        with open(cache_path, "w") as f:
            json.dump(data, f, indent=2, default=str)
        logger.debug(f"✅ Cache persistido: {cache_path}")
    except Exception as e:
        logger.warning(f"⚠️  Erro ao persistir cache: {e}")


def _load_extracted_cache(upload_id: str) -> Dict | None:
    """Carrega dados extraídos de arquivo JSON"""
    try:
        cache_path = _cache_path_for_upload_id(upload_id)
        if cache_path.exists():
            with open(cache_path) as f:
                return json.load(f)
    except Exception as e:
        logger.warning(f"⚠️  Erro ao carregar cache: {e}")
    return None


def _get_upload_data_from_sources(upload_id: str) -> Dict | None:
    """
    Busca dados extraídos de múltiplas fontes em ordem de prioridade:
    1. Cache em memória
    2. Arquivo de cache em disco
    3. Firestore
    4. Fallback None
    """
    # 1. Cache em memória
    if upload_id in _OFFLINE_CACHE:
        return _OFFLINE_CACHE[upload_id]
    
    # 2. Arquivo de cache em disco
    cached_data = _load_extracted_cache(upload_id)
    if cached_data:
        _OFFLINE_CACHE[upload_id] = cached_data
        return cached_data
    
    # 3. Firestore
    try:
        firestore_data = OrcamentoFirestore.get_orcamento_by_upload_id(upload_id)
        if firestore_data:
            raw_items = firestore_data.get("items")
            if not raw_items and firestore_data.get("itemsData"):
                idata = firestore_data.get("itemsData") or {}
                if isinstance(idata, dict):
                    raw_items = idata.get("items", [])
            if raw_items is None:
                raw_items = []

            tables_fs = firestore_data.get("tables") or []
            items_data_resumo = {}
            if isinstance(firestore_data.get("itemsData"), dict):
                items_data_resumo = (firestore_data.get("itemsData") or {}).get("resumo") or {}

            ai_raw = firestore_data.get("aiAnalysis") or firestore_data.get("ai_analysis")
            ai_analysis = ai_raw if isinstance(ai_raw, dict) else None

            # Normalizar formato do Firestore para o formato esperado
            normalized = {
                "uploadId": firestore_data.get("uploadId", upload_id),
                "userId": firestore_data.get("userId"),
                "filename": firestore_data.get("filename"),
                "items": raw_items,
                "tables": tables_fs,
                "resumo": firestore_data.get("resumo") or items_data_resumo,
                "uploadedAt": firestore_data.get("uploadedAt"),
                "extractedAt": firestore_data.get("extractedAt"),
                "tablesFound": len(tables_fs),
                "itemsFound": len(raw_items)
                if raw_items
                else int(firestore_data.get("itemsFound") or 0),
                "status": firestore_data.get("status", "completed"),
            }
            if ai_analysis:
                normalized["ai_analysis"] = ai_analysis
            _OFFLINE_CACHE[upload_id] = normalized
            return normalized
    except Exception as e:
        logger.warning(f"⚠️  Erro ao buscar do Firestore: {e}")
    
    # 4. Fallback
    return None


def _build_tables_text_for_ai(upload_data: Dict) -> str:
    """Monta texto para o prompt: tabelas extraídas ou, na falta delas, lista de itens."""
    tables = upload_data.get("tables") or []
    parts: List[str] = []

    for table in tables:
        rows = table.get("rows", [])
        table_text = "Página {}, Tabela: {} linhas x {} colunas\n".format(
            table.get("page", "?"),
            len(rows),
            table.get("columns", "?"),
        )
        for row in rows[:20]:
            table_text += " | ".join(str(cell)[:40] for cell in row) + "\n"
        parts.append(table_text + "\n---\n")

    items = upload_data.get("items") or []
    if not parts and items:
        block = "=== Itens disponíveis (sem tabelas brutas no cache) ===\n"
        for idx, item in enumerate(items[:250], start=1):
            if not isinstance(item, dict):
                continue
            desc = str(
                item.get("descricao")
                or item.get("description")
                or item.get("Description")
                or "",
            )[:120]
            q = item.get("quantidade", item.get("quantity", item.get("qty")))
            u = str(item.get("unidade") or item.get("unit") or "")
            vu = item.get("valor_unitario", item.get("unitValue"))
            vt = item.get("valor_total", item.get("totalValue"))
            block += f"{idx}. {desc} | qtd={q} | un={u} | vu={vu} | vt={vt}\n"
        parts.append(block)

    return "".join(parts)


def _persist_ai_analysis_to_firestore(upload_id: str, ai_payload: Dict) -> None:
    """Grava resultado da análise de IA no documento do orçamento (se Firestore ativo)."""
    try:
        fs_doc = OrcamentoFirestore.get_orcamento_by_upload_id(upload_id)
        if not fs_doc or not fs_doc.get("id"):
            return
        OrcamentoFirestore.update_orcamento(
            fs_doc["id"],
            {"aiAnalysis": ai_payload},
        )
    except Exception as exc:
        logger.warning("Não foi possível persistir aiAnalysis no Firestore: %s", exc)


def _preview_text_for_table_rows(rows: List[List[Any]], max_chars: int = 280) -> str:
    snippets: List[str] = []
    for row in rows[:4]:
        line = " | ".join(str(c)[:60] if c is not None else "" for c in row)
        if line.strip():
            snippets.append(line.strip())
    text = " · ".join(snippets)
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 1] + "…"


def _normalize_extracted_table_rows(table: List[List[Any]]) -> List[List[Any]]:
    processed_rows: List[List[Any]] = []
    for row in table:
        processed_row: List[Any] = []
        for cell in row:
            if cell is None:
                processed_row.append("")
            elif isinstance(cell, str):
                processed_row.append(cell.strip().replace("\n", " "))
            else:
                processed_row.append(str(cell))
        processed_rows.append(processed_row)
    return processed_rows


def _table_header_fingerprint(rows: List[List[Any]]) -> str:
    parts: List[str] = []
    for row in rows[:4]:
        parts.append(" ".join(str(c).lower().strip() for c in row if str(c).strip()))
    return "|".join(parts)[:240]


def _best_table_signal(tables: List[List[List[Any]]]) -> Tuple[int, int]:
    if not tables:
        return 0, 0
    best_nonempty = 0
    best_score = 0
    for table in tables:
        if not table:
            continue
        rows = _normalize_extracted_table_rows(table)
        best_nonempty = max(best_nonempty, _count_nonempty_table_rows(rows))
        best_score = max(best_score, _score_budget_table_likelihood(rows))
    return best_nonempty, best_score


def _extract_page_tables_multi_strategy(page: Any) -> List[List[List[Any]]]:
    """
    Combina estratégias do pdfplumber na mesma página.
    A estratégia por texto só rodava quando o padrão não encontrava nada; isso
    perdia tabelas de orçamento quando o PDF tinha ruído tabular (ex.: página 47).
    """
    collected: List[List[List[Any]]] = []
    seen_fingerprints: set[str] = set()

    def add_tables(raw_tables: List[List[List[Any]]] | None) -> None:
        if not raw_tables:
            return
        for table in raw_tables:
            if not table:
                continue
            rows = _normalize_extracted_table_rows(table)
            if _count_nonempty_table_rows(rows) < 2:
                continue
            fingerprint = _table_header_fingerprint(rows)
            if fingerprint in seen_fingerprints:
                continue
            seen_fingerprints.add(fingerprint)
            collected.append(rows)

    default_tables = page.extract_tables() or []
    add_tables(default_tables)

    best_nonempty, best_score = _best_table_signal(default_tables)
    needs_fallback = best_nonempty < 12 or best_score < 25

    if needs_fallback:
        for settings in (_PDFPLUMBER_LINES_TABLE_SETTINGS, _PDFPLUMBER_TEXT_TABLE_SETTINGS):
            try:
                add_tables(page.extract_tables(settings) or [])
            except Exception as exc:
                logger.debug("  Extração alternativa falhou: %s", exc)

    if not collected:
        text = page.extract_text()
        if text:
            lines = [line.strip() for line in text.split("\n") if line.strip()]
            if lines:
                collected.append([[line] for line in lines])

    return collected


def _extract_tables_from_pdf_path(
    file_path: Path,
    max_pages: int | None = None,
) -> List[Dict]:
    """Extrai tabelas de um PDF no disco (mesma lógica usada em /api/extract)."""
    if not pdfplumber:
        raise RuntimeError("pdfplumber não está instalado")

    tables: List[Dict] = []
    with pdfplumber.open(file_path) as pdf:
        total_pages = len(pdf.pages)
        scan_limit = min(total_pages, max_pages) if max_pages else total_pages
        logger.info(
            "📄 Processando PDF: %s página(s)%s",
            total_pages,
            f" (limite {scan_limit})" if max_pages and scan_limit < total_pages else "",
        )

        for page_num, page in enumerate(pdf.pages):
            if max_pages is not None and page_num >= max_pages:
                break
            logger.debug("  Página %s: %sx%s", page_num + 1, page.width, page.height)

            page_tables = _extract_page_tables_multi_strategy(page)

            if page_tables:
                for table_idx, processed_rows in enumerate(page_tables):
                    tables.append(
                        {
                            "page": page_num + 1,
                            "table_id": f"page_{page_num}_table_{table_idx}",
                            "rows": processed_rows,
                            "original_rows": len(processed_rows),
                            "columns": len(processed_rows[0]) if processed_rows else 0,
                        }
                    )
                    logger.info(
                        "  ✓ Tabela %s: %s linhas x %s colunas",
                        table_idx + 1,
                        len(processed_rows),
                        len(processed_rows[0]) if processed_rows else 0,
                    )
            else:
                logger.warning("  ⚠️  Nenhuma tabela encontrada na página %s", page_num + 1)

    return tables


def _candidate_camelot_index(candidate_id: str) -> int | None:
    """Índice Camelot alinhado ao id `table-{n}` gerado em detect-tables."""
    match = re.match(r"^table-(\d+)$", str(candidate_id or "").strip())
    if not match:
        return None
    return int(match.group(1))


def _camelot_table_to_rows(camelot_table: Any) -> List[List[Any]]:
    """Converte tabela Camelot em matriz de linhas para o prompt da IA."""
    df = camelot_table.df
    rows: List[List[Any]] = []
    for _, row in df.iterrows():
        rows.append(
            [str(cell).strip() if cell is not None and str(cell) != "nan" else "" for cell in row.tolist()]
        )
    return rows


def _count_nonempty_table_rows(rows: List[List[Any]]) -> int:
    return sum(1 for row in rows if any(str(cell).strip() for cell in row))


_BUDGET_HEADER_HINTS: Dict[str, List[str]] = {
    "descricao": [
        "descrição",
        "descricao",
        "serviço",
        "servico",
        "do serviço",
        "do servico",
        "especificação",
        "especificacao",
    ],
    "quantidade": ["qtde", "qtde.", "quant", "quantidade", "qtd", "qtd."],
    "valor": [
        "preço unit",
        "preco unit",
        "valor unit",
        "p. unit",
        "p.unit",
        "unitário",
        "unitario",
        "preço total",
        "preco total",
        "valor total",
    ],
    "codigo": ["código", "codigo", "code", "item", "fonte"],
    "bdi": ["bdi", "% bdi", "b.d.i"],
    "unidade": ["unid.", "unid", "und.", "und", "unidade"],
}
_PDFPLUMBER_TEXT_TABLE_SETTINGS = {
    "vertical_strategy": "text",
    "horizontal_strategy": "text",
    "snap_tolerance": 5,
    "join_tolerance": 5,
    "edge_min_length": 3,
}
_PDFPLUMBER_LINES_TABLE_SETTINGS = {
    "vertical_strategy": "lines",
    "horizontal_strategy": "lines",
    "snap_tolerance": 5,
    "join_tolerance": 5,
    "edge_min_length": 3,
}
_EDITAL_NOISE_KEYWORDS = (
    "licitação",
    "licitacao",
    "edital",
    "decreto",
    "art.",
    "parágrafo",
    "microempresa",
    "certame",
    "fornecedor",
    "proposta",
    "habilitação",
    "habilitacao",
    "pregão",
    "pregao",
)
_SERVICE_CODE_PATTERN = re.compile(
    r"\b(CPU\d+|[A-Z]{2,}\d{3,}|\d{5,}[A-Z]?)\b",
    re.IGNORECASE,
)


def _score_budget_table_likelihood(rows: List[List[Any]]) -> int:
    """Pontua se a matriz parece planilha de orçamento (não texto do edital)."""
    if not rows:
        return 0

    score = 0
    sample_parts: List[str] = []
    for row in rows[:15]:
        sample_parts.append(" ".join(str(c).lower() for c in row if c))
    sample_text = " ".join(sample_parts)

    edital_hits = sum(1 for kw in _EDITAL_NOISE_KEYWORDS if kw in sample_text)
    if edital_hits >= 4:
        score -= 40
    elif edital_hits >= 2:
        score -= 15

    for row in rows[:18]:
        row_text = " ".join(str(c).lower() for c in row if c)
        has_desc = any(k in row_text for k in _BUDGET_HEADER_HINTS["descricao"])
        has_qtd = any(k in row_text for k in _BUDGET_HEADER_HINTS["quantidade"])
        has_val = any(k in row_text for k in _BUDGET_HEADER_HINTS["valor"])
        has_cod = any(k in row_text for k in _BUDGET_HEADER_HINTS["codigo"])
        has_bdi = any(k in row_text for k in _BUDGET_HEADER_HINTS["bdi"])
        has_unit = any(k in row_text for k in _BUDGET_HEADER_HINTS["unidade"])
        if has_desc and (has_qtd or has_val):
            score += 28
        if has_cod and (has_qtd or has_val):
            score += 22
        if has_bdi and has_cod:
            score += 12
        if has_unit and has_qtd and has_cod:
            score += 10

    code_rows = 0
    for row in rows[1 : min(45, len(rows))]:
        line = " ".join(str(c) for c in row if c)
        if _SERVICE_CODE_PATTERN.search(line):
            code_rows += 1
    score += min(code_rows * 4, 36)

    numeric_rows = 0
    for row in rows[1 : min(35, len(rows))]:
        nums = sum(1 for c in row if _coerce_number(c) > 0)
        if nums >= 2:
            numeric_rows += 1
    score += min(numeric_rows * 2, 20)

    if "orçamento" in sample_text or "orcamento" in sample_text:
        score += 8
    if "composição" in sample_text or "composicao" in sample_text:
        score += 6

    return score


def _is_likely_budget_table(rows: List[List[Any]], min_score: int = 18) -> bool:
    return _score_budget_table_likelihood(rows) >= min_score


def _items_all_missing_prices(items: List[Any]) -> bool:
    executive: List[Dict[str, Any]] = []
    for raw in items:
        if not isinstance(raw, dict):
            continue
        tipo = str(raw.get("tipo") or "item").lower()
        desc = str(raw.get("descricao") or raw.get("description") or "").lower()
        if tipo == "grupo" or "total do grupo" in desc:
            continue
        executive.append(raw)
    if not executive:
        return False
    missing = sum(
        1
        for it in executive
        if _coerce_number(it.get("valor_unitario") or it.get("unitPrice")) <= 0
        and _coerce_number(it.get("valor_total") or it.get("totalValue")) <= 0
    )
    return missing >= max(1, len(executive) // 2)


def _rows_likely_missing_prices(rows: List[List[Any]]) -> bool:
    """Detecta quando colunas de preço do PDF vieram vazias na extração tabular."""
    if not rows or len(rows) < 2:
        return False

    header_idx = -1
    unit_col = -1
    total_col = -1
    qty_col = -1

    for idx, row in enumerate(rows[:25]):
        row_text = " ".join(str(c).lower() for c in row if c)
        if "preço unit" in row_text or "preco unit" in row_text:
            header_idx = idx
            for col_idx, cell in enumerate(row):
                cell_lower = str(cell or "").lower().strip()
                if unit_col < 0 and ("preço unit" in cell_lower or "preco unit" in cell_lower):
                    unit_col = col_idx
                if total_col < 0 and ("preço total" in cell_lower or "preco total" in cell_lower):
                    total_col = col_idx
                if qty_col < 0 and (
                    "qtde" in cell_lower
                    or "quant" in cell_lower
                    or "qtd" in cell_lower
                ):
                    qty_col = col_idx
            break

    if header_idx < 0:
        return False

    data_rows = rows[header_idx + 1 : header_idx + 21]
    priced_rows = 0
    empty_price_rows = 0

    for row in data_rows:
        if _count_nonempty_table_rows([row]) == 0:
            continue
        desc = ""
        if qty_col >= 0 and qty_col < len(row):
            desc = str(row[qty_col] or "")
        if not _coerce_number(desc) and len(str(row[0] if row else "")) < 2:
            continue

        unit_val = _coerce_number(row[unit_col]) if unit_col >= 0 and unit_col < len(row) else 0
        total_val = _coerce_number(row[total_col]) if total_col >= 0 and total_col < len(row) else 0
        if unit_val > 0 or total_val > 0:
            priced_rows += 1
        else:
            empty_price_rows += 1

    return empty_price_rows >= 2 and priced_rows == 0


def _items_from_rows_fallback(rows: List[List[Any]], page: int) -> List[Dict[str, Any]]:
    """Extrai itens localmente quando a IA não retorna linhas válidas."""
    parser = BudgetParser()
    parsed_items, _ = parser.parse_table(rows, page)
    fallback: List[Dict[str, Any]] = []
    template_sem_precos = _rows_likely_missing_prices(rows)
    for idx, it in enumerate(parsed_items, start=1):
        if not isinstance(it, dict):
            continue
        descricao = str(it.get("descricao") or "").strip()
        if len(descricao) < 3:
            continue
        q = _coerce_number(it.get("quantidade"))
        vu = _coerce_number(it.get("valor_unitario"))
        vt = _coerce_number(it.get("valor_total"))
        bdi = _coerce_bdi(it.get("bdi"))
        if vt <= 0 and q > 0 and vu > 0:
            vt = q * vu
        if q <= 0 and vu <= 0 and vt <= 0:
            continue
        alertas: List[str] = []
        if template_sem_precos and vu <= 0 and vt <= 0:
            alertas.append("Preços em branco no edital — preencha manualmente ou use catálogo")
        fallback.append(
            {
                "item": str(idx),
                "tipo": "item",
                "banco": "",
                "codigo": str(it.get("codigo") or "").strip(),
                "descricao": descricao,
                "bdi": bdi,
                "unidade": str(it.get("unidade") or "un"),
                "quantidade": q,
                "valor_unitario": vu,
                "valor_total": vt,
                "origem_extracao": "parser_local",
                "alertas": alertas,
            }
        )
    return fallback


def _deduplicate_orcamento_items(items: List[Any]) -> List[Dict[str, Any]]:
    """Remove itens repetidos após merge de várias tabelas (preserva tabelas distintas)."""
    seen: set[tuple[str, str, str, float, float]] = set()
    result: List[Dict[str, Any]] = []
    for raw in items:
        if not isinstance(raw, dict):
            continue
        source = str(raw.get("_source_table_id") or raw.get("_source_page") or "").strip().lower()
        codigo = str(raw.get("codigo") or raw.get("code") or "").strip().lower()
        descricao = str(raw.get("descricao") or raw.get("description") or "").strip().lower()[:120]
        quantidade = round(_coerce_number(raw.get("quantidade") or raw.get("qty")), 4)
        valor_unitario = round(
            _coerce_number(raw.get("valor_unitario") or raw.get("unitPrice") or raw.get("unit_value")),
            2,
        )
        key = (source, codigo, descricao, quantidade, valor_unitario)
        if key in seen:
            continue
        if not codigo and not descricao:
            continue
        seen.add(key)
        result.append(raw)
    return result


def _resolve_rows_for_candidate(
    candidate_id: str,
    selected_candidate: Dict[str, Any] | None,
    all_tables: List[Dict],
    camelot_tables: Any,
) -> Tuple[List[List[Any]], int, str]:
    """
    Resolve a matriz de linhas para o candidato escolhido na detecção.
    Prioriza as linhas cacheadas em detect-tables (mesmo recorte que o usuário viu).
    """
    page_hint = 1
    if selected_candidate:
        page_hint = int(
            selected_candidate.get("num_pagina")
            or selected_candidate.get("pagina")
            or 1
        )
        cached_rows = selected_candidate.get("rows")
        if isinstance(cached_rows, list) and cached_rows:
            nonempty = _count_nonempty_table_rows(cached_rows)
            if nonempty >= 3:
                logger.info(
                    "Tabela %s resolvida via cache detect-tables (pág %s, %s linhas, %s com conteúdo)",
                    candidate_id,
                    page_hint,
                    len(cached_rows),
                    nonempty,
                )
                return cached_rows, page_hint, candidate_id

    options: List[Tuple[str, List[List[Any]], int, str, int]] = []
    camelot_idx = _candidate_camelot_index(candidate_id)

    if camelot_tables is not None and camelot_idx is not None:
        try:
            ct = camelot_tables[camelot_idx]
            ct_page = int(ct.page)
            if ct_page == page_hint:
                rows = _camelot_table_to_rows(ct)
                options.append(
                    (
                        "camelot_index",
                        rows,
                        ct_page,
                        candidate_id,
                        _count_nonempty_table_rows(rows),
                    )
                )
        except (IndexError, AttributeError, TypeError) as exc:
            logger.warning("Falha ao ler Camelot[%s] para %s: %s", camelot_idx, candidate_id, exc)

    if camelot_tables is not None:
        for idx, ct in enumerate(camelot_tables):
            if int(ct.page) != page_hint:
                continue
            if camelot_idx is not None and idx == camelot_idx:
                continue
            rows = _camelot_table_to_rows(ct)
            options.append(
                (
                    f"camelot_page_{idx}",
                    rows,
                    page_hint,
                    candidate_id,
                    _count_nonempty_table_rows(rows),
                )
            )

    page_tables = [t for t in all_tables if int(t.get("page") or 0) == page_hint]
    for table in page_tables:
        rows = table.get("rows") or []
        options.append(
            (
                "pdfplumber",
                rows,
                page_hint,
                str(table.get("table_id") or candidate_id),
                _count_nonempty_table_rows(rows),
            )
        )

    selected = _find_table_candidate(all_tables, candidate_id)
    if selected:
        rows = selected.get("rows") or []
        options.append(
            (
                "pdfplumber_id",
                rows,
                int(selected.get("page") or page_hint),
                str(selected.get("table_id") or candidate_id),
                _count_nonempty_table_rows(rows),
            )
        )

    if options:
        def score(option: Tuple[str, List[List[Any]], int, str, int]) -> Tuple[int, int]:
            source, _, page, _, nonempty = option
            if source == "camelot_index":
                source_rank = 4
            elif source.startswith("pdfplumber"):
                source_rank = 3
            elif source.startswith("camelot_page"):
                source_rank = 2
            else:
                source_rank = 1
            page_bonus = 1000 if page == page_hint else 0
            return (nonempty + page_bonus, source_rank)

        best = max(options, key=score)
        source, rows, page, resolved_id, nonempty = best
        logger.info(
            "Tabela %s resolvida via %s (%s, pág %s, %s linhas, %s com conteúdo)",
            candidate_id,
            source,
            resolved_id,
            page,
            len(rows),
            nonempty,
        )
        return rows, page, candidate_id

    logger.warning("Nenhuma linha encontrada para candidato %s (página %s)", candidate_id, page_hint)
    return [], page_hint, candidate_id


def _find_table_candidate(all_tables: List[Dict], table_id: str) -> Dict | None:
    if not table_id:
        return None
    for t in all_tables:
        if t.get("table_id") == table_id:
            return t
    if str(table_id).startswith("tbl-mock-"):
        try:
            idx = int(str(table_id).replace("tbl-mock-", "")) - 1
        except ValueError:
            return None
        if 0 <= idx < len(all_tables):
            return all_tables[idx]
    return None


def _find_table_for_page(all_tables: List[Dict], page_number: int) -> Dict | None:
    page_tables = [table for table in all_tables if int(table.get("page") or 0) == int(page_number)]
    if not page_tables:
        return None

    def sort_key(table: Dict[str, Any]) -> tuple[int, int]:
        rows = table.get("rows") or []
        columns = table.get("columns") or 0
        return (len(rows), int(columns))

    return sorted(page_tables, key=sort_key, reverse=True)[0]


def _page_thumbnail_base64(
    file_path: Path,
    page_num: int,
    matrix_scale: float = DETECT_TABLES_THUMB_SCALE,
) -> str:
    doc = fitz.open(str(file_path))
    try:
        page = doc[page_num - 1]
        pix = page.get_pixmap(matrix=fitz.Matrix(matrix_scale, matrix_scale))
        return base64.b64encode(pix.tobytes("png")).decode("utf-8")
    finally:
        doc.close()


def _dedupe_budget_table_candidates(
    scored: List[Tuple[int, Dict[str, Any]]],
) -> List[Dict[str, Any]]:
    """Mantém a melhor tabela por página (evita duplicata entre estratégias de extração)."""
    by_page: Dict[int, List[Tuple[int, Dict[str, Any]]]] = {}
    for score, entry in scored:
        page_num = int(entry.get("pagina") or 0)
        by_page.setdefault(page_num, []).append((score, entry))

    def ranking_value(entry: Dict[str, Any]) -> float:
        score = int(entry.get("budget_score") or 0)
        rows = int(entry.get("row_count") or 0)
        return score + min(rows, 60)

    deduped: List[Dict[str, Any]] = []
    for page_num in sorted(by_page):
        page_items = sorted(
            by_page[page_num],
            key=lambda item: ranking_value(item[1]),
            reverse=True,
        )
        deduped.append(page_items[0][1])
    return deduped


def _pdfplumber_detect_options(
    file_path: Path,
    min_nonempty_rows: int = 8,
    max_pages: int | None = DETECT_TABLES_MAX_PAGES,
) -> List[Dict[str, Any]]:
    """Candidatos de tabela via pdfplumber (mais rápido que Camelot em PDFs de orçamento)."""
    try:
        all_tables = _extract_tables_from_pdf_path(file_path, max_pages=max_pages)
    except Exception as exc:
        logger.warning("pdfplumber detect: %s", exc)
        return []

    scored: List[Tuple[int, Dict[str, Any]]] = []
    for table in all_tables:
        rows = table.get("rows") or []
        nonempty = _count_nonempty_table_rows(rows)
        budget_score = _score_budget_table_likelihood(rows)
        min_rows_required = 4 if budget_score >= 35 else min_nonempty_rows
        if nonempty < min_rows_required:
            continue
        page_num = int(table.get("page") or 1)
        table_id = str(table.get("table_id") or f"page_{page_num}_table_0")
        preview = _preview_text_for_table_rows(rows)
        name = _guess_table_name_from_preview(preview, len(scored) + 1)
        scored.append(
            (
                budget_score,
                {
                    "id": table_id,
                    "pagina": page_num,
                    "num_pagina": page_num,
                    "nome_tabela": f"{name} (Pág {page_num}, {nonempty} linhas)",
                    "preview_texto": preview,
                    "coordenadas": None,
                    "source": "pdfplumber",
                    "row_count": nonempty,
                    "budget_score": budget_score,
                    "is_budget_likely": budget_score >= 18,
                    "rows": rows,
                },
            )
        )

    likely = [entry for score, entry in scored if score >= 18]
    fallback_limit = min(20, DETECT_TABLES_MAX_CANDIDATES)
    options = likely if likely else [entry for _, entry in sorted(scored, key=lambda x: -x[0])[:fallback_limit]]
    options = _dedupe_budget_table_candidates([(int(o.get("budget_score") or 0), o) for o in options])
    if len(options) > DETECT_TABLES_MAX_CANDIDATES:
        options = options[:DETECT_TABLES_MAX_CANDIDATES]
    if not likely and options:
        logger.warning(
            "detect-tables: nenhuma tabela com score alto; retornando %s melhores candidatos",
            len(options),
        )
    options.sort(
        key=lambda o: (
            int(o.get("pagina") or 0),
            -int(o.get("budget_score") or 0),
            -int(o.get("row_count") or 0),
        )
    )

    thumb_cache: Dict[int, str] = {}
    for option in options:
        page_num = int(option.get("pagina") or 1)
        if page_num not in thumb_cache:
            try:
                thumb_cache[page_num] = _page_thumbnail_base64(file_path, page_num)
            except Exception as exc:
                logger.warning("thumbnail página %s: %s", page_num, exc)
                thumb_cache[page_num] = ""
        option["imagem_base64"] = thumb_cache.get(page_num) or None

    return options


def _guess_table_name_from_preview(preview_text: str, fallback_index: int) -> str:
    text = preview_text.lower()
    if "orçamento sintético" in text or "orcamento sintetico" in text:
        return "Orçamento Sintético"
    if "quantitativo" in text or "planilha" in text:
        return "Planilha de Quantitativos"
    if "composi" in text:
        return "Composições"
    if "cronograma" in text:
        return "Cronograma de Desembolso"
    return f"Tabela {fallback_index}"


def _rows_from_analytic_items(items: List[Dict]) -> List[List[Any]]:
    header = ["Descrição", "Quantidade", "Unidade", "Valor Unitário", "Valor Total"]
    out: List[List[Any]] = [header]
    for it in items:
        if not isinstance(it, dict):
            continue
        out.append(
            [
                str(it.get("descricao", "")),
                str(it.get("quantidade", 0)),
                str(it.get("unidade", "un")),
                str(it.get("valor_unitario", 0)),
                str(it.get("valor_total", 0)),
            ]
        )
    return out


# FastAPI app
app = FastAPI(
    title=API_TITLE,
    version=API_VERSION,
    description=API_DESCRIPTION,
)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=FRONTEND_URLS,
    allow_origin_regex=CORS_ORIGIN_REGEX or None,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============== STATIC FILES (FRONTEND) ==============
# Servir arquivos estáticos do frontend build
FRONTEND_DIST = BASE_DIR.parent / "frontend" / "dist"
if FRONTEND_DIST.exists():
    logger.info(f"✅ Frontend dist encontrado: {FRONTEND_DIST}")
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets", check_dir=False), name="assets")
else:
    logger.warning(f"⚠️  Frontend dist não encontrado: {FRONTEND_DIST}")

async def _cloud_upload_pdf_background(
    upload_id: str,
    user_id: str,
    pdf_bytes: bytes,
    filename: str,
    *,
    size_bytes: int,
) -> None:
    """Envia PDF ao Firebase Storage e persiste URL nos metadados."""
    try:
        if not is_storage_available():
            meta = _load_upload_meta(upload_id)
            meta["cloudUploadStatus"] = "unavailable"
            _save_upload_meta(upload_id, meta)
            return

        storage_url = await upload_pdf_bytes_async(
            upload_id=upload_id,
            user_id=user_id,
            pdf_bytes=pdf_bytes,
        )
        if not storage_url:
            meta = _load_upload_meta(upload_id)
            meta["cloudUploadStatus"] = "failed"
            _save_upload_meta(upload_id, meta)
            return

        meta = _load_upload_meta(upload_id)
        meta["storageUrl"] = storage_url
        meta["cloudUploadStatus"] = "completed"
        _save_upload_meta(upload_id, meta)

        try:
            OrcamentoFirestore.save_upload_record(
                user_id=user_id,
                upload_id=upload_id,
                filename=filename,
                storage_url=storage_url,
                size_bytes=size_bytes,
            )
        except Exception as exc:
            logger.warning("Falha ao registrar upload no Firestore: %s", exc)
    except Exception as exc:
        logger.error("Upload em nuvem falhou para %s: %s", upload_id, exc)
        meta = _load_upload_meta(upload_id)
        meta["cloudUploadStatus"] = "failed"
        _save_upload_meta(upload_id, meta)


async def _ensure_pdf_on_disk(upload_id: str, user_id: str) -> Path:
    """Garante PDF no disco local — baixa do Firebase Storage se necessário (Render ephemeral)."""
    file_path = UPLOAD_FOLDER / f"{upload_id}.pdf"
    if file_path.is_file():
        return file_path

    await wait_for_cloud_upload(upload_id, timeout_seconds=60)
    await _resolve_pdf_bytes_for_upload(upload_id, user_id)

    if not file_path.is_file():
        raise HTTPException(status_code=404, detail=f"Upload não encontrado: {upload_id}")
    return file_path


async def _resolve_pdf_bytes_for_upload(upload_id: str, user_id: str) -> bytes:
    """Obtém bytes do PDF (disco local ou Firebase Storage)."""
    file_path = UPLOAD_FOLDER / f"{upload_id}.pdf"
    if file_path.is_file():
        return file_path.read_bytes()

    meta = _load_upload_meta(upload_id)
    owner = meta.get("userId") or user_id
    cloud_bytes = await download_pdf_bytes_async(upload_id=upload_id, user_id=owner)
    if cloud_bytes:
        try:
            file_path.write_bytes(cloud_bytes)
        except OSError as exc:
            logger.warning("Não foi possível cachear PDF localmente: %s", exc)
        return cloud_bytes

    raise HTTPException(
        status_code=404,
        detail=f"PDF não encontrado (local nem nuvem): {upload_id}",
    )


@app.on_event("startup")
async def _startup_analitico_queue() -> None:
    start_queue_worker(process_queued_analitico_job)
    start_abc_queue_worker(process_abc_queue_job)
    if is_celery_queue_enabled():
        logger.info("Filas: Celery + Redis (analítico e Curva ABC)")
    else:
        logger.info("Filas: workers em memória (dev / sem Redis)")


# ============== HEALTH CHECK ==============
@app.get("/health")
async def health_check():
    """Health check endpoint (Render usa para manter/acordar o serviço)."""
    return {
        "status": "online",
        "timestamp": datetime.now().isoformat(),
        "version": API_VERSION,
        "environment": ENVIRONMENT,
    }

# ============== TEST ==============
@app.get("/api/test")
async def test_endpoint():
    """Test endpoint to verify API is working"""
    return {
        "message": "✅ Backend está funcionando!",
        "timestamp": datetime.now().isoformat(),
    }

# ============== AI STANDARDIZATION ==============
class AIItem(BaseModel):
    descricao: str
    quantidade: float
    unidade: str
    valor_unitario: float
    valor_total: float


class AIStandardizeRequest(BaseModel):
    items: List[AIItem] = Field(default_factory=list)


@app.post("/api/ai/standardize")
async def ai_standardize_items(payload: AIStandardizeRequest):
    system_message = (
        "Você é um assistente de normalização de dados de orçamento. "
        "Padronize descrições e unidades de medida, mantendo quantidades e valores. "
        "Retorne apenas JSON válido com uma lista de itens."
    )
    user_message = {
        "tarefa": "padronizar_itens",
        "regras": {
            "unidades": ["un", "m", "m2", "m3", "kg", "t", "l"],
            "manter_campos": ["quantidade", "valor_unitario", "valor_total"],
        },
        "items": [item.model_dump() for item in payload.items],
        "formato_retorno": {
            "items": [
                {
                    "descricao": "string",
                    "quantidade": 0,
                    "unidade": "string",
                    "valor_unitario": 0,
                    "valor_total": 0,
                }
            ]
        },
    }

    try:
        gemini_request_body = {
            "contents": [
                {
                    "parts": [
                        {"text": system_message},
                        {"text": json.dumps(user_message)}
                    ]
                }
            ],
            "generationConfig": {
                "temperature": 0.1,
                "topK": 40,
                "topP": 0.95,
            }
        }

        errors = []
        content = ""
        provider_used = ""

        if OLLAMA_ENABLED:
            try:
                content, provider_used = await _call_ollama_generate_content(
                    system_message=system_message,
                    user_message=user_message,
                    timeout_seconds=min(30.0, OLLAMA_TIMEOUT_SECONDS),
                )
            except AIProviderError as exc:
                errors.append(f"{exc.provider}: {exc.details}")

        if GEMINI_API_KEY:
            try:
                content, provider_used = await _call_gemini_generate_content(
                    gemini_request_body,
                    timeout_seconds=30.0,
                )
            except AIProviderError as exc:
                errors.append(f"{exc.provider}: {exc.details}")

        if not content and OPENROUTER_API_KEY:
            try:
                content, provider_used = await _call_openai_compatible_generate_content(
                    provider="openrouter",
                    base_url="https://openrouter.ai/api/v1",
                    api_key=OPENROUTER_API_KEY,
                    model=OPENROUTER_MODEL,
                    system_message=system_message,
                    user_message=user_message,
                    timeout_seconds=30.0,
                )
            except AIProviderError as exc:
                errors.append(f"{exc.provider}: {exc.details}")

        if not content and GROQ_API_KEY:
            try:
                content, provider_used = await _call_openai_compatible_generate_content(
                    provider="groq",
                    base_url="https://api.groq.com/openai/v1",
                    api_key=GROQ_API_KEY,
                    model=GROQ_MODEL,
                    system_message=system_message,
                    user_message=user_message,
                    timeout_seconds=30.0,
                )
            except AIProviderError as exc:
                errors.append(f"{exc.provider}: {exc.details}")

        if not content and OPENAI_API_KEY:
            try:
                content, provider_used = await _call_openai_compatible_generate_content(
                    provider="openai",
                    base_url="https://api.openai.com/v1",
                    api_key=OPENAI_API_KEY,
                    model=OPENAI_MODEL,
                    system_message=system_message,
                    user_message=user_message,
                    timeout_seconds=30.0,
                )
            except AIProviderError as exc:
                errors.append(f"{exc.provider}: {exc.details}")

        if content:
            parsed = json.loads(_clean_json_text(content))
            ai_mode = "remote"
        else:
            parsed = {"items": _local_standardize_items([item.model_dump() for item in payload.items])}
            provider_used = "local:fallback"
            ai_mode = "local"

        items = parsed.get("items") if isinstance(parsed, dict) else parsed
        if not isinstance(items, list):
            raise ValueError("Resposta de IA inválida")

        return {
            "status": "success",
            "items": items,
            "provider": provider_used,
            "mode": ai_mode,
            "warnings": errors,
        }
    except Exception as exc:
        logger.error(f"❌ Erro ao padronizar itens com IA: {exc}")
        raise HTTPException(
            status_code=500,
            detail="Erro ao processar padronização com IA",
        )

# ============== UPLOAD PDF ==============
@app.post("/api/upload")
async def upload_pdf(
    file: UploadFile = File(...),
    user_id: str = Depends(get_current_user_id),
):
    """
    Upload de arquivo PDF
    
    Returns:
        {
            "status": "success",
            "upload_id": "uuid",
            "filename": "documento.pdf",
            "size": 1234567,
            "message": "Arquivo recebido com sucesso"
        }
    """
    try:
        # Validar tipo de arquivo
        if file.content_type != "application/pdf":
            raise HTTPException(
                status_code=400,
                detail="❌ Apenas arquivos PDF são permitidos",
            )
        
        # Validar tamanho (50MB)
        contents = await file.read()
        if len(contents) > MAX_FILE_SIZE:
            max_mb = MAX_FILE_SIZE / 1024 / 1024
            raise HTTPException(
                status_code=413,
                detail=f"❌ Arquivo muito grande. Máximo: {max_mb:.0f}MB. Seu arquivo tem: {len(contents) / 1024 / 1024:.2f}MB",
            )
        
        # Gerar ID único
        upload_id = str(uuid.uuid4())
        # Guarda o PDF com nome controlado (evita path traversal via file.filename)
        file_path = UPLOAD_FOLDER / f"{upload_id}.pdf"
        
        # Salvar arquivo
        with open(file_path, "wb") as buffer:
            buffer.write(contents)

        # Guarda metadados para uso em /api/extract (UX) sem confiar no nome original no filesystem
        _save_upload_meta(
            upload_id,
            {
                "userId": user_id,
                "filename": file.filename,
                "content_type": file.content_type,
                "cloudUploadStatus": "pending",
            },
        )

        asyncio.create_task(
            _cloud_upload_pdf_background(
                upload_id,
                user_id,
                contents,
                file.filename or f"{upload_id}.pdf",
                size_bytes=len(contents),
            )
        )

        logger.info(f"✅ PDF salvo: {file_path} ({len(contents) / 1024 / 1024:.2f}MB)")

        return {
            "status": "success",
            "upload_id": upload_id,
            "filename": file.filename,
            "size": len(contents),
            "cloud_upload_status": "pending",
            "message": "✅ Arquivo recebido com sucesso",
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Erro no upload: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Erro ao fazer upload: {str(e)}",
        )

# ============== EXTRACT PDF ==============
@app.post("/api/extract")
async def extract_pdf(
    upload_id: str,
    user_id: str = Depends(get_current_user_id),
):
    """
    Extrai tabelas do PDF usando pdfplumber
    Salva dados no Firestore e deleta arquivo PDF
    
    Args:
        upload_id: ID retornado pelo endpoint /api/upload
    
    Returns:
        {
            "status": "success",
            "upload_id": "uuid",
            "document_id": "firestore_doc_id",
            "tables_found": 1,
            "tables": [...]
        }
    """
    try:
        if not pdfplumber:
            raise HTTPException(
                status_code=500,
                detail="pdfplumber não está instalado",
            )
        
        upload_id = _validate_upload_id(upload_id)
        file_path = UPLOAD_FOLDER / f"{upload_id}.pdf"
        if not file_path.exists():
            raise HTTPException(
                status_code=404,
                detail=f"❌ Upload não encontrado: {upload_id}",
            )

        meta = _load_upload_meta(upload_id)
        expected_user = meta.get("userId")
        _assert_upload_access(user_id, expected_user)
        filename = str(meta.get("filename") or file_path.name)

        try:
            tables = _extract_tables_from_pdf_path(file_path)
        except RuntimeError as e:
            raise HTTPException(status_code=500, detail=str(e)) from e
        except Exception as e:
            logger.error(f"❌ Erro ao extrair tabelas: {str(e)}")
            raise HTTPException(
                status_code=500,
                detail=f"Erro ao extrair tabelas: {str(e)}",
            ) from e

        logger.info(f"✅ {len(tables)} tabela(s) extraída(s) de {file_path}")
        
        # Parsear itens das tabelas usando parser inteligente
        parser = BudgetParser()
        parsed_data = parser.parse_all_tables(tables)
        items = parsed_data.get('items', [])
        resumo = parsed_data.get('resumo', {})
        
        logger.info(f"📊 Parser extraiu {len(items)} itens (confiança: {resumo.get('confianca', 0):.2f})")
        
        # Salvar no Firestore
        try:
            doc_id = OrcamentoFirestore.save_orcamento(
                user_id=user_id,
                upload_id=upload_id,
                filename=filename,
                tables=tables,
                items_data={'items': items, 'resumo': resumo}
            )
            logger.info(f"✅ Dados salvos no Firestore: {doc_id}")
        except Exception as e:
            logger.error(f"❌ Erro ao salvar no Firestore: {str(e)}")
            # Continuar mesmo se Firestore falhar, dados extraídos ainda serão retornados
            doc_id = None
        
        # Salvar em cache para modo offline
        _OFFLINE_CACHE[upload_id] = {
            "uploadId": upload_id,
            "userId": user_id,
            "filename": filename,
            "tables": tables,
            "items": items,
            "resumo": resumo,
            "uploadedAt": datetime.now().isoformat(),
            "extractedAt": datetime.now().isoformat(),
            "tablesFound": len(tables),
            "itemsFound": len(items),
            "status": "completed"
        }
        logger.info(f"✅ Dados salvos em cache offline: {upload_id}")

        # Persiste em disco para funcionar com múltiplos workers/instâncias
        _save_extracted_cache(upload_id, _OFFLINE_CACHE[upload_id])
        
        # Deletar arquivo PDF
        try:
            file_path.unlink()
            logger.info(f"🗑️  PDF deletado: {file_path}")

            meta_path = _meta_path_for_upload_id(upload_id)
            if meta_path.exists():
                meta_path.unlink()
                logger.info(f"🗑️  Metadados deletados: {meta_path}")
        except Exception as e:
            logger.warning(f"⚠️  Erro ao deletar PDF: {str(e)}")
        
        return {
            "status": "success",
            "upload_id": upload_id,
            "document_id": doc_id,
            "filename": filename,
            "tables_found": len(tables),
            "items_found": len(items),
            "tables": tables,
            "items": items,
            "resumo": resumo,
            "message": "✅ Dados extraídos e processados com sucesso"
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Erro na extração: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=str(e),
        )

# ============== DETECÇÃO / PROCESSAMENTO DE TABELA (CURADORIA + OPENAI) ==============


class ProcessConfirmedRequest(BaseModel):
    upload_id: str
    table_ids: List[str] = Field(default_factory=list)
    # Mantido para retrocompatibilidade
    table_id: str | None = None


def _strip_rows_from_table_options(options: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Remove matrizes de linhas da resposta HTTP (mantidas no cache do servidor)."""
    return [{key: value for key, value in option.items() if key != "rows"} for option in options]


def _camelot_detect_options(file_path: Path, max_pages: int = DETECT_TABLES_MAX_PAGES) -> List[Dict[str, Any]]:
    """Fallback Camelot em páginas limitadas (mais lento que pdfplumber)."""
    doc = fitz.open(str(file_path))
    try:
        page_count = doc.page_count
    finally:
        doc.close()

    pages_spec = f"1-{min(page_count, max_pages)}"
    tables = _get_camelot().read_pdf(str(file_path), pages=pages_spec, flavor="lattice")
    if len(tables) == 0:
        return []

    options: List[Dict[str, Any]] = []
    doc = fitz.open(str(file_path))
    try:
        for idx, table in enumerate(tables):
            page_num = int(table.page)
            page = doc[page_num - 1]
            x0, y0, x1, y1 = table._bbox
            rect = fitz.Rect(x0, page.rect.height - y1, x1, page.rect.height - y0)
            pix = page.get_pixmap(clip=rect, matrix=fitz.Matrix(2, 2))
            b64 = base64.b64encode(pix.tobytes("png")).decode("utf-8")
            camelot_rows = _camelot_table_to_rows(table)
            nonempty = _count_nonempty_table_rows(camelot_rows)
            if nonempty < 3:
                continue
            options.append(
                {
                    "id": f"table-{idx}",
                    "pagina": page_num,
                    "coordenadas": [x0, y0, x1, y1],
                    "imagem_base64": b64,
                    "nome_tabela": f"Tabela {idx + 1} (Pág {page_num}, {nonempty} linhas)",
                    "num_pagina": page_num,
                    "preview_texto": _preview_text_for_table_rows(camelot_rows)
                    or "Visualização disponível via imagem.",
                    "row_count": nonempty,
                    "rows": camelot_rows,
                    "source": "camelot",
                }
            )
    finally:
        doc.close()
    return options


def _detect_table_options_sync(file_path: Path) -> Tuple[List[Dict[str, Any]], bool]:
    """
    Detecta candidatos a tabela: pdfplumber primeiro (rápido), Camelot como fallback.
    Retorna (opções, usou_fallback_camelot).
    """
    options = _pdfplumber_detect_options(file_path)
    if options:
        logger.info("detect-tables: %s candidato(s) via pdfplumber", len(options))
        return options, False

    logger.info("detect-tables: pdfplumber vazio — tentando Camelot (máx. %s págs)", DETECT_TABLES_MAX_PAGES)
    try:
        options = _camelot_detect_options(file_path)
    except Exception as exc:
        logger.warning("detect-tables: Camelot falhou: %s", exc)
        options = []

    return options, True


@app.post("/api/orcamentos/detect-tables")
async def detect_orcamento_tables(
    upload_id: str = Form(...),
    user_id: str = Depends(get_current_user_id),
):
    """
    Lista candidatos a tabela orçamentária (pdfplumber + fallback Camelot em páginas limitadas).
    """
    upload_id = _validate_upload_id(upload_id)
    file_path = await _ensure_pdf_on_disk(upload_id, user_id)

    meta = _load_upload_meta(upload_id)
    expected_user = meta.get("userId")
    _assert_upload_access(user_id, expected_user)

    upload_data = _get_upload_data_from_sources(upload_id) or {}
    cached_options = upload_data.get("table_candidates") or []
    cached_version = int(upload_data.get("table_candidates_version") or 0)
    if cached_options and cached_version >= DETECT_TABLES_CACHE_VERSION:
        return {
            "status": "success",
            "upload_id": upload_id,
            "tables_found": len(cached_options),
            "options": _strip_rows_from_table_options(cached_options),
            "mock_fallback": False,
            "cached": True,
        }

    try:
        options, fallback_used = await asyncio.to_thread(_detect_table_options_sync, file_path)
    except Exception as exc:
        logger.error("detect-tables: falha na identificação: %s", exc)
        raise HTTPException(status_code=500, detail=f"Erro ao analisar PDF: {exc}") from exc

    _OFFLINE_CACHE.setdefault(upload_id, {})
    _OFFLINE_CACHE[upload_id]["table_candidates"] = options
    _OFFLINE_CACHE[upload_id]["table_candidates_version"] = DETECT_TABLES_CACHE_VERSION
    _OFFLINE_CACHE[upload_id]["uploadId"] = upload_id
    _OFFLINE_CACHE[upload_id]["userId"] = user_id
    if meta.get("filename"):
        _OFFLINE_CACHE[upload_id]["filename"] = meta.get("filename")
    _save_extracted_cache(upload_id, _OFFLINE_CACHE[upload_id])

    return {
        "status": "success",
        "upload_id": upload_id,
        "tables_found": len(options),
        "options": _strip_rows_from_table_options(options),
        "mock_fallback": fallback_used,
        "cached": False,
    }


@app.get("/api/orcamentos/{upload_id}/table-candidates")
async def get_orcamento_table_candidates(
    upload_id: str,
    user_id: str = Depends(get_current_user_id),
):
    """Retorna tabelas já detectadas (cache) sem reprocessar o PDF."""
    upload_id = _validate_upload_id(upload_id)
    meta = _load_upload_meta(upload_id)
    _assert_upload_access(user_id, meta.get("userId"))

    upload_data = _get_upload_data_from_sources(upload_id) or {}
    options = upload_data.get("table_candidates") or []
    return {
        "status": "success",
        "upload_id": upload_id,
        "tables_found": len(options),
        "options": _strip_rows_from_table_options(options),
        "cached": True,
    }


def _normalize_analytic_items(raw_items: List[Any]) -> List[Dict[str, Any]]:
    normalized: List[Dict[str, Any]] = []
    for idx, it in enumerate(raw_items):
        if not isinstance(it, dict):
            continue
        tipo = str(it.get("tipo_linha") or it.get("tipo") or "item").strip().lower()
        descricao_raw = str(it.get("descricao") or it.get("Descrição") or "").strip()
        desc_lower = descricao_raw.lower()
        if tipo in ("grupo", "composicao", "composição"):
            continue
        if "total do grupo" in desc_lower or desc_lower.startswith("total "):
            continue
        q = _coerce_number(it.get("quantidade") or it.get("qty"))
        vu = _coerce_number(
            it.get("valor_unitario")
            or it.get("valor_unitário")
            or it.get("unit_value")
            or it.get("unitPrice")
        )
        vt = _coerce_number(it.get("valor_total") or it.get("total"))
        if vu <= 0 and vt > 0 and q > 0:
            vu = vt / q
        if vt <= 0 and q > 0 and vu > 0:
            vt = q * vu
        confianca = it.get("confianca")
        alertas = it.get("alertas")
        origem_extracao = it.get("origem_extracao") or "openai_orcamento_analitico"
        status = "revisar" if (
            (isinstance(confianca, (int, float)) and float(confianca) < 0.75)
            or (isinstance(alertas, list) and len(alertas) > 0)
        ) else "validado"
        normalized.append(
            {
                "id": f"item_ai_{idx}",
                "item": str(it.get("item") or it.get("item_numero") or ""),
                "tipo": str(it.get("tipo") or "item"),
                "banco": str(it.get("banco") or ""),
                "codigo": str(it.get("codigo") or it.get("Código") or it.get("code") or ""),
                "descricao": str(it.get("descricao") or it.get("Descrição") or "").strip(),
                "bdi": _coerce_bdi(it.get("bdi") or it.get("BDI")),
                "quantidade": q,
                "unidade": str(it.get("unidade", "un") or "un"),
                "valor_unitario": vu,
                "valor_total": vt if vt > 0 else q * vu,
                "status": status,
                "origem": origem_extracao,
                "confianca": confianca,
                "alertas": alertas if isinstance(alertas, list) else [],
            }
        )
    return normalized


@app.post("/api/orcamentos/process-confirmed")
async def process_orcamento_confirmed(
    payload: ProcessConfirmedRequest,
    user_id: str = Depends(get_current_user_id),
):
    """
    Processa a tabela escolhida com GPT-4o e persiste orçamento + ia_metadata.
    """
    upload_id = _validate_upload_id(payload.upload_id)
    meta = _load_upload_meta(upload_id)
    _assert_upload_access(user_id, meta.get("userId"))

    ids_to_process = payload.table_ids
    if not ids_to_process and payload.table_id:
        ids_to_process = [payload.table_id]
    if not ids_to_process:
        raise HTTPException(status_code=400, detail="Nenhuma tabela selecionada")

    return await _execute_process_confirmed(upload_id, user_id, ids_to_process)


async def _execute_process_confirmed(
    upload_id: str,
    user_id: str,
    ids_to_process: list[str],
) -> Dict[str, Any]:
    """Núcleo do process-confirmed (usado pela API e pela fila ABC)."""
    upload_id = _validate_upload_id(upload_id)
    file_path = UPLOAD_FOLDER / f"{upload_id}.pdf"
    if not file_path.exists():
        raise HTTPException(status_code=404, detail=f"Upload não encontrado: {upload_id}")

    meta = _load_upload_meta(upload_id)
    expected_user = meta.get("userId")
    _assert_upload_access(user_id, expected_user)

    filename = str(meta.get("filename") or file_path.name)

    upload_data = _get_upload_data_from_sources(upload_id) or {}
    table_candidates = upload_data.get("table_candidates") or []

    all_tables: List[Dict] = []
    try:
        all_tables = _extract_tables_from_pdf_path(file_path, max_pages=DETECT_TABLES_MAX_PAGES)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Erro ao ler PDF: {exc}") from exc

    camelot_tables = None
    needs_camelot = any(
        not (next((c for c in table_candidates if c.get("id") == t_id), {}) or {}).get("rows")
        for t_id in ids_to_process
    )
    if needs_camelot:
        try:
            doc = fitz.open(str(file_path))
            try:
                page_count = doc.page_count
            finally:
                doc.close()
            pages_spec = f"1-{min(page_count, DETECT_TABLES_MAX_PAGES)}"
            camelot_tables = _get_camelot().read_pdf(str(file_path), pages=pages_spec, flavor="lattice")
            logger.info(
                "Camelot: %s tabela(s) carregadas para process-confirmed (%s)",
                len(camelot_tables),
                pages_spec,
            )
        except Exception as exc:
            logger.warning("Camelot indisponível em process-confirmed: %s", exc)

    candidate_ids = {str(c.get("id")) for c in table_candidates if c.get("id")}
    unknown_ids = [t_id for t_id in ids_to_process if t_id and t_id not in candidate_ids]
    if unknown_ids:
        raise HTTPException(
            status_code=400,
            detail=(
                "Tabela(s) selecionada(s) não correspondem à detecção atual: "
                f"{', '.join(unknown_ids)}. Volte ao passo anterior e selecione novamente."
            ),
        )

    logger.info("process-confirmed: upload=%s tabelas=%s", upload_id, ids_to_process)

    combined_items = []
    combined_hierarchical: List[Dict[str, Any]] = []
    combined_resumo = {"total_items": 0, "valor_total": 0.0, "metodo": "gpt-4o (multi-table)"}
    ia_metadata_list = []
    pdf_bytes = file_path.read_bytes()
    tables_out = []

    tables_total = len([t for t in ids_to_process if t])
    update_abc_job(
        upload_id,
        pages_total=tables_total,
        pages_done=0,
        message=(
            f"Preparando análise de {tables_total} tabela(s)…"
            if tables_total
            else "IA analisando tabelas…"
        ),
    )

    table_index = 0
    for t_id in ids_to_process:
        if not t_id:
            continue

        update_abc_job(
            upload_id,
            pages_done=table_index,
            pages_total=tables_total,
            message=f"IA analisando tabela {table_index + 1} de {tables_total}…",
        )
            
        selected_candidate = next(
            (item for item in table_candidates if item.get("id") == t_id),
            None,
        )
        if not selected_candidate:
            raise HTTPException(
                status_code=400,
                detail=f"Tabela {t_id} não encontrada entre as opções detectadas.",
            )

        cached_rows = selected_candidate.get("rows")
        if cached_rows and _count_nonempty_table_rows(cached_rows) >= 3:
            rows = cached_rows
            page = int(
                selected_candidate.get("pagina")
                or selected_candidate.get("num_pagina")
                or 1
            )
            resolved_table_id = str(selected_candidate.get("id") or t_id)
            logger.info(
                "Tabela %s resolvida via cache de detecção (pág %s, %s linhas)",
                t_id,
                page,
                len(rows),
            )
        else:
            rows, page, resolved_table_id = _resolve_rows_for_candidate(
                t_id,
                selected_candidate,
                all_tables,
                camelot_tables,
            )
        if not rows:
            logger.warning("Tabela não encontrada para o ID: %s", t_id)
            raise HTTPException(
                status_code=400,
                detail=f"Tabela não encontrada para o ID: {t_id}",
            )

        if _count_nonempty_table_rows(rows) < 3:
            label = str(selected_candidate.get("nome_tabela") or t_id)
            raise HTTPException(
                status_code=400,
                detail=(
                    f"A tabela selecionada \"{label}\" ({t_id}, página {page}) tem poucas linhas "
                    f"({len(rows)}). Escolha outra tabela com o orçamento detalhado "
                    "(Código, Descrição, Qtde, Preço)."
                ),
            )

        candidate_name = str((selected_candidate or {}).get("nome_tabela") or "")
        table_image_b64 = (selected_candidate or {}).get("imagem_base64")
        template_sem_precos = _rows_likely_missing_prices(rows)
        parser_items = _items_from_rows_fallback(rows, page)
        if template_sem_precos:
            logger.info(
                "Colunas de preço vazias em %s (pág %s) — parser local como base estrutural",
                t_id,
                page,
            )

        logger.info(
            "Processando candidato %s → %s na página %s (%s linhas, imagem=%s, parser=%s itens)",
            t_id,
            resolved_table_id,
            page,
            len(rows),
            bool(table_image_b64),
            len(parser_items),
        )

        tables_out.append({
            "page": page,
            "table_id": resolved_table_id,
            "rows": rows,
            "original_rows": len(rows),
            "columns": len(rows[0]) if rows else 0,
        })

        try:
            structured_data, provider_used = await process_selected_table(
                pdf_bytes,
                resolved_table_id,
                table_rows=rows,
                table_page=page,
                table_name=candidate_name,
                table_image_base64=table_image_b64,
            )
            
            items_this_table = structured_data.get("items") or []
            hierarchical_this_table = structured_data.get("hierarchical_items") or []
            if not items_this_table:
                logger.warning(
                    "IA retornou 0 itens para %s (pág %s, %s linhas). Tentando parser local.",
                    t_id,
                    page,
                    len(rows),
                )
                items_this_table = parser_items
                if items_this_table:
                    ia_metadata_list.append(
                        {
                            "table_id": resolved_table_id,
                            "provider": "local:budget_parser_fallback",
                            "resumo": {"total_items": len(items_this_table)},
                        }
                    )
            elif template_sem_precos and parser_items and (
                _items_all_missing_prices(items_this_table)
                or len(items_this_table) < len(parser_items)
            ):
                logger.info(
                    "Mesclando parser local (%s itens) com IA (%s itens) em %s",
                    len(parser_items),
                    len(items_this_table),
                    t_id,
                )
                items_this_table = merge_parser_as_primary(parser_items, items_this_table)
                ia_metadata_list.append(
                    {
                        "table_id": resolved_table_id,
                        "provider": "local:parser_primary_hibrido",
                        "resumo": {"total_items": len(items_this_table)},
                    }
                )
            elif _items_all_missing_prices(items_this_table):
                logger.warning(
                    "IA retornou itens sem preços para %s (pág %s). Tentando parser local.",
                    t_id,
                    page,
                )
                if parser_items:
                    items_this_table = merge_parser_as_primary(parser_items, items_this_table)
                    ia_metadata_list.append(
                        {
                            "table_id": resolved_table_id,
                            "provider": "local:budget_parser_fallback_prices",
                            "resumo": {"total_items": len(items_this_table)},
                        }
                    )

            for raw_item in items_this_table:
                if isinstance(raw_item, dict):
                    raw_item.setdefault("_source_table_id", t_id)
                    raw_item.setdefault("_source_page", page)
            combined_items.extend(items_this_table)
            for raw_item in hierarchical_this_table:
                if isinstance(raw_item, dict):
                    raw_item.setdefault("_source_table_id", t_id)
            combined_hierarchical.extend(hierarchical_this_table)

            resumo_this = structured_data.get("resumo") or {}
            combined_resumo["total_items"] += int(resumo_this.get("total_items") or len(items_this_table))
            combined_resumo["valor_total"] += float(
                resumo_this.get("valor_total")
                or sum(float(item.get("valor_total") or 0) for item in items_this_table)
            )

            used_fallback = any(
                m.get("table_id") == resolved_table_id
                and m.get("provider") == "local:budget_parser_fallback"
                for m in ia_metadata_list
            )
            if not used_fallback:
                ia_metadata_list.append({
                    "table_id": resolved_table_id,
                    "provider": provider_used,
                    "resumo": resumo_this,
                })

            table_index += 1
            update_abc_job(
                upload_id,
                pages_done=table_index,
                pages_total=tables_total,
                message=f"Tabela {table_index} de {tables_total} concluída…",
            )
            
        except OpenAIServiceError as exc:
            logger.warning(f"Erro ao processar tabela {t_id}: {exc}")
            import traceback; traceback.print_exc()
            status = getattr(exc, "status_code", 500) or 500
            raise HTTPException(
                status_code=status,
                detail=f"Erro OpenAI na tabela {t_id}: {str(exc)}",
            )
        except Exception as exc:
            logger.warning(f"Erro inesperado ao processar tabela {t_id}: {exc}")
            import traceback; traceback.print_exc()
            raise HTTPException(status_code=500, detail=f"Erro inesperado na tabela {t_id}: {str(exc)}")

    if not combined_items:
        tabelas_txt = ", ".join(ids_to_process)
        raise HTTPException(
            status_code=422,
            detail=(
                "Nenhum item de orçamento foi extraído das tabelas selecionadas. "
                "As páginas marcadas parecem ser capa, edital ou texto jurídico — não a planilha "
                "com colunas Código, Descrição, Qtde e Preço Unitário. "
                f"Tabelas: {tabelas_txt}. Volte ao passo anterior e selecione páginas da planilha analítica "
                "(as sugestões no topo da lista costumam ser as corretas)."
            ),
        )

    combined_items = _deduplicate_orcamento_items(combined_items)
    if combined_hierarchical:
        combined_hierarchical = _deduplicate_orcamento_items(combined_hierarchical)
    else:
        combined_hierarchical = combined_items
    logger.info(
        "Itens após deduplicação: %s (hierárquicos: %s, tabelas processadas: %s)",
        len(combined_items),
        len(combined_hierarchical),
        len(ids_to_process),
    )

    # Normalizar os itens combinados (executivos para Curva ABC)
    normalized_items = _normalize_analytic_items(combined_items)
    structured_items = combined_hierarchical
    
    # Atualizar o resumo final
    combined_resumo["total_items"] = len(normalized_items)
    combined_resumo["valor_total"] = sum(float(it.get("valor_total") or 0) for it in normalized_items)

    ia_metadata_final = {
        "tables_processed": len(ia_metadata_list),
        "details": ia_metadata_list,
        "combined_resumo": combined_resumo,
        "model": OPENAI_ORCAMENTO_MODEL,
        "engine_used": "openai_gpt4o (multi)",
        "provider": "openai"
    }

    try:
        doc_id = OrcamentoFirestore.save_orcamento(
            user_id=user_id,
            upload_id=upload_id,
            filename=filename,
            tables=tables_out,
            items_data={
                "items": normalized_items,
                "hierarchical_items": structured_items,
                "resumo": combined_resumo,
            },
            ia_metadata=ia_metadata_final,
        )
    except Exception as exc:
        logger.error("process-confirmed: erro ao salvar no Firestore: %s", exc)
        doc_id = upload_id

    _OFFLINE_CACHE.setdefault(upload_id, {})
    _OFFLINE_CACHE[upload_id].update(
        {
            "uploadId": upload_id,
            "userId": user_id,
            "filename": filename,
            "items": normalized_items,
            "tables": tables_out,
            "resumo": combined_resumo,
            "status": "completed",
            "itemsData": {
                "items": normalized_items,
                "hierarchical_items": structured_items,
                "resumo": combined_resumo,
            },
            "ia_metadata": ia_metadata_final,
        }
    )
    _save_extracted_cache(upload_id, _OFFLINE_CACHE[upload_id])

    log_ai_exchange(
        operation="process_confirmed",
        provider="pipeline",
        model=str(ia_metadata_final.get("model", "")),
        input_payload={
            "upload_id": upload_id,
            "table_ids": ids_to_process,
        },
        output_payload={
            "items_found": len(normalized_items),
        }
    )

    return {
        "status": "success",
        "upload_id": upload_id,
        "document_id": doc_id,
        "filename": filename,
        "tables_found": len(all_tables),
        "items_found": len(normalized_items),
        "tables": tables_out,
        "items": normalized_items,
        "structured_items": structured_items,
        "hierarchical_items": structured_items,
        "resumo": combined_resumo,
        "ia_metadata": ia_metadata_final,
        "message": f"✅ Dados extraídos de {len(ia_metadata_list)} tabela(s) com sucesso",
    }


class AbcRegisterJobItem(BaseModel):
    upload_id: str
    filename: str


class AbcBatchRegisterRequest(BaseModel):
    jobs: list[AbcRegisterJobItem] = Field(..., min_length=1)


class AbcJobUpdateRequest(BaseModel):
    status: str | None = None
    message: str | None = None
    tables_found: int | None = None
    error: str | None = None


class AbcBatchStatusRequest(BaseModel):
    upload_ids: list[str] = Field(..., min_length=1)


class AbcProcessRequest(BaseModel):
    upload_id: str
    table_ids: list[str] = Field(..., min_length=1)


def _build_abc_job_status(upload_id: str) -> Dict[str, Any]:
    from services.abc_queue import get_queue_position

    job = get_abc_job(upload_id)
    if not job:
        return {
            "upload_id": upload_id,
            "status": "not_found",
            "message": "Job não encontrado",
            "queue_position": 0,
            "tables_found": 0,
        }

    position = get_queue_position(upload_id)
    if job.get("status") == "queued" and position > 0:
        job = {**job, "queue_position": position}

    return job


@app.post("/api/abc-analysis/batch-register")
async def abc_batch_register(
    payload: AbcBatchRegisterRequest,
    user_id: str = Depends(get_current_user_id),
):
    """Registra lote de análises Curva ABC após upload dos PDFs."""
    registered: list[Dict[str, Any]] = []
    for item in payload.jobs:
        upload_id = _validate_upload_id(item.upload_id)
        meta = _load_upload_meta(upload_id)
        _assert_upload_access(user_id, meta.get("userId"))
        job = init_abc_job(
            upload_id,
            user_id=user_id,
            filename=item.filename,
            status="uploading",
            message="Arquivo recebido — aguardando detecção de tabelas…",
        )
        registered.append(job)
    return {"status": "success", "jobs": registered}


@app.patch("/api/abc-analysis/{upload_id}")
async def abc_update_job_status(
    upload_id: str,
    payload: AbcJobUpdateRequest,
    user_id: str = Depends(get_current_user_id),
):
    """Atualiza status de um job ABC (ex.: após detect-tables no frontend)."""
    upload_id = _validate_upload_id(upload_id)
    meta = _load_upload_meta(upload_id)
    _assert_upload_access(user_id, meta.get("userId"))

    job = get_abc_job(upload_id)
    if not job:
        init_abc_job(
            upload_id,
            user_id=user_id,
            filename=str(meta.get("filename") or f"{upload_id}.pdf"),
        )

    fields: Dict[str, Any] = {}
    if payload.status:
        if payload.status not in {
            "uploading",
            "detecting",
            "awaiting_selection",
            "queued",
            "processing",
            "completed",
            "failed",
        }:
            raise HTTPException(status_code=400, detail="Status inválido")
        fields["status"] = payload.status
    if payload.message is not None:
        fields["message"] = payload.message
    if payload.tables_found is not None:
        fields["tables_found"] = payload.tables_found
    if payload.error is not None:
        fields["error"] = payload.error

    if fields:
        update_abc_job(upload_id, **fields)

    return {"status": "success", "job": _build_abc_job_status(upload_id)}


@app.post("/api/abc-analysis/process")
async def abc_enqueue_process(
    payload: AbcProcessRequest,
    user_id: str = Depends(get_current_user_id),
):
    """Enfileira processamento IA após seleção de tabelas."""
    upload_id = _validate_upload_id(payload.upload_id)
    meta = _load_upload_meta(upload_id)
    _assert_upload_access(user_id, meta.get("userId"))

    file_path = UPLOAD_FOLDER / f"{upload_id}.pdf"
    if not file_path.is_file():
        raise HTTPException(status_code=404, detail=f"Upload não encontrado: {upload_id}")

    filename = str(meta.get("filename") or f"{upload_id}.pdf")
    position = enqueue_abc_job(
        AbcQueueJob(
            upload_id=upload_id,
            user_id=user_id,
            filename=filename,
            table_ids=payload.table_ids,
        )
    )
    return {
        "status": "queued",
        "upload_id": upload_id,
        "queue_position": position,
        "message": f"Na fila de processamento (posição {position})…",
    }


@app.get("/api/abc-analysis/list")
async def abc_list_jobs(user_id: str = Depends(get_current_user_id)):
    """Lista análises Curva ABC do usuário."""
    jobs = get_user_jobs(user_id)
    return {"status": "success", "jobs": jobs}


@app.get("/api/abc-analysis/status/{upload_id}")
async def abc_job_status(
    upload_id: str,
    user_id: str = Depends(get_current_user_id),
):
    upload_id = _validate_upload_id(upload_id)
    meta = _load_upload_meta(upload_id)
    _assert_upload_access(user_id, meta.get("userId"))
    return _build_abc_job_status(upload_id)


@app.post("/api/abc-analysis/batch-status")
async def abc_batch_status(
    payload: AbcBatchStatusRequest,
    user_id: str = Depends(get_current_user_id),
):
    jobs: list[Dict[str, Any]] = []
    for raw_id in payload.upload_ids:
        upload_id = _validate_upload_id(raw_id)
        meta = _load_upload_meta(upload_id)
        _assert_upload_access(user_id, meta.get("userId"))
        jobs.append(_build_abc_job_status(upload_id))
    return {"status": "success", "jobs": jobs}


class ProcessAnaliticoFullRequest(BaseModel):
    upload_id: str | None = None
    upload_ids: list[str] | None = None
    force_reprocess: bool = False

    @model_validator(mode="after")
    def _require_upload_ids(self) -> "ProcessAnaliticoFullRequest":
        if not self.upload_id and not self.upload_ids:
            raise ValueError("Informe upload_id ou upload_ids")
        return self

    def resolved_upload_ids(self) -> list[str]:
        if self.upload_ids:
            return self.upload_ids
        if self.upload_id:
            return [self.upload_id]
        return []


class AnaliticoBatchStatusRequest(BaseModel):
    upload_ids: list[str] = Field(..., min_length=1)


def _cached_analitico_payload(upload_id: str) -> Dict[str, Any] | None:
    """Retorna resposta pronta se o upload já tiver análise analítica em cache."""
    data = _get_upload_data_from_sources(upload_id)
    if not data:
        return None
    items_data = data.get("itemsData") or {}
    hierarchical_raw = items_data.get("hierarchical_items") or []
    if not hierarchical_raw:
        return None
    hierarchical = normalize_hierarchical_analitico(hierarchical_raw)
    ia_meta = data.get("ia_metadata") or {}
    combined_resumo = items_data.get("resumo") or ia_meta.get("combined_resumo") or {}
    normalized_items = items_data.get("items") or []
    filename = str(data.get("filename") or upload_id)
    return {
        "status": "success",
        "upload_id": upload_id,
        "document_id": data.get("document_id") or upload_id,
        "filename": filename,
        "items_found": len(normalized_items),
        "hierarchical_items": hierarchical,
        "structured_items": hierarchical,
        "items": normalized_items,
        "resumo": combined_resumo,
        "ia_metadata": ia_meta,
        "cached": True,
        "message": f"✅ Resultado em cache — {len(hierarchical)} linhas hierárquicas",
    }


def _build_analitico_job_status(upload_id: str) -> Dict[str, Any]:
    """Monta resposta de status para um upload_id (job ativo, cache ou erro)."""
    job = get_job(upload_id)
    if job:
        base = {
            "upload_id": upload_id,
            "status": job.get("status") or "processing",
            "pages_total": job.get("pages_total") or 0,
            "pages_done": job.get("pages_done") or 0,
            "current_page": job.get("current_page"),
            "message": job.get("message"),
            "queue_position": job.get("queue_position") or get_queue_position(upload_id),
        }
        if job.get("status") == "completed" and job.get("result"):
            return {**base, "status": "completed", "result": job["result"]}
        if job.get("status") == "failed":
            err_msg = job.get("error") or job.get("message") or "Erro desconhecido"
            return {**base, "status": "failed", "error": err_msg}
        return base

    cached = _cached_analitico_payload(upload_id)
    if cached:
        return {
            "upload_id": upload_id,
            "status": "completed",
            "message": "Resultado em cache",
            "result": cached,
            "pages_total": 0,
            "pages_done": 0,
            "queue_position": 0,
        }
    return {
        "upload_id": upload_id,
        "status": "not_found",
        "message": "Nenhum processamento encontrado",
        "pages_total": 0,
        "pages_done": 0,
        "queue_position": 0,
    }


def _enqueue_single_analitico(
    upload_id: str,
    user_id: str,
    *,
    force_reprocess: bool,
) -> Dict[str, Any]:
    upload_id = _validate_upload_id(upload_id)
    file_path = UPLOAD_FOLDER / f"{upload_id}.pdf"
    meta = _load_upload_meta(upload_id)
    expected_user = meta.get("userId")
    _assert_upload_access(user_id, expected_user)

    if not file_path.is_file() and not meta.get("storageUrl"):
        raise HTTPException(status_code=404, detail=f"Upload não encontrado: {upload_id}")

    if not force_reprocess:
        cached = _cached_analitico_payload(upload_id)
        if cached:
            return {**cached, "queue_position": 0}

    existing = get_job(upload_id)
    if existing and existing.get("status") in {"processing", "queued"}:
        return _build_analitico_job_status(upload_id)

    clear_job(upload_id)
    filename = str(meta.get("filename") or f"{upload_id}.pdf")
    position = enqueue_analitico_job(
        AnaliticoQueueJob(
            upload_id=upload_id,
            user_id=user_id,
            filename=filename,
            force_reprocess=force_reprocess,
        )
    )
    return {
        "status": "processing",
        "upload_id": upload_id,
        "pages_total": 0,
        "pages_done": 0,
        "current_page": None,
        "queue_position": position,
        "message": f"Na fila de processamento (posição {position})…",
    }


@app.post("/api/orcamentos/process-analitico-full")
async def process_analitico_full_pdf(
    payload: ProcessAnaliticoFullRequest,
    user_id: str = Depends(get_current_user_id),
):
    """
    Inicia processamento do PDF inteiro para Orçamento Analítico.
    Aceita upload_id (único) ou upload_ids (lote). Jobs entram em fila sequencial.
    """
    upload_ids = [_validate_upload_id(uid) for uid in payload.resolved_upload_ids()]
    if not upload_ids:
        raise HTTPException(status_code=400, detail="Nenhum upload_id informado")

    if len(upload_ids) == 1:
        result = _enqueue_single_analitico(
            upload_ids[0],
            user_id,
            force_reprocess=payload.force_reprocess,
        )
        if result.get("status") == "success":
            return result
        return result

    jobs: list[Dict[str, Any]] = []
    for upload_id in upload_ids:
        try:
            job_status = _enqueue_single_analitico(
                upload_id,
                user_id,
                force_reprocess=payload.force_reprocess,
            )
            jobs.append(job_status)
        except HTTPException as exc:
            jobs.append(
                {
                    "upload_id": upload_id,
                    "status": "failed",
                    "error": str(exc.detail),
                    "message": str(exc.detail),
                }
            )

    return {
        "status": "batch_accepted",
        "jobs": jobs,
        "message": f"{len(upload_ids)} arquivo(s) enfileirado(s) para processamento sequencial",
    }


@app.post("/api/orcamentos/process-analitico-full/batch-status")
async def process_analitico_full_batch_status(
    payload: AnaliticoBatchStatusRequest,
    user_id: str = Depends(get_current_user_id),
):
    """Consulta status de múltiplos jobs de processamento analítico."""
    jobs: list[Dict[str, Any]] = []
    for raw_id in payload.upload_ids:
        upload_id = _validate_upload_id(raw_id)
        meta = _load_upload_meta(upload_id)
        expected_user = meta.get("userId")
        _assert_upload_access(user_id, expected_user)
        jobs.append(_build_analitico_job_status(upload_id))
    return {"status": "success", "jobs": jobs}


@app.get("/api/orcamentos/process-analitico-full/status/{upload_id}")
async def process_analitico_full_status(
    upload_id: str,
    user_id: str = Depends(get_current_user_id),
):
    """Consulta progresso ou resultado do processamento analítico integral."""
    upload_id = _validate_upload_id(upload_id)
    meta = _load_upload_meta(upload_id)
    expected_user = meta.get("userId")
    _assert_upload_access(user_id, expected_user)

    status_payload = _build_analitico_job_status(upload_id)
    if status_payload.get("status") == "not_found":
        raise HTTPException(
            status_code=404,
            detail="Nenhum processamento em andamento para este upload.",
        )
    if status_payload.get("status") == "failed":
        logger.warning(
            "process-analitico-full status failed upload_id=%s: %s",
            upload_id,
            status_payload.get("error"),
        )
    return status_payload


# ============== ANALYZE WITH AI ==============
class AnalyzeWithAIRequest(BaseModel):
    upload_id: str
    focus: str = "budget"  # budget, items, structure, all


class ReviewedItem(BaseModel):
    id: str | None = None
    descricao: str
    quantidade: float
    unidade: str
    valor_unitario: float
    valor_total: float | None = None
    validado: bool = True
    notas: str | None = ""
    classification: str | None = None
    accumulated_percentage: float | None = None


class SaveReviewedItemsRequest(BaseModel):
    items: List[ReviewedItem] = Field(default_factory=list)

@app.post("/api/analyze-with-ai")
async def analyze_with_ai(
    payload: AnalyzeWithAIRequest,
    user_id: str = Depends(get_current_user_id),
):
    """
    Análise inteligente de dados extraídos (Ollama, Gemini, OpenRouter, Groq, OpenAI ou fallback local).

    Usa IA para:
    - Identificar estrutura de planilha orçamentária
    - Reconhecer colunas (descrição, quantidade, unidade, valor)
    - Filtrar linhas irrelevantes (subtotais, linhas em branco)
    - Validar dados e sugerir correções
    
    Args:
        upload_id: ID retornado pelo /api/upload
        focus: Tipo de análise (budget, items, structure, all)
    
    Returns:
        {
            "status": "success",
            "upload_id": "uuid",
            "analysis": {
                "structure": {...},
                "items": [...],
                "metadata": {...}
            }
        }
    """
    try:
        # Buscar dados extraídos (memória, disco ou Firestore)
        upload_data = _get_upload_data_from_sources(payload.upload_id)
        if not upload_data:
            raise HTTPException(
                status_code=404,
                detail=(
                    f"Dados extraídos não encontrados: {payload.upload_id}. "
                    "Se o servidor reiniciou, reenvie o PDF ou garanta que o orçamento "
                    "está salvo no Firestore com o mesmo uploadId."
                ),
            )

        expected_user = upload_data.get("userId")
        _assert_upload_access(user_id, expected_user)

        tables_text = _build_tables_text_for_ai(upload_data)
        if not tables_text.strip():
            raise HTTPException(
                status_code=400,
                detail="Nenhuma tabela ou item encontrado para análise",
            )
        
        # Payload para IA
        system_message = """Você é um especialista em análise de orçamentos e planilhas de construção civil.
Analise os dados extraídos de um PDF de orçamento e:
1. Identifique a estrutura (quais colunas representam descrição, quantidade, unidade, valor)
2. Extraia e valide os items orçamentários
3. Filtre e descarte linhas irrelevantes (subtotais, totalizações, cabeçalhos duplicados, linhas em branco)
4. Retorne apenas JSON estruturado com os dados validados

Estrutura esperada de cada item:
- descricao: string com descrição do serviço/material
- quantidade: número (pode ter decimais)
- unidade: string (un, m, m2, m3, kg, t, l, h, dia, etc)
- valor_unitario: número em reais
- valor_total: quantidade * valor_unitario

Regras:
- Descartar linhas onde descricao contém: "total", "subtotal", "suma", "resumen"
- Descartar linhas que parecem ser títulos ou seções
- Converter valores de string para número (remover R$, converter vírgula em ponto)
- Manter apenas items que tenham pelo menos: descrição e um valor numérico"""
        
        user_message = {
            "tarefa": "analisar_orcamento",
            "dados_extraidos": tables_text,
            "requisitos": {
                "validar_estrutura": True,
                "filtrar_linhas_invalidas": True,
                "identificar_colunas": True,
                "extrair_items": True
            },
            "formato_retorno": {
                "structure": {
                    "coluna_descricao": 0,
                    "coluna_quantidade": 1,
                    "coluna_unidade": 2,
                    "coluna_valor_unitario": 3,
                    "confianca": 0.95
                },
                "items": [
                    {
                        "id": "item_1",
                        "descricao": "descrição do item",
                        "quantidade": 10.0,
                        "unidade": "un",
                        "valor_unitario": 100.50,
                        "valor_total": 1005.0,
                        "validado": True,
                        "notas": ""
                    }
                ],
                "resumo": {
                    "total_items": 0,
                    "valor_total": 0.0,
                    "confianca_analise": 0.95,
                    "avisos": []
                }
            }
        }

        gemini_request_body = {
            "contents": [
                {
                    "parts": [
                        {"text": system_message},
                        {"text": json.dumps(user_message, ensure_ascii=False)}
                    ]
                }
            ],
            "generationConfig": {
                "temperature": 0.2,  # Baixa temperatura para respostas mais determinísticas
                "topK": 40,
                "topP": 0.95,
                "maxOutputTokens": 4000,
            }
        }

        errors = []
        content = ""
        provider_used = ""

        if OLLAMA_ENABLED:
            try:
                content, provider_used = await _call_ollama_generate_content(
                    system_message=system_message,
                    user_message=user_message,
                    timeout_seconds=min(AI_PROVIDER_TIMEOUT_SECONDS, OLLAMA_TIMEOUT_SECONDS),
                )
            except AIProviderError as exc:
                errors.append(f"{exc.provider}: {exc.details}")

        if not content and GEMINI_API_KEY:
            try:
                content, provider_used = await _call_gemini_generate_content(
                    gemini_request_body,
                    timeout_seconds=AI_PROVIDER_TIMEOUT_SECONDS,
                )
            except AIProviderError as exc:
                errors.append(f"{exc.provider}: {exc.details}")

        if not content and OPENROUTER_API_KEY and ENABLE_MULTI_PROVIDER_CHAIN:
            try:
                content, provider_used = await _call_openai_compatible_generate_content(
                    provider="openrouter",
                    base_url="https://openrouter.ai/api/v1",
                    api_key=OPENROUTER_API_KEY,
                    model=OPENROUTER_MODEL,
                    system_message=system_message,
                    user_message=user_message,
                    timeout_seconds=AI_PROVIDER_TIMEOUT_SECONDS,
                )
            except AIProviderError as exc:
                errors.append(f"{exc.provider}: {exc.details}")

        if not content and GROQ_API_KEY and ENABLE_MULTI_PROVIDER_CHAIN:
            try:
                content, provider_used = await _call_openai_compatible_generate_content(
                    provider="groq",
                    base_url="https://api.groq.com/openai/v1",
                    api_key=GROQ_API_KEY,
                    model=GROQ_MODEL,
                    system_message=system_message,
                    user_message=user_message,
                    timeout_seconds=AI_PROVIDER_TIMEOUT_SECONDS,
                )
            except AIProviderError as exc:
                errors.append(f"{exc.provider}: {exc.details}")

        if not content and OPENAI_API_KEY and ENABLE_MULTI_PROVIDER_CHAIN:
            try:
                content, provider_used = await _call_openai_compatible_generate_content(
                    provider="openai",
                    base_url="https://api.openai.com/v1",
                    api_key=OPENAI_API_KEY,
                    model=OPENAI_MODEL,
                    system_message=system_message,
                    user_message=user_message,
                    timeout_seconds=AI_PROVIDER_TIMEOUT_SECONDS,
                )
            except AIProviderError as exc:
                errors.append(f"{exc.provider}: {exc.details}")

        if IS_VERCEL and not ENABLE_MULTI_PROVIDER_CHAIN and not content and errors:
            errors.append("serverless: fallback local aplicado para reduzir timeout")

        if content:
            try:
                analysis = json.loads(_clean_json_text(content))
            except json.JSONDecodeError:
                logger.warning("⚠️ IA retornou JSON inválido; aplicando fallback local")
                errors.append("parser: resposta de IA inválida, fallback local aplicado")
                analysis = _local_budget_analysis(upload_data)
                provider_used = "local:fallback"
        else:
            analysis = _local_budget_analysis(upload_data)
            provider_used = "local:fallback"
        
        # Validar estrutura
        items = analysis.get("items", [])
        summary = analysis.get("resumo", {})
        structure = analysis.get("structure", {})
        
        # Enriquecer dados
        if not summary.get("valor_total"):
            summary["valor_total"] = sum(item.get("valor_total", 0) for item in items)
        if not summary.get("total_items"):
            summary["total_items"] = len(items)
        
        # Salvar análise em cache (memória + disco) e Firestore
        ai_analysis_payload = {
            "analyzed_at": datetime.now().isoformat(),
            "provider": provider_used,
            "warnings": errors,
            "structure": structure,
            "items": items,
            "summary": summary,
        }
        _OFFLINE_CACHE[payload.upload_id]["ai_analysis"] = ai_analysis_payload
        _save_extracted_cache(payload.upload_id, _OFFLINE_CACHE[payload.upload_id])
        _persist_ai_analysis_to_firestore(payload.upload_id, ai_analysis_payload)

        logger.info(f"✅ Análise concluída: {len(items)} items reconhecidos")
        
        return {
            "status": "success",
            "upload_id": payload.upload_id,
            "provider": provider_used,
            "warnings": errors,
            "analysis": {
                "structure": structure,
                "items": items,
                "summary": summary,
                "confianca_geral": summary.get("confianca_analise", 0.8)
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Erro na análise com IA: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Erro ao analisar com IA: {str(e)}",
        )


@app.get("/api/ai-analysis/{upload_id}")
async def get_ai_analysis(upload_id: str):
    """Retorna análise detalhada de IA já processada para um upload."""
    upload_data = _get_upload_data_from_sources(upload_id)
    if not upload_data:
        raise HTTPException(
            status_code=404,
            detail=(
                f"❌ Upload não encontrado: {upload_id}. "
                "Esse id pode ter expirado do cache local. Reenvie o PDF se necessário."
            ),
        )

    ai_analysis = upload_data.get("ai_analysis")
    if not ai_analysis:
        raise HTTPException(
            status_code=404,
            detail="❌ Análise de IA ainda não foi gerada para este upload",
        )

    return {
        "status": "success",
        "upload_id": upload_id,
        "analysis": {
            "structure": ai_analysis.get("structure", {}),
            "items": ai_analysis.get("items", []),
            "summary": ai_analysis.get("summary", {}),
            "confianca_geral": ai_analysis.get("summary", {}).get("confianca_analise", 0.8),
        },
        "provider": ai_analysis.get("provider", "desconhecido"),
        "warnings": ai_analysis.get("warnings", []),
        "analyzed_at": ai_analysis.get("analyzed_at"),
    }

def _is_executive_budget_item(item: Dict[str, Any]) -> bool:
    """Itens executivos para Curva ABC: apenas tipo 'item', sem totais de grupo."""
    tipo = str(
        item.get("tipo_linha") or item.get("tipo") or "item"
    ).strip().lower()
    desc = str(item.get("descricao") or item.get("description") or "").lower()
    if tipo in ("grupo", "composicao", "composição", "insumo", "subitem", "titulo", "título"):
        return False
    if "total do grupo" in desc or desc.startswith("total "):
        return False
    return tipo == "item"


def _apply_abc_classification(executives: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Aplica Curva ABC (Pareto 80/95) in-place em itens executivos já filtrados."""
    for item in executives:
        line_total = _item_line_total(item)
        if line_total > 0:
            item["valor_total"] = line_total
            item["lineTotal"] = line_total

    executives.sort(
        key=lambda row: (
            -_item_line_total(row),
            str(row.get("codigo") or row.get("id") or ""),
        ),
    )

    total_value = sum(_item_line_total(row) for row in executives)
    accumulated = 0.0

    for item in executives:
        line_total = _item_line_total(item)
        pct_before = (accumulated / total_value * 100) if total_value > 0 else 0
        accumulated += line_total
        item["accumulated_percentage"] = round(
            (accumulated / total_value * 100) if total_value > 0 else 0,
            1,
        )
        item["individual_percentage"] = round(
            (line_total / total_value * 100) if total_value > 0 else 0,
            1,
        )
        if pct_before < 80:
            item["classification"] = "A"
        elif pct_before < 95:
            item["classification"] = "B"
        else:
            item["classification"] = "C"

    value_a = sum(
        _item_line_total(i) for i in executives if i.get("classification") == "A"
    )
    value_b = sum(
        _item_line_total(i) for i in executives if i.get("classification") == "B"
    )
    value_c = sum(
        _item_line_total(i) for i in executives if i.get("classification") == "C"
    )

    return {
        "total": total_value,
        "countA": sum(1 for i in executives if i.get("classification") == "A"),
        "countB": sum(1 for i in executives if i.get("classification") == "B"),
        "countC": sum(1 for i in executives if i.get("classification") == "C"),
        "valueA": value_a,
        "valueB": value_b,
        "valueC": value_c,
        "percentA": round((value_a / total_value * 100), 1) if total_value > 0 else 0,
        "percentB": round((value_b / total_value * 100), 1) if total_value > 0 else 0,
        "percentC": round((value_c / total_value * 100), 1) if total_value > 0 else 0,
    }


def _classify_abc_items(
    items: List[Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Filtra itens executivos, normaliza valor_total e aplica Curva ABC (Pareto 80/95)."""
    executives: List[Dict[str, Any]] = []
    for raw in items:
        if not isinstance(raw, dict) or not _is_executive_budget_item(raw):
            continue
        if _item_line_total(raw) <= 0:
            continue
        executives.append(dict(raw))

    summary = _apply_abc_classification(executives)
    return executives, summary


def _item_line_total(item: Dict[str, Any]) -> float:
    explicit = _coerce_number(item.get("lineTotal") or item.get("line_total") or 0)
    if explicit > 0:
        return explicit
    total = _coerce_number(
        item.get("valor_total") or item.get("totalValue") or item.get("lineTotal") or 0
    )
    if total > 0:
        return total
    qty = _coerce_number(
        item.get("quantidade") or item.get("quantity") or item.get("qty") or 0
    )
    unit = _coerce_number(
        item.get("valor_unitario")
        or item.get("unitValue")
        or item.get("unitPrice")
        or 0
    )
    bdi = _coerce_bdi(item.get("bdi"))
    return qty * unit * (1 + bdi / 100.0)


def _enrich_items_with_abc(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Recalcula totais e classificação A/B/C (Pareto) quando ausentes no Firestore."""
    enriched: List[Dict[str, Any]] = [dict(item) for item in items]
    executives = [item for item in enriched if _is_executive_budget_item(item)]
    _apply_abc_classification(executives)
    return enriched


def _detect_abc_class_filter(message: str) -> str | None:
    msg = message.lower()
    for cls in ("a", "b", "c"):
        if re.search(
            rf"(?:curva|classe|classifica[cç][aã]o|class)\s+{cls}\b|"
            rf"\bcurva\s+{cls}\b",
            msg,
        ):
            return cls.upper()
    return None


def _filter_items_for_message(
    items: List[Dict[str, Any]], message: str
) -> Tuple[List[Dict[str, Any]], str | None]:
    abc_cls = _detect_abc_class_filter(message)
    if not abc_cls:
        return items, None

    filtered = [
        item
        for item in items
        if _is_executive_budget_item(item)
        and str(item.get("classification") or "").upper() == abc_cls
    ]
    return filtered, abc_cls


def _infer_chart_value_label(message: str) -> str:
    msg = message.lower()
    if any(k in msg for k in ("quantidade", "qtd", "volume", "qtde")):
        return "quantidade"
    if any(k in msg for k in ("percentual", "percent", "porcentagem", "%")):
        return "percentual"
    return "valor"


def _rebuild_chart_from_items(
    items: List[Dict[str, Any]],
    title: str,
    *,
    chart_type: str = "horizontal_bar",
    value_label: str = "valor",
    limit: int = 15,
) -> Dict[str, Any]:
    rows: List[Dict[str, Any]] = []
    for item in items:
        if not _is_executive_budget_item(item):
            continue
        desc = str(item.get("descricao") or item.get("description") or "Item").strip()
        code = str(item.get("codigo") or item.get("code") or "").strip()
        label = f"{code} — {desc}" if code else desc
        if value_label == "quantidade":
            metric = _coerce_number(
                item.get("quantidade") or item.get("quantity") or item.get("qty") or 0
            )
        elif value_label == "percentual":
            metric = _coerce_number(
                item.get("individual_percentage")
                or item.get("percentual")
                or 0
            )
        else:
            metric = _item_line_total(item)

        if metric <= 0:
            continue
        rows.append({"name": label[:55], "value": float(metric)})

    rows.sort(key=lambda row: row["value"], reverse=True)
    top = rows[:limit]

    return {
        "title": title,
        "chart_type": chart_type,
        "value_label": value_label,
        "data": top or [{"name": "Sem dados", "value": 0}],
    }


def _sanitize_ai_chart(
    chart: Dict[str, Any] | None,
    source_items: List[Dict[str, Any]],
    message: str,
    *,
    default_title: str = "Gráfico do orçamento",
) -> Dict[str, Any] | None:
    if not source_items:
        return chart

    value_label = _infer_chart_value_label(message)
    executives = [i for i in source_items if _is_executive_budget_item(i)]
    if not executives:
        return chart

    max_source = max(
        (
            _coerce_number(
                i.get("quantidade") if value_label == "quantidade" else _item_line_total(i)
            )
            for i in executives
        ),
        default=0,
    )

    if not chart or not isinstance(chart.get("data"), list):
        if any(k in message.lower() for k in ("gráfico", "grafico", "chart", "barras", "pizza")):
            return _rebuild_chart_from_items(
                source_items,
                default_title,
                value_label=value_label,
            )
        return chart

    data = chart.get("data") or []
    max_chart = max(
        (_coerce_number(row.get("value") or row.get("valor") or 0) for row in data if isinstance(row, dict)),
        default=0,
    )
    chart_label = str(chart.get("value_label") or "valor").lower()

    wrong_percent_axis = chart_label == "percentual" and value_label == "valor"
    wrong_tiny_values = (
        value_label == "valor"
        and max_chart > 0
        and max_chart < 1000
        and max_source > 10_000
    )
    empty_or_zero = max_chart <= 0 and max_source > 0
    suspicious_count_scale = (
        value_label == "valor"
        and max_chart <= 100
        and max_source > 50_000
        and len(data) > 0
    )

    if wrong_percent_axis or wrong_tiny_values or empty_or_zero or suspicious_count_scale:
        return _rebuild_chart_from_items(
            source_items,
            str(chart.get("title") or default_title),
            chart_type=str(chart.get("chart_type") or "horizontal_bar"),
            value_label=value_label,
        )

    normalized = []
    for row in data[:15]:
        if not isinstance(row, dict):
            continue
        normalized.append(
            {
                "name": str(row.get("name") or row.get("label") or "—")[:55],
                "value": _coerce_number(row.get("value") or row.get("valor") or 0),
            }
        )
    if not normalized:
        return _rebuild_chart_from_items(
            source_items, str(chart.get("title") or default_title), value_label=value_label
        )

    chart["data"] = normalized
    chart["value_label"] = value_label
    if not chart.get("chart_type"):
        chart["chart_type"] = "horizontal_bar"
    return chart


class ReportChatMessage(BaseModel):
    role: str = Field(..., pattern="^(user|assistant)$")
    content: str = Field(..., min_length=1, max_length=8000)


class AiReportChatRequest(BaseModel):
    """Suporta histórico multi-turno (messages) ou pergunta única legada (message)."""
    messages: List[ReportChatMessage] = Field(default_factory=list)
    message: str = Field(default="", max_length=2000)
    items: List[Dict[str, Any]] = Field(default_factory=list)
    filename: str = Field(default="orcamento")
    upload_id: str = Field(default="")


def _resolve_report_conversation(payload: AiReportChatRequest) -> Tuple[List[Dict[str, str]], str]:
    conv: List[Dict[str, str]] = []
    for msg in payload.messages or []:
        role = str(msg.role).lower().strip()
        content = str(msg.content).strip()
        if role in ("user", "assistant") and content:
            conv.append({"role": role, "content": content})
    if conv:
        last_user = ""
        for msg in reversed(conv):
            if msg["role"] == "user":
                last_user = msg["content"]
                break
        return conv, last_user
    single = str(payload.message or "").strip()
    if len(single) < 3:
        raise HTTPException(status_code=400, detail="Informe uma mensagem ou histórico messages[]")
    return [{"role": "user", "content": single}], single


def _encode_attachment(filename: str, mime_type: str, text_content: str) -> Dict[str, str]:
    return {
        "filename": filename,
        "mime_type": mime_type,
        "content_base64": base64.b64encode(text_content.encode("utf-8")).decode("ascii"),
    }


def _encode_attachment_bytes(filename: str, mime_type: str, raw: bytes) -> Dict[str, str]:
    return {
        "filename": filename,
        "mime_type": mime_type,
        "content_base64": base64.b64encode(raw).decode("ascii"),
    }


def _safe_attachment_stem(upload_label: str) -> str:
    """Remove extensões (.pdf, .md) do nome do arquivo para anexos."""
    raw = str(upload_label or "orcamento").strip()
    stem = Path(raw).stem
    stem = re.sub(r"[^\w\-]+", "_", stem).strip("_")
    return stem[:40] or "orcamento"


def _format_brl(value: float) -> str:
    return (
        f"R$ {value:,.2f}"
        .replace(",", "\u00a4")
        .replace(".", ",")
        .replace("\u00a4", ".")
    )


def _wants_markdown_table(message: str) -> bool:
    msg = message.lower()
    return any(
        k in msg
        for k in (
            "tabela",
            "table",
            "liste",
            "listar",
            "listagem",
            "ranking",
            "top ",
            "maiores",
            "mais caro",
            "mais caros",
        )
    )


def _extract_table_limit(message: str, default: int = 10) -> int:
    msg = message.lower()
    patterns = [
        r"(\d+)\s*(?:itens|item|maiores|primeiros|principais)",
        r"top\s*(\d+)",
        r"(\d+)\s*mais\s*car",
    ]
    for pattern in patterns:
        match = re.search(pattern, msg)
        if match:
            return min(max(int(match.group(1)), 1), 50)
    return default


def _build_markdown_table_from_rows(
    rows: List[Dict[str, Any]],
    *,
    title: str,
    limit: int,
) -> str:
    """Gera tabela GFM (pipe) para renderização no chat."""
    top = rows[:limit]
    if not top:
        return "Nenhum item encontrado para montar a tabela."

    lines = [
        f"### {title}",
        "",
        "| # | Descrição | Qtd. | Unid. | Valor total |",
        "|---:|---|---:|---|---:|",
    ]
    for idx, row in enumerate(top, 1):
        desc = str(row.get("descricao") or row.get("description") or "—").replace("|", "/")
        qty = _coerce_number(row.get("quantidade") or row.get("quantity") or 0)
        unit = str(row.get("unidade") or row.get("unit") or "—")
        val = _coerce_number(
            row.get("valor_total")
            or row.get("metric")
            or row.get("valor_total_calculado")
            or _item_line_total(row)
        )
        lines.append(
            f"| {idx} | {desc[:80]} | {qty:,.2f} | {unit} | {_format_brl(val)} |"
        )
    return "\n".join(lines)


def _ensure_reply_has_markdown_table(
    reply: str,
    items: List[Dict[str, Any]],
    message: str,
) -> str:
    """Garante tabela Markdown quando o usuário pediu tabela e a IA devolveu só lista."""
    if not _wants_markdown_table(message):
        return reply

    if "|" in reply and re.search(r"\|[\s\-:]+\|", reply):
        return reply

    limit = _extract_table_limit(message, default=10)
    sorted_items = sorted(
        [i for i in items if _is_executive_budget_item(i)],
        key=lambda i: _item_line_total(i),
        reverse=True,
    )
    table_md = _build_markdown_table_from_rows(
        [
            {
                "descricao": str(i.get("descricao") or i.get("description") or ""),
                "quantidade": i.get("quantidade") or i.get("quantity"),
                "unidade": i.get("unidade") or i.get("unit"),
                "valor_total": _item_line_total(i),
            }
            for i in sorted_items
        ],
        title=f"Top {limit} itens por valor total",
        limit=limit,
    )

    intro = reply.strip()
    if intro.startswith("## Resposta (análise local)"):
        return f"{table_md}\n\n---\n\n{intro}"
    if intro:
        return f"{table_md}\n\n{intro}"
    return table_md


def _build_report_attachments(
    reply: str,
    table: Dict[str, Any] | None,
    chart: Dict[str, Any] | None,
    upload_label: str,
) -> List[Dict[str, str]]:
    attachments: List[Dict[str, str]] = []
    safe_label = _safe_attachment_stem(upload_label)

    has_pdf_content = bool(
        (reply and reply.strip())
        or (chart and isinstance(chart.get("data"), list) and chart.get("data"))
        or (table and isinstance(table.get("rows"), list) and table.get("rows"))
    )
    if has_pdf_content:
        doc_title = f"Análise - {upload_label}"
        body = (reply or "").strip()
        try:
            pdf_bytes = build_analysis_pdf_bytes(
                doc_title,
                body,
                chart=chart if isinstance(chart, dict) else None,
                table=table if isinstance(table, dict) else None,
            )
            attachments.append(
                _encode_attachment_bytes(
                    f"analise_{safe_label}.pdf",
                    "application/pdf",
                    pdf_bytes,
                )
            )
        except Exception as exc:
            logger.warning("Falha ao gerar PDF da análise, usando Markdown: %s", exc)
            md = f"# {doc_title}\n\n{body}\n"
            attachments.append(
                _encode_attachment(f"analise_{safe_label}.md", "text/markdown", md)
            )

    if table and isinstance(table.get("rows"), list):
        headers = table.get("headers") or []
        rows = table.get("rows") or []
        lines = []
        if headers:
            lines.append(";".join(str(h) for h in headers))
        for row in rows[:500]:
            if isinstance(row, list):
                lines.append(";".join(str(c) for c in row))
        if lines:
            attachments.append(
                _encode_attachment(
                    f"tabela_{safe_label}.csv",
                    "text/csv",
                    "\n".join(lines),
                )
            )

    if chart and isinstance(chart.get("data"), list):
        chart_lines = ["item;valor"]
        for point in chart["data"][:50]:
            if isinstance(point, dict):
                chart_lines.append(
                    f"{point.get('name', '')};{point.get('value', 0)}"
                )
        attachments.append(
            _encode_attachment(
                f"grafico_{safe_label}.csv",
                "text/csv",
                "\n".join(chart_lines),
            )
        )

    return attachments


def _local_report_response(
    message: str,
    items: List[Dict[str, Any]],
    *,
    abc_filter: str | None = None,
) -> Dict[str, Any]:
    """Fallback local quando IA indisponível."""
    msg_lower = message.lower()
    value_label = _infer_chart_value_label(message)
    use_value = value_label == "valor"

    rows_data = []
    for item in items[:200]:
        desc = str(item.get("descricao") or item.get("description") or "Item")[:60]
        qty = _coerce_number(
            item.get("quantidade") or item.get("quantity") or item.get("qty") or 0
        )
        val = _item_line_total(item)
        if value_label == "percentual":
            metric = _coerce_number(item.get("individual_percentage") or 0)
        elif use_value:
            metric = val
        else:
            metric = qty
        if metric <= 0:
            continue
        rows_data.append(
            {
                "descricao": desc,
                "quantidade": qty,
                "unidade": str(item.get("unidade") or item.get("unit") or "un"),
                "valor_total": val,
                "metric": metric,
            }
        )

    rows_data.sort(key=lambda r: r["metric"], reverse=True)
    limit = _extract_table_limit(message, default=10)
    top = rows_data[:limit]

    metric_label = (
        "valor total (R$)"
        if value_label == "valor"
        else "percentual (%)"
        if value_label == "percentual"
        else "quantidade"
    )
    chart_title = (
        f"Itens da Curva {abc_filter} do Orçamento"
        if abc_filter
        else f"Itens por {metric_label}"
    )
    chart_data = [
        {"name": r["descricao"][:40], "value": float(r["metric"])} for r in top
    ]

    if _wants_markdown_table(message):
        title = f"Top {limit} itens por {metric_label}"
        if abc_filter:
            title = f"Curva {abc_filter} - {title}"
        reply = _build_markdown_table_from_rows(top, title=title, limit=limit)
    else:
        lines = [
            "## Resposta (análise local)\n",
            f"Pedido: *{message[:200]}*\n",
        ]
        if abc_filter:
            lines.append(
                f"Filtro aplicado: **Curva {abc_filter}** ({len(items)} itens nesta classe).\n"
            )
        lines.append(f"Top **{len(top)}** itens por **{metric_label}**:\n")
        for i, r in enumerate(top, 1):
            lines.append(
                f"{i}. **{r['descricao']}** - qtd: {r['quantidade']:,.2f}, "
                f"valor: {_format_brl(r['valor_total'])}"
            )
        reply = "\n".join(lines)
    table = {
        "title": f"Top itens por {metric_label}",
        "headers": ["#", "Descrição", "Quantidade", "Valor total (R$)"],
        "rows": [
            [i, r["descricao"], r["quantidade"], r["valor_total"]]
            for i, r in enumerate(top, 1)
        ],
    }
    chart = {
        "title": chart_title,
        "chart_type": "horizontal_bar",
        "value_label": value_label,
        "data": chart_data or [{"name": "Sem dados", "value": 0}],
    }

    wants_chart = any(
        k in msg_lower for k in ("gráfico", "grafico", "chart", "pizza", "barras")
    )

    return {
        "reply": reply,
        "response_type": "mixed" if wants_chart else "text",
        "chart": chart if wants_chart else None,
        "table": table,
    }


@app.post("/api/ai-report-chat")
async def ai_report_chat(
    payload: AiReportChatRequest,
    user_id: str = Depends(get_current_user_id),
):
    """
    Assistente ChatGPT-style: histórico multi-turno, Markdown nas respostas e gráfico opcional.
    """
    conversation, last_user_message = _resolve_report_conversation(payload)

    items = payload.items or []
    if not items:
        raise HTTPException(status_code=400, detail="Nenhum item enviado para análise")

    enriched_items = _enrich_items_with_abc(items)
    working_items, abc_filter = _filter_items_for_message(
        enriched_items, last_user_message
    )
    if abc_filter and not working_items:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Nenhum item encontrado na Curva {abc_filter}. "
                "Valide o orçamento na aba Validação para recalcular a classificação ABC."
            ),
        )

    budget_items: List[Dict[str, Any]] = []
    for idx, item in enumerate(working_items[:300]):
        budget_items.append(
            {
                "i": idx + 1,
                "item": str(item.get("item") or ""),
                "codigo": str(item.get("codigo") or item.get("code") or ""),
                "descricao": str(item.get("descricao") or item.get("description") or ""),
                "tipo": str(item.get("tipo") or "item"),
                "unidade": str(item.get("unidade") or item.get("unit") or "un"),
                "quantidade": _coerce_number(
                    item.get("quantidade") or item.get("quantity") or item.get("qty")
                ),
                "valor_unitario": _coerce_number(
                    item.get("valor_unitario")
                    or item.get("unitValue")
                    or item.get("unitPrice")
                ),
                "bdi": _coerce_bdi(item.get("bdi")),
                "valor_total": _coerce_number(
                    item.get("valor_total") or item.get("totalValue") or item.get("lineTotal")
                ),
                "valor_total_calculado": _item_line_total(item),
                "classificacao": str(item.get("classification") or "").upper()[:1],
                "percentual_individual": round(
                    _coerce_number(item.get("individual_percentage") or 0), 4
                ),
                "percentual_acumulado": round(
                    _coerce_number(item.get("accumulated_percentage") or 0), 4
                ),
            }
        )

    budget_context = {
        "arquivo": payload.filename,
        "upload_id": payload.upload_id,
        "total_itens": len(budget_items),
        "filtro_curva_abc_aplicado": abc_filter,
        "itens": budget_items,
    }

    provider_used = "local:fallback"
    errors: List[str] = []
    parsed: Dict[str, Any] | None = None

    try:
        parsed, provider_used = await generate_report_chat(conversation, budget_context)
    except OpenAIServiceError as exc:
        errors.append(str(exc))
    except Exception as exc:
        logger.exception("Erro generate_report_chat")
        errors.append(str(exc))

    if not parsed or not str(parsed.get("reply") or "").strip():
        parsed = _local_report_response(
            last_user_message, working_items, abc_filter=abc_filter
        )
        provider_used = "local:fallback"

    reply = str(parsed.get("reply") or "").strip()
    if not reply:
        reply = "Não foi possível gerar uma análise para este pedido."

    reply = _ensure_reply_has_markdown_table(reply, working_items, last_user_message)

    chart: Dict[str, Any] | None = parsed.get("chart") if isinstance(parsed.get("chart"), dict) else None
    if chart and not chart.get("chart_type"):
        raw_type = str(chart.get("type") or "bar").lower()
        chart["chart_type"] = "pie" if raw_type == "pie" else "horizontal_bar"

    chart_title_default = (
        f"Itens da Curva {abc_filter} do Orçamento"
        if abc_filter
        else "Gráfico do orçamento"
    )
    chart = _sanitize_ai_chart(
        chart,
        working_items,
        last_user_message,
        default_title=chart_title_default,
    )

    upload_label = payload.filename or payload.upload_id or "orcamento"
    report_table = parsed.get("table") if isinstance(parsed.get("table"), dict) else None
    attachments = _build_report_attachments(reply, report_table, chart, upload_label)

    return {
        "status": "success",
        "provider": provider_used,
        "warnings": errors,
        "reply": reply,
        "response_type": str(parsed.get("response_type") or ("mixed" if chart else "text")),
        "chart": chart,
        "table": report_table,
        "attachments": attachments,
    }


@app.get("/api/orcamentos/{upload_id}/pdf")
async def get_orcamento_pdf(
    upload_id: str,
    user_id: str = Depends(get_current_user_id),
):
    """Retorna o PDF original do upload (disco local ou Firebase Storage)."""
    upload_id = _validate_upload_id(upload_id)
    meta = _load_upload_meta(upload_id)
    owner = meta.get("userId")
    _assert_upload_access(user_id, owner)

    file_path = UPLOAD_FOLDER / f"{upload_id}.pdf"
    if not file_path.is_file():
        try:
            pdf_bytes = await _resolve_pdf_bytes_for_upload(upload_id, user_id)
            file_path.write_bytes(pdf_bytes)
        except HTTPException:
            raise HTTPException(
                status_code=404,
                detail="PDF não encontrado no servidor. Reenvie o arquivo se necessário.",
            ) from None

    upload_data = _get_upload_data_from_sources(upload_id) or {}
    filename = str(
        meta.get("filename")
        or upload_data.get("filename")
        or f"{upload_id}.pdf"
    )
    return FileResponse(
        path=str(file_path),
        media_type="application/pdf",
        filename=filename,
    )


# ============== FIRESTORE OPERATIONS ==============

@app.get("/api/orcamentos")
async def list_orcamentos(user_id: str = Depends(get_current_user_id)):
    """
    Listar todos os orçamentos salvos no Firestore + cache offline
    
    Returns:
        {
            "status": "success",
            "count": 5,
            "orcamentos": [...]
        }
    """
    try:
        orcamentos = OrcamentoFirestore.list_all_orcamentos(user_id=user_id)
        return {
            "status": "success",
            "count": len(orcamentos),
            "orcamentos": orcamentos,
        }
    except Exception as e:
        logger.error(f"❌ Erro ao listar orçamentos: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Erro ao listar orçamentos: {str(e)}",
        )

@app.get("/api/orcamentos/{upload_id}")
async def get_orcamento(
    upload_id: str,
    user_id: str = Depends(get_current_user_id),
):
    """
    Recuperar orçamento (cache offline, disco ou Firestore).
    """
    try:
        upload_id = _validate_upload_id(upload_id)
        upload_data = _get_upload_data_from_sources(upload_id)
        meta = _load_upload_meta(upload_id)
        owner = meta.get("userId") or (upload_data or {}).get("userId")
        _assert_upload_access(user_id, owner)

        if not upload_data:
            raise HTTPException(
                status_code=404,
                detail=f"❌ Orçamento não encontrado: {upload_id}",
            )

        items_data = upload_data.get("itemsData") or {}
        if not isinstance(items_data, dict):
            items_data = {}

        items = upload_data.get("items") or items_data.get("items") or []
        hierarchical = (
            items_data.get("hierarchical_items")
            or upload_data.get("hierarchical_items")
            or []
        )
        resumo = items_data.get("resumo") or upload_data.get("resumo") or {}

        orcamento = {
            "uploadId": upload_id,
            "userId": upload_data.get("userId") or owner,
            "filename": upload_data.get("filename") or meta.get("filename"),
            "items": items,
            "itemsData": {
                "items": items,
                "hierarchical_items": hierarchical,
                "resumo": resumo,
            },
            "hierarchical_items": hierarchical,
            "tables": upload_data.get("tables") or [],
            "ia_metadata": upload_data.get("ia_metadata") or upload_data.get("iaMetadata"),
            "iaMetadata": upload_data.get("ia_metadata") or upload_data.get("iaMetadata"),
            "status": upload_data.get("status", "completed"),
            "resumo": resumo,
            "extractedAt": upload_data.get("extractedAt"),
            "uploadedAt": upload_data.get("uploadedAt"),
        }

        return {
            "status": "success",
            "orcamento": orcamento,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Erro ao recuperar orçamento: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Erro ao recuperar orçamento: {str(e)}",
        )


@app.post("/api/orcamentos/{upload_id}/review-items")
async def save_reviewed_items(upload_id: str, payload: SaveReviewedItemsRequest):
    """Persiste itens revisados da aba de análise detalhada."""
    try:
        if not payload.items:
            raise HTTPException(
                status_code=400,
                detail="❌ Nenhum item revisado enviado",
            )

        upload_data = _get_upload_data_from_sources(upload_id)
        if not upload_data:
            raise HTTPException(
                status_code=404,
                detail=f"❌ Orçamento não encontrado: {upload_id}",
            )

        normalized_items = []
        for index, item in enumerate(payload.items, start=1):
            quantidade = float(item.quantidade or 0)
            valor_unitario = float(item.valor_unitario or 0)
            valor_total = (
                float(item.valor_total)
                if item.valor_total is not None
                else quantidade * valor_unitario
            )

            normalized_items.append(
                {
                    "id": item.id or f"item_{index}",
                    "descricao": item.descricao,
                    "quantidade": quantidade,
                    "unidade": item.unidade,
                    "valor_unitario": valor_unitario,
                    "valor_total": valor_total,
                    "validado": bool(item.validado),
                    "status": "validado" if item.validado else "pendente_validacao",
                    "notas": item.notas or "",
                    "classification": item.classification,
                    "accumulated_percentage": item.accumulated_percentage,
                }
            )

        valor_total = sum(item["valor_total"] for item in normalized_items)
        resumo = upload_data.get("resumo", {}) or {}
        resumo["total_items"] = len(normalized_items)
        resumo["valor_total"] = valor_total

        upload_data["items"] = normalized_items
        upload_data["resumo"] = resumo
        upload_data["itemsFound"] = len(normalized_items)
        upload_data["updatedAt"] = datetime.now().isoformat()

        ai_analysis = upload_data.get("ai_analysis") or {}
        if ai_analysis:
            ai_summary = ai_analysis.get("summary", {}) or {}
            ai_summary["total_items"] = len(normalized_items)
            ai_summary["valor_total"] = valor_total
            ai_analysis["items"] = normalized_items
            ai_analysis["summary"] = ai_summary
            ai_analysis["updated_at"] = datetime.now().isoformat()
            upload_data["ai_analysis"] = ai_analysis

        _OFFLINE_CACHE[upload_id] = upload_data

        firestore_orcamento = OrcamentoFirestore.get_orcamento_by_upload_id(upload_id)
        if firestore_orcamento and firestore_orcamento.get("id"):
            OrcamentoFirestore.update_orcamento(
                firestore_orcamento["id"],
                {
                    "items": normalized_items,
                    "itemsData": {
                        "items": normalized_items,
                        "resumo": resumo,
                    },
                    "status": "reviewed",
                },
            )

        return {
            "status": "success",
            "upload_id": upload_id,
            "items_saved": len(normalized_items),
            "valor_total": valor_total,
            "message": "✅ Itens revisados salvos com sucesso",
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Erro ao salvar itens revisados: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Erro ao salvar itens revisados: {str(e)}",
        )

# ============== CURVA ABC ==============
@app.get("/api/curva-abc/{upload_id}")
async def get_curva_abc(
    upload_id: str,
    user_id: str = Depends(get_current_user_id),
):
    """
    Calcula Curva ABC (análise de Pareto) para itens do orçamento
    
    Args:
        upload_id: Upload ID do orçamento
    
    Returns:
        {
            "status": "success",
            "items": [...],
            "summary": {...}
        }
    """
    try:
        # Buscar orçamento
        orcamento = OrcamentoFirestore.get_orcamento_by_upload_id(
            upload_id, user_id
        )
        
        # Se não encontrou no Firestore, tentar buscar do cache offline
        if not orcamento:
            orcamento = _OFFLINE_CACHE.get(upload_id) or _load_extracted_cache(
                upload_id
            )
            if orcamento:
                expected_user = orcamento.get("userId")
                _assert_upload_access(user_id, expected_user)
        
        if not orcamento:
            raise HTTPException(
                status_code=404,
                detail=f"❌ Orçamento não encontrado: {upload_id}",
            )
        
        # Usar items já extraídos pelo parser (se disponíveis)
        items = orcamento.get("items", [])
        
        # Se não tem items extraídos, tentar das tabelas (fallback legado)
        if not items:
            tables = orcamento.get("tables", [])
            items = []
            
            for table in tables:
                rows = table.get("rows", [])
                
                # Pular primeira linha (cabeçalho)
                for row in rows[1:]:
                    if len(row) < 4:
                        continue
                    
                    try:
                        # Tentar extrair: descrição, quantidade, unidade, valor unitário
                        descricao = str(row[0] or "").strip()
                        quantidade_str = str(row[1] or "").strip()
                        unidade = str(row[2] or "").strip()
                        valor_str = str(row[3] or "").strip()
                        
                        if not descricao or descricao.lower() in ["total", "subtotal", ""]:
                            continue
                        
                        # Limpar e converter valores numéricos
                        quantidade = float(quantidade_str.replace(",", "."))
                        valor_unitario = float(valor_str.replace("R$", "").replace(",", ".").strip())
                        valor_total = quantidade * valor_unitario
                        
                        items.append({
                            "id": f"item_{len(items) + 1}",
                            "descricao": descricao,
                            "quantidade": quantidade,
                            "unidade": unidade,
                            "valor_unitario": valor_unitario,
                            "valor_total": valor_total,
                            "status": "validado"
                        })
                    except (ValueError, IndexError, TypeError):
                        continue
        
        if not items:
            return {
                "status": "success",
                "items": [],
                "summary": {
                    "total": 0,
                    "countA": 0,
                    "countB": 0,
                    "countC": 0,
                    "valueA": 0,
                    "valueB": 0,
                    "valueC": 0,
                    "percentA": 0,
                    "percentB": 0,
                    "percentC": 0
                }
            }

        classified_items, summary = _classify_abc_items(items)

        return {
            "status": "success",
            "items": classified_items,
            "summary": summary
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Erro ao calcular Curva ABC: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Erro ao calcular Curva ABC: {str(e)}",
        )

def _bdi_factor(bdi_percent: float) -> float:
    return 1.0 + (bdi_percent / 100.0) if bdi_percent > 0 else 1.0


def _prepare_xlsx_export_rows(items: List[Dict]) -> Tuple[List[Dict[str, Any]], float]:
    """Normaliza itens do front, calcula valores S/BDI e C/BDI e métricas ABC."""
    prepared: List[Dict[str, Any]] = []
    for raw in items:
        if not isinstance(raw, dict):
            continue
        tipo = str(raw.get("tipo") or "item").strip().lower()
        descricao = str(raw.get("description") or raw.get("descricao") or "").strip()
        if tipo == "grupo" or "total do grupo" in descricao.lower():
            continue

        bdi = _coerce_bdi(raw.get("bdi") or raw.get("BDI"))
        qty = _coerce_number(raw.get("qty") or raw.get("quantidade"))
        unit_com_bdi = _coerce_number(
            raw.get("unitPrice") or raw.get("valor_unitario") or raw.get("unitValue")
        )
        total_com_bdi = _coerce_number(
            raw.get("lineTotal")
            or raw.get("line_total")
            or raw.get("totalValue")
            or raw.get("valor_total")
        )
        if total_com_bdi <= 0 and qty > 0 and unit_com_bdi > 0:
            total_com_bdi = qty * unit_com_bdi
        if unit_com_bdi <= 0 and qty > 0 and total_com_bdi > 0:
            unit_com_bdi = total_com_bdi / qty

        factor = _bdi_factor(bdi)
        unit_sem_bdi = unit_com_bdi / factor if factor > 0 else unit_com_bdi
        total_sem_bdi = total_com_bdi / factor if factor > 0 else total_com_bdi
        if total_sem_bdi <= 0 and qty > 0 and unit_sem_bdi > 0:
            total_sem_bdi = qty * unit_sem_bdi

        prepared.append(
            {
                "code": str(raw.get("code") or raw.get("codigo") or "").strip(),
                "description": descricao,
                "bdi": bdi,
                "unit": str(raw.get("unit") or raw.get("unidade") or "").strip(),
                "qty": qty,
                "unit_sem_bdi": unit_sem_bdi,
                "unit_com_bdi": unit_com_bdi,
                "total_sem_bdi": total_sem_bdi,
                "total_com_bdi": total_com_bdi,
                "classification": str(raw.get("classification") or raw.get("class") or "").strip().upper(),
                "accumulated_percentage": raw.get("accumulated_percentage"),
            }
        )

    prepared.sort(key=lambda row: row["total_com_bdi"], reverse=True)
    total_geral = sum(row["total_com_bdi"] for row in prepared)

    accumulated = 0.0
    for row in prepared:
        percent = (row["total_com_bdi"] / total_geral * 100.0) if total_geral > 0 else 0.0
        pct_before = accumulated
        accumulated += percent

        row["percent"] = percent
        acc_front = row.get("accumulated_percentage")
        row["accumulated"] = (
            float(acc_front) if acc_front is not None and acc_front != "" else accumulated
        )

        if not row["classification"]:
            if pct_before < 80:
                row["classification"] = "A"
            elif pct_before < 95:
                row["classification"] = "B"
            else:
                row["classification"] = "C"

    return prepared, total_geral


class ExportXlsxRequest(BaseModel):
    items: List[Dict[str, Any]] = Field(default_factory=list)
    modelos_selecionados: Dict[str, bool] = Field(
        default_factory=lambda: {
            "analitico": False,
            "sintetico": False,
            "curva_abc": True,
        }
    )
    nome_projeto: str | None = None


# ============== AUDITORIA, VERSIONAMENTO E LOCKS ==============

class AuditLogRequest(BaseModel):
    item_codigo: str
    campo_alterado: str
    valor_antigo: str | float | int | None = None
    valor_novo: str | float | int | None = None
    user_name: str | None = None


class SaveBudgetVersionRequest(BaseModel):
    version_name: str = Field(..., min_length=1, max_length=200)
    items_snapshot: List[Dict[str, Any]] = Field(default_factory=list)
    created_by_name: str | None = None


class LockActionRequest(BaseModel):
    user_name: str | None = None


@app.post("/api/orcamentos/{project_id}/audit")
async def create_audit_log(
    project_id: str,
    payload: AuditLogRequest,
    request: Request,
    user_id: str = Depends(get_current_user_id),
):
    """Registra alteração granular em célula do orçamento analítico."""
    _assert_project_access(project_id, user_id)
    user_name = payload.user_name or _resolve_user_name_from_request(request)

    log_id = OrcamentoEnterpriseFirestore.save_audit_log(
        project_id=project_id,
        user_id=user_id,
        user_name=user_name,
        item_codigo=payload.item_codigo,
        campo_alterado=payload.campo_alterado,
        valor_antigo=payload.valor_antigo,
        valor_novo=payload.valor_novo,
    )
    return {"status": "success", "id": log_id}


@app.post("/api/orcamentos/{project_id}/versions")
async def save_budget_version(
    project_id: str,
    payload: SaveBudgetVersionRequest,
    request: Request,
    user_id: str = Depends(get_current_user_id),
):
    """Salva snapshot profundo do orçamento analítico como nova revisão."""
    _assert_project_access(project_id, user_id)

    if not payload.items_snapshot:
        raise HTTPException(status_code=400, detail="items_snapshot não pode estar vazio")

    created_by_name = payload.created_by_name or _resolve_user_name_from_request(request)
    version = OrcamentoEnterpriseFirestore.save_budget_version(
        project_id=project_id,
        version_name=payload.version_name.strip(),
        items_snapshot=payload.items_snapshot,
        created_by=user_id,
        created_by_name=created_by_name,
    )

    if not version:
        raise HTTPException(status_code=503, detail="Firestore indisponível")

    return {"status": "success", "version": _serialize_firestore_doc(version)}


@app.get("/api/orcamentos/{project_id}/versions")
async def list_budget_versions(
    project_id: str,
    user_id: str = Depends(get_current_user_id),
):
    """Lista revisões salvas do orçamento analítico."""
    _assert_project_access(project_id, user_id)
    versions = OrcamentoEnterpriseFirestore.list_budget_versions(project_id)
    return {
        "status": "success",
        "versions": [_serialize_firestore_doc(v) for v in versions],
    }


@app.post("/api/orcamentos/{project_id}/lock/{item_id}")
async def acquire_item_lock(
    project_id: str,
    item_id: str,
    payload: LockActionRequest,
    request: Request,
    user_id: str = Depends(get_current_user_id),
):
    """Adquire lock de linha para edição concorrente."""
    _assert_project_access(project_id, user_id)
    user_name = payload.user_name or _resolve_user_name_from_request(request)

    result = OrcamentoEnterpriseFirestore.acquire_lock(
        project_id=project_id,
        item_id=item_id,
        user_id=user_id,
        user_name=user_name,
    )

    if result.get("status") == "locked":
        raise HTTPException(
            status_code=409,
            detail={
                "message": "Linha bloqueada por outro usuário",
                "locked_by": result.get("locked_by"),
                "locked_by_name": result.get("locked_by_name"),
            },
        )

    return {"status": "success", **result}


@app.post("/api/orcamentos/{project_id}/unlock/{item_id}")
async def release_item_lock(
    project_id: str,
    item_id: str,
    user_id: str = Depends(get_current_user_id),
):
    """Libera lock de linha após edição."""
    _assert_project_access(project_id, user_id)
    released = OrcamentoEnterpriseFirestore.release_lock(
        project_id=project_id,
        item_id=item_id,
        user_id=user_id,
    )

    if not released:
        raise HTTPException(status_code=403, detail="Lock pertence a outro usuário")

    return {"status": "success"}


def _serialize_firestore_doc(data: Dict[str, Any]) -> Dict[str, Any]:
    """Converte datetimes do Firestore para ISO strings."""
    serialized: Dict[str, Any] = {}
    for key, value in data.items():
        if isinstance(value, datetime):
            serialized[key] = value.isoformat()
        else:
            serialized[key] = value
    return serialized


# ============== EXPORT XLSX ==============
@app.post("/api/export-xlsx")
async def export_xlsx(
    payload: ExportXlsxRequest,
    user_id: str = Depends(get_current_user_id),
):
    """
    Exporta XLSX com abas condicionais: Analítico, Sintético e/ou Curva ABC.
    """
    try:
        items = payload.items or []
        if not items:
            raise HTTPException(status_code=400, detail="Nenhum item para exportar.")

        file_path, filename = save_export_workbook(
            items,
            payload.modelos_selecionados,
            TEMP_FOLDER,
            nome_projeto=payload.nome_projeto,
        )

        logger.info(
            "✅ XLSX gerado: %s (%s itens, modelos=%s)",
            file_path,
            len(items),
            payload.modelos_selecionados,
        )

        return FileResponse(
            path=file_path,
            filename=filename,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Erro ao exportar XLSX: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Erro ao gerar Excel: {str(e)}",
        )

# ============== SERVE FRONTEND INDEX (SPA FALLBACK) ==============
@app.get("/{path_name:path}")
async def serve_frontend(path_name: str):
    """
    Serve o frontend para rotas que não são API
    Necessário para SPA (Single Page Application)
    """
    if path_name == "api" or path_name.startswith("api/"):
        raise HTTPException(status_code=404, detail="API route not found")

    # Se é um arquivo com extensão (CSS, JS, etc), tentar servir como estático
    if "." in path_name and not path_name.startswith("api"):
        return {"error": "File not found"}
    
    # Servir index.html para rotas do frontend
    index_path = FRONTEND_DIST / "index.html"
    if index_path.exists():
        return FileResponse(index_path)
    
    return {"error": "Frontend not available"}

# ============== RUN ==============
def _is_port_in_use(port: int) -> bool:
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind(("0.0.0.0", port))
            return False
        except OSError:
            return True


def _thora_api_already_running(port: int) -> bool:
    """Verifica se a Thora API já responde na porta (evita segundo uvicorn)."""
    try:
        with httpx.Client(timeout=2.0) as client:
            response = client.get(f"http://127.0.0.1:{port}/health")
            if response.status_code != 200:
                return False
            payload = response.json()
            return payload.get("status") == "online"
    except Exception:
        return False


if __name__ == "__main__":
    import sys
    import uvicorn

    port = int(os.getenv("PORT", 8000))

    if _is_port_in_use(port):
        if _thora_api_already_running(port):
            print(f"\n[OK] Thora API já está ativa em http://localhost:{port}")
            print("   Não é necessário iniciar outro servidor.")
            print("   Para reiniciar, encerre o processo na porta e rode py main.py novamente.\n")
            sys.exit(0)

        print(f"\n[ERRO] A porta {port} já está em uso por outro processo.")
        print(f"   Se for a Thora API, acesse: http://localhost:{port}")
        print(
            f"\n   Para encerrar o processo anterior (PowerShell):\n"
            f"   Get-NetTCPConnection -LocalPort {port} | "
            f"ForEach-Object {{ Stop-Process -Id $_.OwningProcess -Force }}\n"
        )
        sys.exit(1)

    print(f"Thora API em http://localhost:{port}")
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=port,
        reload=False,
    )
