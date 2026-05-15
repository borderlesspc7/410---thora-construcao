from fastapi import FastAPI, UploadFile, File, HTTPException, Depends, Request, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from datetime import datetime
import uuid
import os
import logging
from pathlib import Path
from typing import List, Dict, Tuple, Any
import json
import re
import base64
import fitz
import camelot

import httpx
from pydantic import BaseModel, Field

from config import (
    FRONTEND_URLS,
    IS_VERCEL,
    API_TITLE,
    API_VERSION,
    API_DESCRIPTION,
    UPLOAD_FOLDER,
    MAX_FILE_SIZE,
    TEMP_FOLDER,
    BASE_DIR,
    CACHE_FOLDER,
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
from firebase_service import OrcamentoFirestore
from budget_parser import BudgetParser
from firebase_admin import auth as firebase_auth
from services.openai_service import identify_tables, process_selected_table, OpenAIServiceError
from services.ai_audit_logger import log_ai_exchange

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

async def get_current_user_id(request: Request) -> str:
    """
    Extrai user_id do Firebase token ou retorna um ID de desenvolvimento
    TODO: Implementar validação real com Firebase
    """
    # Tenta extrair do header Authorization: Bearer <token>
    anonymous_user_id = request.headers.get("X-Anonymous-User", "").strip()
    auth_header = request.headers.get("Authorization", "").strip()
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]
        try:
            # Em development, aceita qualquer token
            if ENVIRONMENT == "development":
                return token[:20] if len(token) > 20 else token
            # Em produção, validar com Firebase (TODO)
            # decoded = firebase_auth.verify_id_token(token)
            # return decoded.get("uid", "anonymous")
        except Exception as e:
            logger.warning(f"⚠️ Erro ao validar token: {e}")

    if anonymous_user_id:
        return anonymous_user_id
    
    # Fallback: gerar ID anônimo se nenhum identificador foi enviado
    if ENVIRONMENT == "development":
        return "dev-user-" + str(uuid.uuid4())[:8]
    
    return "anon-server-" + str(uuid.uuid4())[:8]


def _meta_path_for_upload_id(upload_id: str) -> Path:
    """Retorna caminho de arquivo de metadados para um upload_id"""
    return UPLOAD_FOLDER / f".meta_{upload_id}.json"


def _save_upload_meta(upload_id: str, meta_dict: Dict) -> None:
    """Salva metadados do upload em arquivo JSON"""
    try:
        meta_path = _meta_path_for_upload_id(upload_id)
        with open(meta_path, "w") as f:
            json.dump(meta_dict, f, indent=2)
        logger.debug(f"✅ Metadados salvos: {meta_path}")
    except Exception as e:
        logger.warning(f"⚠️  Erro ao salvar metadados: {e}")


def _load_upload_meta(upload_id: str) -> Dict:
    """Carrega metadados do upload de arquivo JSON"""
    try:
        meta_path = _meta_path_for_upload_id(upload_id)
        if meta_path.exists():
            with open(meta_path) as f:
                return json.load(f)
    except Exception as e:
        logger.warning(f"⚠️  Erro ao carregar metadados: {e}")
    return {}


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


def _extract_tables_from_pdf_path(file_path: Path) -> List[Dict]:
    """Extrai tabelas de um PDF no disco (mesma lógica usada em /api/extract)."""
    if not pdfplumber:
        raise RuntimeError("pdfplumber não está instalado")

    tables: List[Dict] = []
    with pdfplumber.open(file_path) as pdf:
        logger.info(f"📄 Processando PDF: {len(pdf.pages)} página(s)")

        for page_num, page in enumerate(pdf.pages):
            logger.info(f"  Página {page_num + 1}: {page.width}x{page.height}")

            page_tables = page.extract_tables()

            if not page_tables:
                logger.info("  Tentando extração com settings customizados...")
                try:
                    page_tables = page.extract_tables(
                        {
                            "vertical_strategy": "text",
                            "horizontal_strategy": "text",
                            "snap_tolerance": 5,
                            "join_tolerance": 5,
                            "edge_min_length": 3,
                        }
                    )
                except Exception as e:
                    logger.warning(f"  Erro na extração customizada: {str(e)}")
                    page_tables = []

            if not page_tables:
                logger.info("  Tentando extração de texto estruturado...")
                text = page.extract_text()
                if text:
                    lines = [line.strip() for line in text.split("\n") if line.strip()]
                    if lines:
                        page_tables = [[[line] for line in lines]]
                        logger.info(f"  Extraído {len(lines)} linhas de texto")

            if page_tables:
                for table_idx, table in enumerate(page_tables):
                    processed_rows = []
                    for row in table:
                        processed_row = []
                        for cell in row:
                            if cell is None:
                                processed_row.append("")
                            elif isinstance(cell, str):
                                cleaned = cell.strip().replace("\n", " ")
                                processed_row.append(cleaned)
                            else:
                                processed_row.append(str(cell))
                        processed_rows.append(processed_row)

                    tables.append(
                        {
                            "page": page_num + 1,
                            "table_id": f"page_{page_num}_table_{table_idx}",
                            "rows": processed_rows,
                            "original_rows": len(table),
                            "columns": len(table[0]) if table else 0,
                        }
                    )
                    logger.info(
                        f"  ✓ Tabela {table_idx + 1}: {len(processed_rows)} linhas x {len(table[0]) if table else 0} colunas"
                    )
            else:
                logger.warning(f"  ⚠️  Nenhuma tabela encontrada na página {page_num + 1}")

    return tables


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

# ============== HEALTH CHECK ==============
@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "online",
        "timestamp": datetime.now().isoformat(),
        "version": API_VERSION,
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
            },
        )
        
        logger.info(f"✅ PDF salvo: {file_path} ({len(contents) / 1024 / 1024:.2f}MB)")
        
        return {
            "status": "success",
            "upload_id": upload_id,
            "filename": file.filename,
            "size": len(contents),
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
        if expected_user and str(expected_user) != str(user_id):
            raise HTTPException(status_code=403, detail="Acesso negado")
        if not expected_user and ENVIRONMENT != "development":
            raise HTTPException(status_code=403, detail="Acesso negado")
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


import base64
import fitz
import camelot

@app.post("/api/orcamentos/detect-tables")
async def detect_orcamento_tables(
    upload_id: str = Form(...),
    user_id: str = Depends(get_current_user_id),
):
    """
    Lista candidatos a tabela orçamentária usando Camelot (leitura vetorial) e gera thumbnails com PyMuPDF.
    """
    upload_id = _validate_upload_id(upload_id)
    file_path = UPLOAD_FOLDER / f"{upload_id}.pdf"
    if not file_path.exists():
        raise HTTPException(status_code=404, detail=f"Upload não encontrado: {upload_id}")

    meta = _load_upload_meta(upload_id)
    expected_user = meta.get("userId")
    if expected_user and str(expected_user) != str(user_id):
        raise HTTPException(status_code=403, detail="Acesso negado")
    if not expected_user and ENVIRONMENT != "development":
        raise HTTPException(status_code=403, detail="Acesso negado")

    try:
        # 1. Detectar tabelas com Camelot
        # Usamos pages='1-10' para não demorar muito em PDFs gigantes, ou 'all' se preferir.
        # O prompt pediu pages='all', mas pode ser lento. Vamos usar 'all'
        tables = camelot.read_pdf(str(file_path), pages='all', flavor='lattice')
        
        options = []
        if len(tables) > 0:
            # 2. Abrir PDF com PyMuPDF para gerar thumbnails
            doc = fitz.open(str(file_path))
            
            for idx, table in enumerate(tables):
                page_num = int(table.page)
                # PyMuPDF usa índice 0-based
                page = doc[page_num - 1]
                
                # Coordenadas do Camelot: (x0, y0, x1, y1) onde y é de baixo para cima
                x0, y0, x1, y1 = table._bbox
                
                # Converter para coordenadas do PyMuPDF (y de cima para baixo)
                rect = fitz.Rect(x0, page.rect.height - y1, x1, page.rect.height - y0)
                
                # Renderizar imagem
                pix = page.get_pixmap(clip=rect, matrix=fitz.Matrix(2, 2))
                img_bytes = pix.tobytes("png")
                b64 = base64.b64encode(img_bytes).decode("utf-8")
                
                options.append({
                    "id": f"table-{idx}",
                    "pagina": page_num,
                    "coordenadas": [x0, y0, x1, y1],
                    "imagem_base64": b64,
                    # Campos legados para não quebrar o frontend imediatamente se ele ainda depender
                    "nome_tabela": f"Tabela {idx + 1} (Pág {page_num})",
                    "num_pagina": page_num,
                    "preview_texto": "Visualização disponível via imagem."
                })
            
            doc.close()
            
    except Exception as exc:
        logger.error("detect-tables: falha na identificação com Camelot: %s", exc)
        raise HTTPException(status_code=500, detail=f"Erro ao analisar PDF: {exc}") from exc

    fallback_used = False
    if not options:
        fallback_used = True
        # Se o Camelot não achar nada, retorna array vazio ou fallback
        pass

    _OFFLINE_CACHE.setdefault(upload_id, {})
    _OFFLINE_CACHE[upload_id]["table_candidates"] = options
    _OFFLINE_CACHE[upload_id]["uploadId"] = upload_id
    _OFFLINE_CACHE[upload_id]["userId"] = user_id
    _save_extracted_cache(upload_id, _OFFLINE_CACHE[upload_id])

    return {
        "status": "success",
        "upload_id": upload_id,
        "tables_found": len(options),
        "options": options,
        "mock_fallback": fallback_used,
    }


def _normalize_analytic_items(raw_items: List[Any]) -> List[Dict[str, Any]]:
    normalized: List[Dict[str, Any]] = []
    for idx, it in enumerate(raw_items):
        if not isinstance(it, dict):
            continue
        q = float(it.get("quantidade") or 0)
        vu = float(it.get("valor_unitario") or 0)
        vt = float(it.get("valor_total") or 0)
        if vt <= 0 and q and vu:
            vt = q * vu
        normalized.append(
            {
                "id": f"item_ai_{idx}",
                "descricao": str(it.get("descricao", "")).strip(),
                "quantidade": q,
                "unidade": str(it.get("unidade", "un") or "un"),
                "valor_unitario": vu,
                "valor_total": vt if vt > 0 else q * vu,
                "status": "validado",
                "origem": "openai_orcamento_analitico",
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
    file_path = UPLOAD_FOLDER / f"{upload_id}.pdf"
    if not file_path.exists():
        raise HTTPException(status_code=404, detail=f"Upload não encontrado: {upload_id}")

    meta = _load_upload_meta(upload_id)
    expected_user = meta.get("userId")
    if expected_user and str(expected_user) != str(user_id):
        raise HTTPException(status_code=403, detail="Acesso negado")
    if not expected_user and ENVIRONMENT != "development":
        raise HTTPException(status_code=403, detail="Acesso negado")

    filename = str(meta.get("filename") or file_path.name)

    try:
        all_tables = _extract_tables_from_pdf_path(file_path)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Erro ao ler PDF: {exc}") from exc

    upload_data = _get_upload_data_from_sources(upload_id) or {}
    table_candidates = upload_data.get("table_candidates") or []
    
    # Suportar tanto o novo formato (lista) quanto o antigo (string)
    ids_to_process = payload.table_ids
    if not ids_to_process and payload.table_id:
        ids_to_process = [payload.table_id]
        
    if not ids_to_process:
        raise HTTPException(status_code=400, detail="Nenhuma tabela selecionada")

    combined_items = []
    combined_resumo = {"total_items": 0, "valor_total": 0.0, "metodo": "gpt-4o (multi-table)"}
    ia_metadata_list = []
    pdf_bytes = file_path.read_bytes()
    tables_out = []

    for t_id in ids_to_process:
        if not t_id:
            continue
            
        selected_candidate = next((item for item in table_candidates if item.get("id") == t_id), None)

        selected = None
        if selected_candidate:
            selected = _find_table_for_page(all_tables, int(selected_candidate.get("num_pagina") or selected_candidate.get("pagina") or 1))
        if not selected:
            selected = _find_table_candidate(all_tables, t_id)
        if not selected:
            continue # Pula se não achar a tabela

        rows = selected.get("rows") or []
        page = int(selected.get("page") or 1)
        resolved_table_id = str(selected.get("table_id") or t_id)
        candidate_name = str((selected_candidate or {}).get("nome_tabela") or "")

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
            )
            
            # Merge items
            items_this_table = structured_data.get("items") or []
            combined_items.extend(items_this_table)
            
            # Merge resumo
            resumo_this = structured_data.get("resumo") or {}
            combined_resumo["total_items"] += int(resumo_this.get("total_items") or len(items_this_table))
            combined_resumo["valor_total"] += float(resumo_this.get("valor_total") or sum(float(item.get("valor_total") or 0) for item in items_this_table))
            
            ia_metadata_list.append({
                "table_id": resolved_table_id,
                "provider": provider_used,
                "resumo": resumo_this
            })
            
        except OpenAIServiceError as exc:
            logger.warning(f"Erro ao processar tabela {t_id}: {exc}")
            continue
        except Exception as exc:
            logger.warning(f"Erro inesperado ao processar tabela {t_id}: {exc}")
            continue

    if not combined_items:
        raise HTTPException(status_code=500, detail="Falha ao extrair dados de todas as tabelas selecionadas.")

    # Normalizar os itens combinados
    normalized_items = _normalize_analytic_items(combined_items)
    
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
            items_data={"items": normalized_items, "resumo": combined_resumo},
            ia_metadata=ia_metadata_final,
        )
    except Exception as exc:
        logger.error("process-confirmed: erro ao salvar no Firestore: %s", exc)
        doc_id = upload_id

    _OFFLINE_CACHE.setdefault(upload_id, {})
    _OFFLINE_CACHE[upload_id]["itemsData"] = {"items": normalized_items, "resumo": combined_resumo}
    _OFFLINE_CACHE[upload_id]["ia_metadata"] = ia_metadata_final
    _save_extracted_cache(upload_id, _OFFLINE_CACHE[upload_id])

    try:
        file_path.unlink()
        meta_path = _meta_path_for_upload_id(upload_id)
        if meta_path.exists():
            meta_path.unlink()
    except Exception as e:
        logger.warning("⚠️  Erro ao remover PDF após processamento: %s", e)

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
        "resumo": combined_resumo,
        "ia_metadata": ia_metadata_final,
        "message": f"✅ Dados extraídos de {len(ia_metadata_list)} tabela(s) com sucesso",
    }
        "filename": filename,
        "tables_found": len(tables_out),
        "items_found": len(items),
        "tables": tables_out,
        "items": items,
        "structured_items": raw_structured_items,
        "resumo": resumo,
        "ia_metadata": ia_metadata,
        "message": "Orçamento processado com a tabela selecionada",
    }


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
        if expected_user and str(expected_user) != str(user_id):
            raise HTTPException(status_code=403, detail="Acesso negado")

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
        orcamentos = OrcamentoFirestore.list_all_orcamentos()
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
    Recuperar orçamento específico do Firestore
    
    Args:
        upload_id: Upload ID
    
    Returns:
        {
            "status": "success",
            "orcamento": {...}
        }
    """
    try:
        orcamento = OrcamentoFirestore.get_orcamento_by_upload_id(
            upload_id, user_id
        )
        
        if not orcamento:
            raise HTTPException(
                status_code=404,
                detail=f"❌ Orçamento não encontrado: {upload_id}",
            )
        
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
                if expected_user and str(expected_user) != str(user_id):
                    raise HTTPException(status_code=403, detail="Acesso negado")
        
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
        
        # Ordenar por valor total decrescente
        items.sort(key=lambda x: x["valor_total"], reverse=True)
        
        # Calcular total e percentuais acumulados (regra Pareto 80/15/5 em valor)
        # Classifica pelo % acumulado *antes* do item: quem ainda não atingiu 80% do valor total em A
        # (inclui o item que cruza o corte); evita um único item dominante cair em C.
        total_value = sum(item["valor_total"] for item in items)
        accumulated = 0

        for item in items:
            pct_before = (accumulated / total_value * 100) if total_value > 0 else 0
            accumulated += item["valor_total"]
            accumulated_percentage = (accumulated / total_value * 100) if total_value > 0 else 0
            item["accumulated_percentage"] = round(accumulated_percentage, 1)

            if pct_before < 80:
                item["classification"] = "A"
            elif pct_before < 95:
                item["classification"] = "B"
            else:
                item["classification"] = "C"
        
        # Calcular resumo
        countA = sum(1 for item in items if item["classification"] == "A")
        countB = sum(1 for item in items if item["classification"] == "B")
        countC = sum(1 for item in items if item["classification"] == "C")
        
        valueA = sum(item["valor_total"] for item in items if item["classification"] == "A")
        valueB = sum(item["valor_total"] for item in items if item["classification"] == "B")
        valueC = sum(item["valor_total"] for item in items if item["classification"] == "C")
        
        summary = {
            "total": total_value,
            "countA": countA,
            "countB": countB,
            "countC": countC,
            "valueA": valueA,
            "valueB": valueB,
            "valueC": valueC,
            "percentA": round((valueA / total_value * 100), 1) if total_value > 0 else 0,
            "percentB": round((valueB / total_value * 100), 1) if total_value > 0 else 0,
            "percentC": round((valueC / total_value * 100), 1) if total_value > 0 else 0,
        }
        
        return {
            "status": "success",
            "items": items,
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

# ============== EXPORT XLSX ==============
@app.post("/api/export-xlsx")
async def export_xlsx(
    items: List[Dict],
    user_id: str = Depends(get_current_user_id),
):
    """
    Exporta itens da planilha para arquivo XLSX
    
    Args:
        items: Lista de itens [
            {
                "id": 1,
                "code": "001",
                "description": "Item",
                "unit": "un",
                "qty": 10,
                "unitPrice": 100.00
            }
        ]
    
    Returns:
        arquivo XLSX para download
    """
    try:
        if not Workbook:
            raise HTTPException(
                status_code=500,
                detail="openpyxl não está instalado",
            )
        
        # Criar workbook
        wb = Workbook()
        ws = wb.active
        ws.title = "Orçamento"
        
        # Estilos
        header_fill = PatternFill(start_color="1F4E78", end_color="1F4E78", fill_type="solid")
        header_font = Font(bold=True, color="FFFFFF", size=11)
        total_fill = PatternFill(start_color="E8F4F8", end_color="E8F4F8", fill_type="solid")
        total_font = Font(bold=True, size=11)
        currency_fill = PatternFill(start_color="F0F8FF", end_color="F0F8FF", fill_type="solid")
        
        border = Border(
            left=Side(style='thin'),
            right=Side(style='thin'),
            top=Side(style='thin'),
            bottom=Side(style='thin')
        )
        
        # Cabeçalho
        headers = ["Código", "Descrição", "Unidade", "Quantidade", "Valor Unitário", "Total"]
        for col_num, header in enumerate(headers, 1):
            cell = ws.cell(row=1, column=col_num)
            cell.value = header
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = Alignment(horizontal="center", vertical="center")
            cell.border = border
        
        # Dados
        total_geral = 0
        for row_num, item in enumerate(items, 2):
            ws.cell(row=row_num, column=1).value = item.get("code", "")
            ws.cell(row=row_num, column=2).value = item.get("description", "")
            ws.cell(row=row_num, column=3).value = item.get("unit", "")
            
            qty = float(item.get("qty", 0))
            unit_price = float(item.get("unitPrice", 0))
            total = qty * unit_price
            total_geral += total
            
            ws.cell(row=row_num, column=4).value = qty
            ws.cell(row=row_num, column=5).value = unit_price
            ws.cell(row=row_num, column=6).value = total
            
            # Formato moeda para R$
            ws.cell(row=row_num, column=5).number_format = 'R$ #,##0.00'
            ws.cell(row=row_num, column=6).number_format = 'R$ #,##0.00'
            ws.cell(row=row_num, column=6).fill = currency_fill
            
            # Bordas
            for col in range(1, 7):
                ws.cell(row=row_num, column=col).border = border
                ws.cell(row=row_num, column=col).alignment = Alignment(horizontal="right" if col >= 4 else "left")
        
        # Linha de Total
        total_row = len(items) + 3
        ws.cell(row=total_row, column=5).value = "TOTAL GERAL:"
        ws.cell(row=total_row, column=5).font = total_font
        ws.cell(row=total_row, column=5).alignment = Alignment(horizontal="right")
        
        ws.cell(row=total_row, column=6).value = total_geral
        ws.cell(row=total_row, column=6).number_format = 'R$ #,##0.00'
        ws.cell(row=total_row, column=6).fill = total_fill
        ws.cell(row=total_row, column=6).font = total_font
        ws.cell(row=total_row, column=6).border = border
        
        # Ajustar largura das colunas
        ws.column_dimensions['A'].width = 12
        ws.column_dimensions['B'].width = 40
        ws.column_dimensions['C'].width = 12
        ws.column_dimensions['D'].width = 15
        ws.column_dimensions['E'].width = 15
        ws.column_dimensions['F'].width = 15
        
        # Altura do cabeçalho
        ws.row_dimensions[1].height = 25
        
        # Salvar arquivo
        filename = f"orcamento_{uuid.uuid4().hex[:8]}.xlsx"
        file_path = TEMP_FOLDER / filename
        wb.save(file_path)
        
        logger.info(f"✅ XLSX gerado: {file_path}")
        
        return FileResponse(
            path=file_path,
            filename=filename,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
    
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
    # Se é um arquivo com extensão (CSS, JS, etc), tentar servir como estático
    if "." in path_name and not path_name.startswith("api"):
        return {"error": "File not found"}
    
    # Servir index.html para rotas do frontend
    index_path = FRONTEND_DIST / "index.html"
    if index_path.exists():
        return FileResponse(index_path)
    
    return {"error": "Frontend not available"}

# ============== RUN ==============
if __name__ == "__main__":
    import uvicorn
    import os
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=port,
        reload=False,
    )
