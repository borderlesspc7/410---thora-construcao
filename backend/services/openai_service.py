"""
Integração base com OpenAI para o fluxo de Orçamento Analítico.
Chave via OPENAI_API_KEY (nunca embutida no código).
"""

from __future__ import annotations

import base64
import json
import logging
import os
import re
import time
from io import BytesIO
from typing import Any, Dict, List, Tuple

import pdfplumber
from openai import APIConnectionError, APITimeoutError, AsyncOpenAI, BadRequestError, OpenAIError, RateLimitError

from config import (
    OPENAI_API_KEY,
    OPENAI_MODEL,
    OPENAI_ORCAMENTO_MODEL,
    OPENAI_ORCAMENTO_TIMEOUT_SECONDS,
)

from .ai_audit_logger import log_ai_exchange, truncate_rows_for_audit

logger = logging.getLogger(__name__)

_MAX_DETECTION_PAGES = 4
_MAX_DETECTION_CHARS_PER_PAGE = 3200
_MAX_TABLE_ROWS_FOR_PROMPT = 90
_MAX_CELL_CHARS = 120

DETECTION_SYSTEM_PROMPT = (
    "Você é um especialista em engenharia de custos. Sua tarefa é localizar tabelas relevantes "
    "de orçamento de obras em PDFs. Considere apenas as páginas iniciais fornecidas. "
    "Retorne a resposta obrigatoriamente no formato JSON."
)

DETECTION_USER_PROMPT_TEMPLATE = {
    "objetivo": "Identificar tabelas de orçamento com alta precisão",
    "tipos_desejados": ["Orçamento", "Planilha de Quantitativos", "Composições"],
    "regras": [
        "Retorne somente tabelas com forte evidência de serem relevantes para orçamento de obras.",
        "Ignore páginas de capa, sumário, páginas institucionais, logos, cabeçalhos e rodapés.",
        "Se uma página tiver apenas texto corrido sem tabela, não invente tabela.",
        "Use preview_texto com uma amostra literal curta do conteúdo encontrado.",
        "Ordene as tabelas por relevância descrescente.",
    ],
    "schema_saida": {
        "tables": [
            {
                "id": "table-1",
                "nome_tabela": "Orçamento Estimado",
                "num_pagina": 1,
                "preview_texto": "Item | Descrição | Unidade | Quantidade | Valor Unitário | Total",
            }
        ]
    },
}

EXTRACTION_SYSTEM_PROMPT = (
    "Você é um Engenheiro de Custos especialista em análise de dados. Sua única missão é extrair os itens da planilha de ORÇAMENTO DETALHADO de arquivos PDF de licitações e estruturá-los em um JSON estrito.\n\n"
    "REGRAS DE EXTRAÇÃO E MAPEAMENTO ESPACIAL (MUITO IMPORTANTE):\n\n"
    "0. ORDEM DAS COLUNAS NO PDF (da esquerda para a direita): Código | Descrição do Serviço | BDI | Unid. | Qtde | Preço Unit. | Preço total. "
    "Variante comum em licitações: Código | Descrição | BDI | Unid. | Qtde. Máxima | Qtde. Mínima | Preço Unit. | Preço total — use Qtde. Máxima como 'quantidade' quando existirem duas colunas de qtde. "
    "O campo JSON 'codigo' vem da coluna Código (ex: CPU6724, 5914351M). O campo 'item' é a numeração hierárquica (ex: 1.1, 2.3) se existir em coluna separada; não repita o código no campo item.\n"
    "0b. PREÇOS NA IMAGEM: Leia Preço Unit. e Preço total diretamente da imagem quando o texto extraído vier vazio ou zerado. Nunca deixe valor_unitario e valor_total zerados se a imagem mostrar valores.\n"
    "1. IDENTIFICAÇÃO DE COLUNAS POR CABEÇALHO: Localize cada coluna pelo cabeçalho exato antes de extrair valores.\n"
    "2. EXTRAÇÃO BASEADA EM LINHA: Cada valor deve pertencer à coluna vertical correta. Célula vazia → 0.0. NUNCA desloque Qtde para Preço Unit. ou Preço total.\n"
    "3. RIGOR COM NÚMEROS E UNIDADES: 'unidade' só com siglas (M2, M3, UN, m, T, TKm). Separe número e unidade se vierem juntos.\n"
    "4. LIMPEZA MATEMÁTICA: Remova 'R$' e '%'. Converta padrão brasileiro para float (ex: '3.017,500' → 3017.5; '17.260,10' → 17260.10; '20,81' → 20.81).\n"
    "5. COLUNA BDI (%): Extraia o percentual da coluna BDI de cada linha de serviço (ex: '20,81' ou '20,81%' → 20.81). Não use taxas de páginas de resumo de BDI.\n"
    "6. FÓRMULA DE CONSISTÊNCIA: quantidade × valor_unitario ≈ valor_total (tolerância ~2%). Se não bater, re-leia a linha e corrija o alinhamento das colunas.\n"
    "7. DIFERENCIE GRUPOS: Linhas só com título de capítulo ou 'Total do grupo' → tipo 'grupo' (serão ignoradas). Linhas com código de serviço e quantidade → tipo 'item'.\n"
    "8. REMOÇÃO DE LIXO: Ignore cabeçalhos repetidos, 'RESUMO GERAL', 'COMPOSIÇÕES', 'MAPA DE COTAÇÃO', linhas institucionais.\n\n"
    "FORMATO DE SAÍDA OBRIGATÓRIO (JSON):\n"
    "Retorne um array de objetos JSON chamado orcamento_itens seguindo exatamente este schema:\n"
    "{\n"
    '  "orcamento_itens": [\n'
    "    {\n"
    '      "item": "string",\n'
    '      "tipo": "grupo|item",\n'
    '      "banco": "string",\n'
    '      "codigo": "string",\n'
    '      "descricao": "string",\n'
    '      "bdi": 0.0,\n'
    '      "unidade": "string",\n'
    '      "quantidade": 0.0,\n'
    '      "valor_unitario": 0.0,\n'
    '      "valor_total": 0.0\n'
    "    }\n"
    "  ]\n"
    "}"
)

EXTRACTION_USER_PROMPT_HEADER = (
    "Extraia a tabela selecionada seguindo rigorosamente as regras do sistema, em especial o MAPEAMENTO ESPACIAL e o SANITY CHECK (Qtd * VU = Total)."
)


EXTRACTION_JSON_SCHEMA = {
    "name": "orcamento_schema",
    "strict": True,
    "schema": {
        "type": "object",
        "properties": {
            "orcamento_itens": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "item": {"type": ["string", "null"]},
                        "tipo": {"type": "string", "enum": ["grupo", "item"]},
                        "banco": {"type": ["string", "null"]},
                        "codigo": {"type": "string"},
                        "descricao": {"type": "string"},
                        "bdi": {"type": "number"},
                        "unidade": {"type": "string"},
                        "quantidade": {"type": "number"},
                        "valor_unitario": {"type": "number"},
                        "valor_total": {"type": "number"}
                    },
                    "required": [
                        "item",
                        "tipo",
                        "banco",
                        "codigo",
                        "descricao",
                        "bdi",
                        "unidade",
                        "quantidade",
                        "valor_unitario",
                        "valor_total",
                    ],
                    "additionalProperties": False
                }
            }
        },
        "required": ["orcamento_itens"],
        "additionalProperties": False
    }
}

class OpenAIServiceError(Exception):
    def __init__(self, message: str, *, status_code: int = 500, code: str = "openai_error"):
        super().__init__(message)
        self.status_code = status_code
        self.code = code


def _ensure_api_key() -> None:
    if not OPENAI_API_KEY.strip():
        raise OpenAIServiceError(
            "OPENAI_API_KEY ausente. Configure a chave no ambiente para habilitar a extração via GPT-4o.",
            status_code=503,
            code="missing_api_key",
        )


def _get_client() -> AsyncOpenAI:
    return AsyncOpenAI(
        api_key=OPENAI_API_KEY.strip(),
        timeout=OPENAI_ORCAMENTO_TIMEOUT_SECONDS,
    )


def _parse_json_content(content: str) -> Dict[str, Any]:
    text = content.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?", "", text, count=1).strip()
        text = re.sub(r"```$", "", text).strip()
    return json.loads(text)


import base64

def _pdf_page_to_base64_image(pdf_content: bytes, page_number: int) -> str:
    """Converte uma página do PDF para uma imagem base64 JPEG."""
    with pdfplumber.open(BytesIO(pdf_content)) as pdf:
        if page_number < 1 or page_number > len(pdf.pages):
            raise ValueError(f"Página {page_number} inválida.")
        page = pdf.pages[page_number - 1]
        im = page.to_image(resolution=150).original
        buffered = BytesIO()
        im.convert("RGB").save(buffered, format="JPEG")
        return base64.b64encode(buffered.getvalue()).decode("utf-8")
def _extract_page_snippets(pdf_content: bytes, max_pages: int = _MAX_DETECTION_PAGES) -> List[Dict[str, Any]]:
    snippets: List[Dict[str, Any]] = []
    with pdfplumber.open(BytesIO(pdf_content)) as pdf:
        for index, page in enumerate(pdf.pages[:max_pages], start=1):
            text = (page.extract_text() or "").strip()
            if not text:
                continue
            snippets.append(
                {
                    "page": index,
                    "text": text[:_MAX_DETECTION_CHARS_PER_PAGE],
                }
            )
    return snippets


def _build_detection_prompt(page_snippets: List[Dict[str, Any]]) -> str:
    payload = {**DETECTION_USER_PROMPT_TEMPLATE, "páginas_iniciais": page_snippets}
    return json.dumps(payload, ensure_ascii=False)


def _build_selected_table_prompt(
    table_rows: List[List[Any]],
    table_page: int,
    table_id: str,
    table_name: str | None = None,
) -> str:
    payload = {
        "tarefa": "extrair_orcamento_analitico",
        "table_id": table_id,
        "nome_tabela_sugerido": table_name,
        "num_pagina": table_page,
        "observacao": "Use apenas o contexto da tabela selecionada. Se o arquivo tiver cabeçalhos/rodapés repetidos, ignore-os.",
        "linhas": truncate_rows_for_audit(
            table_rows,
            max_rows=_MAX_TABLE_ROWS_FOR_PROMPT,
            max_cell_len=_MAX_CELL_CHARS,
        ),
    }
    return json.dumps(payload, ensure_ascii=False)


def _normalize_table_candidates(raw_tables: Any) -> List[Dict[str, Any]]:
    if isinstance(raw_tables, dict):
        raw_tables = raw_tables.get("tables") or raw_tables.get("options") or []
    if not isinstance(raw_tables, list):
        return []

    normalized: List[Dict[str, Any]] = []
    for index, item in enumerate(raw_tables, start=1):
        if not isinstance(item, dict):
            continue
        normalized.append(
            {
                "id": str(item.get("id") or f"table-{index}"),
                "nome_tabela": str(
                    item.get("nome_tabela")
                    or item.get("name")
                    or item.get("titulo")
                    or f"Tabela {index}"
                ),
                "num_pagina": int(item.get("num_pagina") or item.get("page") or 1),
                "preview_texto": str(item.get("preview_texto") or item.get("preview") or "").strip(),
            }
        )
    return normalized


def _coerce_number(value: Any) -> float:
    if value is None or value == "":
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    text = text.replace("R$", "").replace("$", "").replace(" ", "")
    if "." in text and "," in text:
        text = text.replace(".", "").replace(",", ".")
    elif "," in text and "." not in text:
        text = text.replace(",", ".")
    try:
        return float(text)
    except (TypeError, ValueError):
        return 0.0


def _coerce_bdi(value: Any) -> float:
    """Converte BDI com ou sem '%' (ex: '24,53%' -> 24.53)."""
    if value is None or value == "":
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().replace("%", "").replace(" ", "")
    return _coerce_number(text)


def _apply_line_sanity_check(
    quantidade: float,
    valor_unitario: float,
    valor_total: float,
) -> tuple[float, float, float]:
    """Corrige desalinhamento típico entre Qtde, Preço Unit. e Preço total."""
    if quantidade <= 0:
        return quantidade, valor_unitario, valor_total

    if valor_unitario <= 0 and valor_total > 0:
        valor_unitario = valor_total / quantidade

    if valor_total <= 0 and valor_unitario > 0:
        valor_total = quantidade * valor_unitario
        return quantidade, valor_unitario, valor_total

    if valor_unitario <= 0:
        return quantidade, valor_unitario, valor_total

    esperado = quantidade * valor_unitario
    if valor_total <= 0:
        return quantidade, valor_unitario, esperado

    erro_relativo = abs(valor_total - esperado) / max(abs(esperado), abs(valor_total), 1.0)
    if erro_relativo <= 0.02:
        return quantidade, valor_unitario, valor_total

    # Total do PDF costuma estar correto; realinha unitário
    if valor_total < esperado * 0.5 or valor_total > esperado * 2.0:
        vu_corrigido = valor_total / quantidade
        if vu_corrigido > 0:
            return quantidade, vu_corrigido, valor_total

    return quantidade, valor_unitario, valor_total


def _items_missing_prices(items: List[Dict[str, Any]]) -> bool:
    """True quando a maioria dos itens executivos não tem preço unitário nem total."""
    executive = [
        it
        for it in items
        if str(it.get("tipo") or "item").lower() != "grupo"
        and "total do grupo" not in str(it.get("descricao") or "").lower()
    ]
    if not executive:
        return False
    missing = 0
    for it in executive:
        vu = _coerce_number(it.get("valor_unitario"))
        vt = _coerce_number(it.get("valor_total"))
        if vu <= 0 and vt <= 0:
            missing += 1
    return missing >= max(1, len(executive) // 2)


async def _extract_with_openai_vision(
    client: AsyncOpenAI,
    *,
    system_msg: str,
    user_msg: str,
    base64_image: str,
    image_mime: str = "image/jpeg",
) -> Tuple[List[Dict[str, Any]], Dict[str, Any], str]:
    """Executa extração estruturada com imagem + texto de apoio."""
    response = await client.chat.completions.create(
        model="gpt-4o-2024-08-06",
        temperature=0.0,
        max_tokens=8192,
        response_format={"type": "json_schema", "json_schema": EXTRACTION_JSON_SCHEMA},
        messages=[
            {"role": "system", "content": system_msg},
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": (
                            f"{EXTRACTION_USER_PROMPT_HEADER}\n\n"
                            f"CONTEXTO DE TEXTO EXTRAÍDO (pode estar incompleto — a imagem é a fonte da verdade para preços):\n"
                            f"{user_msg}"
                        ),
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:{image_mime};base64,{base64_image}",
                            "detail": "high",
                        },
                    },
                ],
            },
        ],
    )
    raw_content = response.choices[0].message.content or "{}"
    if raw_content.startswith("```"):
        raw_content = raw_content.strip("`").removeprefix("json").strip()
    parsed = json.loads(raw_content)
    raw_items = parsed.get("orcamento_itens") if isinstance(parsed, dict) else []
    normalized_items = _normalize_structured_items(raw_items)
    return normalized_items, parsed if isinstance(parsed, dict) else {}, raw_content


def _should_skip_extracted_row(tipo: str, descricao: str, codigo: str) -> bool:
    if tipo == "grupo":
        return True
    desc_lower = descricao.lower()
    if "total do grupo" in desc_lower:
        return True
    if desc_lower.startswith("total ") and not codigo:
        return True
    return False


def _normalize_structured_items(raw_items: Any) -> List[Dict[str, Any]]:
    if not isinstance(raw_items, list):
        return []

    normalized: List[Dict[str, Any]] = []
    for index, item in enumerate(raw_items, start=1):
        if not isinstance(item, dict):
            continue

        item_number = item.get("item") or item.get("Item") or item.get("item_numero") or ""
        tipo = str(item.get("tipo") or "item").strip().lower()
        banco = item.get("banco") or ""
        codigo = str(item.get("codigo") or item.get("Código") or item.get("code") or "").strip()
        descricao = item.get("descricao") or item.get("Descrição") or item.get("description") or ""
        descricao = str(descricao).strip()
        if _should_skip_extracted_row(tipo, descricao, codigo):
            continue
        bdi = _coerce_bdi(item.get("bdi") or item.get("BDI") or item.get("bdi_percentual"))
        unidade = item.get("unidade") or item.get("Unidade") or item.get("unit") or "un"
        quantidade = _coerce_number(item.get("quantidade") or item.get("Quantidade") or item.get("qty"))
        valor_unitario = _coerce_number(
            item.get("valor_unitario")
            or item.get("Valor Unitário")
            or item.get("valor_unitário")
            or item.get("unit_value")
        )
        total = _coerce_number(item.get("valor_total") or item.get("Total") or item.get("total"))
        quantidade, valor_unitario, total = _apply_line_sanity_check(
            quantidade, valor_unitario, total
        )

        grupo_val = str(item.get("grupo") or item.get("Grupo") or item.get("grupo_hierarquico") or "").strip()

        normalized.append(
            {
                "item": str(item_number),
                "tipo": str(tipo).strip(),
                "banco": str(banco).strip(),
                "codigo": str(codigo),
                "grupo": grupo_val or None,
                "descricao": str(descricao).strip(),
                "bdi": bdi,
                "unidade": str(unidade).strip() or "un",
                "quantidade": quantidade,
                "valor_unitario": valor_unitario,
                "valor_total": total,
            }
        )
    return normalized


def _build_summary(items: List[Dict[str, Any]], model_name: str) -> Dict[str, Any]:
    return {
        "total_items": len(items),
        "valor_total": sum(float(item.get("valor_total") or 0) for item in items),
        "confianca": 0.82 if items else 0.0,
        "metodo": model_name,
    }


async def identify_tables(pdf_content: bytes) -> List[Dict[str, Any]]:
    """
    Identifica tabelas candidatas usando apenas as páginas iniciais do PDF.
    Retorna lista de objetos com id, nome_tabela, num_pagina e preview_texto.
    """
    _ensure_api_key()
    t0 = time.perf_counter()
    page_snippets = _extract_page_snippets(pdf_content)
    if not page_snippets:
        raise OpenAIServiceError(
            "Não foi possível extrair texto das páginas iniciais do PDF.",
            status_code=422,
            code="no_text_found",
        )

    system_msg = DETECTION_SYSTEM_PROMPT
    user_msg = _build_detection_prompt(page_snippets)
    client = _get_client()
    input_audit = {
        "pages": [{"page": snippet["page"], "chars": len(snippet["text"])} for snippet in page_snippets],
    }

    try:
        response = await client.chat.completions.create(
            model=OPENAI_ORCAMENTO_MODEL,
            temperature=0,
            max_tokens=900,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system_msg},
                {"role": "user", "content": user_msg},
            ],
        )
        duration_ms = (time.perf_counter() - t0) * 1000
        raw_content = response.choices[0].message.content or "{}"
        parsed = _parse_json_content(raw_content)
        candidates = _normalize_table_candidates(parsed)

        log_ai_exchange(
            operation="identify_tables",
            provider="openai",
            model=OPENAI_ORCAMENTO_MODEL,
            input_payload=input_audit,
            output_payload={
                "tables_found": len(candidates),
                "tables_preview": [
                    {"id": table["id"], "nome_tabela": table["nome_tabela"], "num_pagina": table["num_pagina"]}
                    for table in candidates[:10]
                ],
                "raw_chars": len(raw_content),
            },
            duration_ms=duration_ms,
        )
        return candidates

    except RateLimitError as exc:
        duration_ms = (time.perf_counter() - t0) * 1000
        log_ai_exchange(
            operation="identify_tables",
            provider="openai",
            model=OPENAI_ORCAMENTO_MODEL,
            input_payload=input_audit,
            error=f"rate_limit: {exc}",
            duration_ms=duration_ms,
        )
        raise OpenAIServiceError("Limite de requisições da OpenAI atingido. Tente novamente em instantes.", status_code=429, code="rate_limit") from exc
    except (APIConnectionError, APITimeoutError) as exc:
        duration_ms = (time.perf_counter() - t0) * 1000
        log_ai_exchange(
            operation="identify_tables",
            provider="openai",
            model=OPENAI_ORCAMENTO_MODEL,
            input_payload=input_audit,
            error=f"connection: {exc}",
            duration_ms=duration_ms,
        )
        raise OpenAIServiceError("Falha de conexão com a OpenAI. Tente novamente.", status_code=503, code="connection_error") from exc
    except BadRequestError as exc:
        duration_ms = (time.perf_counter() - t0) * 1000
        log_ai_exchange(
            operation="identify_tables",
            provider="openai",
            model=OPENAI_ORCAMENTO_MODEL,
            input_payload=input_audit,
            error=f"bad_request: {exc}",
            duration_ms=duration_ms,
        )
        raise OpenAIServiceError("A requisição para a OpenAI foi rejeitada. Verifique o prompt ou a chave.", status_code=400, code="bad_request") from exc
    except (json.JSONDecodeError, OpenAIError, ValueError) as exc:
        duration_ms = (time.perf_counter() - t0) * 1000
        log_ai_exchange(
            operation="identify_tables",
            provider="openai",
            model=OPENAI_ORCAMENTO_MODEL,
            input_payload=input_audit,
            error=f"parse_or_openai: {exc}",
            duration_ms=duration_ms,
        )
        raise OpenAIServiceError("A OpenAI retornou uma resposta inválida ao detectar tabelas.", status_code=502, code="invalid_response") from exc


async def process_selected_table(
    pdf_content: bytes,
    table_id: str,
    *,
    table_rows: List[List[Any]],
    table_page: int,
    table_name: str | None = None,
    table_image_base64: str | None = None,
) -> Tuple[Dict[str, Any], str]:
    """
    Processa a tabela escolhida com GPT-4o e retorna JSON estruturado.
    """
    _ensure_api_key()
    t0 = time.perf_counter()
    client = _get_client()

    system_msg = EXTRACTION_SYSTEM_PROMPT
    user_msg = _build_selected_table_prompt(table_rows, table_page, table_id, table_name)
    
    image_mime = "image/png"
    if table_image_base64:
        base64_image = table_image_base64.strip()
    else:
        try:
            base64_image = _pdf_page_to_base64_image(pdf_content, table_page)
            image_mime = "image/jpeg"
        except Exception as e:
            logger.warning(f"Falha ao gerar imagem da página {table_page}: {e}")
            base64_image = None

    input_audit = {
        "table_id": table_id,
        "table_name": table_name,
        "page": table_page,
        "rows_count": len(table_rows),
        "rows_truncated": truncate_rows_for_audit(table_rows, max_rows=10),
        "has_image": bool(base64_image),
        "image_source": "crop" if table_image_base64 else "full_page",
    }

    try:
        messages = [
            {"role": "system", "content": system_msg},
        ]
        
        if base64_image:
            messages.append({
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": f"{EXTRACTION_USER_PROMPT_HEADER}\n\nCONTEXTO DE TEXTO EXTRAÍDO (Pode conter erros de alinhamento, use a imagem como fonte da verdade):\n{user_msg}"
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:{image_mime};base64,{base64_image}",
                            "detail": "high"
                        }
                    }
                ]
            })
        else:
            messages.append({
                "role": "user",
                "content": f"{EXTRACTION_USER_PROMPT_HEADER}\n\nCONTEXTO DA TABELA:\n{user_msg}"
            })

        response = await client.chat.completions.create(
            model="gpt-4o-2024-08-06",
            temperature=0.0,
            max_tokens=8192,
            response_format={"type": "json_schema", "json_schema": EXTRACTION_JSON_SCHEMA},
            messages=messages,
        )
        duration_ms = (time.perf_counter() - t0) * 1000
        raw_content = response.choices[0].message.content or "{}"
        
        # Limpa formatação markdown se houver
        if raw_content.startswith("```"):
            raw_content = raw_content.strip("`").removeprefix("json").strip()
            
        try:
            parsed = json.loads(raw_content)
        except json.JSONDecodeError as e:
            print("CONTEÚDO QUE FALHOU NO PARSE:", raw_content)
            import traceback; traceback.print_exc()
            raise ValueError(f"Falha ao decodificar o JSON retornado pela OpenAI: {e}")
        raw_items = parsed.get("orcamento_itens") if isinstance(parsed, dict) else []
        normalized_items = _normalize_structured_items(raw_items)
        if not normalized_items and raw_content:
            logger.warning(
                "OpenAI retornou 0 itens úteis para %s (pág %s). raw_chars=%s snippet=%s",
                table_id,
                table_page,
                len(raw_content),
                raw_content[:200],
            )

        needs_full_page_retry = (
            table_image_base64
            and (
                not normalized_items
                or _items_missing_prices(normalized_items)
            )
        )
        if needs_full_page_retry:
            try:
                full_page_b64 = _pdf_page_to_base64_image(pdf_content, table_page)
                logger.info(
                    "Retentando %s (pág %s) com imagem da página inteira (itens=%s, sem_preço=%s)",
                    table_id,
                    table_page,
                    len(normalized_items),
                    _items_missing_prices(normalized_items),
                )
                retry_items, retry_parsed, retry_raw = await _extract_with_openai_vision(
                    client,
                    system_msg=system_msg,
                    user_msg=user_msg,
                    base64_image=full_page_b64,
                    image_mime="image/jpeg",
                )
                if retry_items and (
                    not normalized_items
                    or not _items_missing_prices(retry_items)
                    or len(retry_items) > len(normalized_items)
                ):
                    normalized_items = retry_items
                    parsed = retry_parsed
                    raw_content = retry_raw
                    input_audit["image_source"] = "full_page_retry"
                    duration_ms = (time.perf_counter() - t0) * 1000
            except Exception as retry_exc:
                logger.warning("Retry página inteira falhou para %s: %s", table_id, retry_exc)

        summary = parsed.get("resumo") if isinstance(parsed, dict) else {}
        if not isinstance(summary, dict):
            summary = _build_summary(normalized_items, OPENAI_ORCAMENTO_MODEL)
        else:
            summary = {
                "total_items": int(summary.get("total_items") or len(normalized_items)),
                "valor_total": float(summary.get("valor_total") or sum(float(item.get("valor_total") or 0) for item in normalized_items)),
                "confianca": float(summary.get("confianca") or 0.82),
                "metodo": str(summary.get("metodo") or OPENAI_ORCAMENTO_MODEL),
            }

        structured_output = {
            "items": normalized_items,
            "resumo": summary,
        }

        log_ai_exchange(
            operation="process_selected_table",
            provider="openai",
            model=OPENAI_ORCAMENTO_MODEL,
            input_payload=input_audit,
            output_payload={
                "items_count": len(normalized_items),
                "raw_items_count": len(structured_output["items"]),
                "resumo": summary,
                "raw_chars": len(raw_content),
            },
            duration_ms=duration_ms,
        )
        return structured_output, f"openai:{OPENAI_ORCAMENTO_MODEL}"

    except RateLimitError as exc:
        duration_ms = (time.perf_counter() - t0) * 1000
        log_ai_exchange(
            operation="process_selected_table",
            provider="openai",
            model=OPENAI_ORCAMENTO_MODEL,
            input_payload=input_audit,
            error=f"rate_limit: {exc}",
            duration_ms=duration_ms,
        )
        raise OpenAIServiceError("Limite de requisições da OpenAI atingido. Tente novamente em instantes.", status_code=429, code="rate_limit") from exc
    except (APIConnectionError, APITimeoutError) as exc:
        duration_ms = (time.perf_counter() - t0) * 1000
        log_ai_exchange(
            operation="process_selected_table",
            provider="openai",
            model=OPENAI_ORCAMENTO_MODEL,
            input_payload=input_audit,
            error=f"connection: {exc}",
            duration_ms=duration_ms,
        )
        raise OpenAIServiceError("Falha de conexão com a OpenAI. Tente novamente.", status_code=503, code="connection_error") from exc
    except BadRequestError as exc:
        duration_ms = (time.perf_counter() - t0) * 1000
        log_ai_exchange(
            operation="process_selected_table",
            provider="openai",
            model=OPENAI_ORCAMENTO_MODEL,
            input_payload=input_audit,
            error=f"bad_request: {exc}",
            duration_ms=duration_ms,
        )
        print("OPENAI BAD REQUEST ERROR:", exc)
        import traceback; traceback.print_exc()
        raise OpenAIServiceError(f"A requisição para a OpenAI foi rejeitada: {exc}", status_code=400, code="bad_request") from exc
    except (json.JSONDecodeError, OpenAIError, ValueError) as exc:
        duration_ms = (time.perf_counter() - t0) * 1000
        log_ai_exchange(
            operation="process_selected_table",
            provider="openai",
            model=OPENAI_ORCAMENTO_MODEL,
            input_payload=input_audit,
            error=f"parse_or_openai: {exc}",
            duration_ms=duration_ms,
        )
        print("OPENAI PARSE/RESPONSE ERROR:", exc)
        import traceback; traceback.print_exc()
        raise OpenAIServiceError(f"A OpenAI retornou uma resposta inválida: {exc}", status_code=502, code="invalid_response") from exc


# ---------------------------------------------------------------------------
# Relatórios — chat multi-turno (ChatGPT style)
# ---------------------------------------------------------------------------

REPORT_CHAT_MODEL = os.getenv("OPENAI_REPORT_MODEL", OPENAI_MODEL)
_MAX_REPORT_HISTORY = 24

REPORT_CHAT_JSON_SCHEMA = {
    "name": "report_chat_response",
    "strict": True,
    "schema": {
        "type": "object",
        "properties": {
            "reply": {
                "type": "string",
                "description": "Resposta em Markdown (GFM): tabelas, listas, negrito, código.",
            },
            "chart": {
                "type": "object",
                "properties": {
                    "type": {
                        "type": "string",
                        "enum": ["none", "bar", "pie"],
                        "description": "Use 'none' quando não houver gráfico.",
                    },
                    "title": {"type": "string"},
                    "value_label": {
                        "type": "string",
                        "enum": ["valor", "quantidade", "percentual"],
                    },
                    "data": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "name": {"type": "string"},
                                "value": {"type": "number"},
                            },
                            "required": ["name", "value"],
                            "additionalProperties": False,
                        },
                    },
                },
                "required": ["type", "title", "value_label", "data"],
                "additionalProperties": False,
            },
        },
        "required": ["reply", "chart"],
        "additionalProperties": False,
    },
}

REPORT_CHAT_SYSTEM_TEMPLATE = """Você é um Engenheiro de Custos Sênior e Analista de Dados especializado em orçamentos de obras públicas e privadas no Brasil.

CONTEXTO DO ORÇAMENTO (JSON validado — fonte única da verdade; NUNCA invente itens ou valores):
{budget_json}

RESUMO CURVA ABC:
{abc_summary}

REGRAS OBRIGATÓRIAS:
1. Responda SOMENTE com base nos dados do JSON acima.
2. O campo "reply" deve usar Markdown com GitHub Flavored Markdown (tabelas com | col |, listas, **negrito**).
3. Quando o usuário pedir TABELA, use OBRIGATORIAMENTE tabela Markdown GFM no campo "reply", com cabeçalho e linha separadora. Exemplo:
| # | Descrição | Qtd. | Valor total |
|---:|---|---:|---:|
| 1 | Serviço X | 10,00 | R$ 150.000,00 |
Nunca substitua tabela por lista numerada quando pedirem "tabela".
4. Respeite a quantidade pedida (ex: "5 itens" → exatamente 5 linhas na tabela).
5. Preencha "chart" APENAS se o usuário pedir gráfico/visualização OU se um gráfico facilitar muito a resposta; caso contrário use type "none", title "", value_label "valor" e data [].
6. Em "chart": type "bar", "pie" ou "none"; data com até 15 pontos; "value" em REAIS quando value_label for "valor" (use valor_total_calculado), NUNCA percentual acumulado 0-100 no eixo de valor.
7. Quando houver gráfico, o campo "reply" deve trazer análise textual completa (2+ parágrafos), insights e tabela Markdown quando fizer sentido — o PDF exporta texto + gráfico juntos.
8. value_label: "quantidade" só para gráficos de quantidade; "percentual" só se o usuário pedir % explicitamente; caso contrário "valor".
9. Mantenha coerência com o histórico da conversa (perguntas anteriores do usuário).
10. Não responda assuntos fora deste orçamento/PDF.
11. Responda sempre em português do Brasil."""


def _build_abc_summary(items: List[Dict[str, Any]]) -> str:
    totals = {"A": 0.0, "B": 0.0, "C": 0.0}
    counts = {"A": 0, "B": 0, "C": 0}
    for item in items:
        cls = str(item.get("classification") or item.get("classificacao") or "").upper()
        if cls not in totals:
            continue
        val = float(item.get("valor_total_calculado") or item.get("lineTotal") or item.get("valor_total") or 0)
        totals[cls] += val
        counts[cls] += 1
    grand = sum(totals.values()) or 1.0
    lines = []
    for cls in ("A", "B", "C"):
        pct = totals[cls] / grand * 100.0
        lines.append(f"- Classe {cls}: {counts[cls]} itens, R$ {totals[cls]:,.2f} ({pct:.1f}% do total)")
    return "\n".join(lines) if lines else "Classificação ABC não disponível."


def _normalize_report_chart(raw_chart: Any) -> Dict[str, Any] | None:
    if raw_chart is None:
        return None
    if not isinstance(raw_chart, dict):
        return None
    chart_type_raw = str(raw_chart.get("type") or raw_chart.get("chart_type") or "").lower()
    if chart_type_raw in ("none", "null", ""):
        return None
    data = raw_chart.get("data") or []
    if not isinstance(data, list) or not data:
        return None
    normalized = []
    for row in data[:15]:
        if not isinstance(row, dict):
            continue
        normalized.append(
            {
                "name": str(row.get("name") or row.get("label") or "-")[:55],
                "value": float(row.get("value") or row.get("valor") or 0),
            }
        )
    if not normalized:
        return None
    chart_type = str(raw_chart.get("type") or raw_chart.get("chart_type") or "bar").lower()
    if chart_type not in ("bar", "pie"):
        chart_type = "bar"
    return {
        "type": chart_type,
        "chart_type": "horizontal_bar" if chart_type == "bar" else "pie",
        "title": str(raw_chart.get("title") or "Gráfico"),
        "value_label": str(raw_chart.get("value_label") or "valor"),
        "data": normalized,
    }


async def generate_report_chat(
    conversation: List[Dict[str, str]],
    budget_context: Dict[str, Any],
) -> Tuple[Dict[str, Any], str]:
    """
    Chat multi-turno com structured output.
    conversation: [{"role": "user"|"assistant", "content": "..."}]
    budget_context: orçamento completo + metadados
    """
    if not OPENAI_API_KEY:
        raise OpenAIServiceError(
            "OPENAI_API_KEY não configurada.",
            status_code=503,
            code="missing_api_key",
        )

    items = budget_context.get("itens") or []
    abc_summary = _build_abc_summary(items if isinstance(items, list) else [])
    budget_json = json.dumps(budget_context, ensure_ascii=False, default=str)
    if len(budget_json) > 120_000:
        budget_json = json.dumps(
            {**budget_context, "itens": (items[:180] if isinstance(items, list) else [])},
            ensure_ascii=False,
            default=str,
        )

    system_content = REPORT_CHAT_SYSTEM_TEMPLATE.format(
        budget_json=budget_json,
        abc_summary=abc_summary,
    )

    api_messages: List[Dict[str, str]] = [{"role": "system", "content": system_content}]
    for msg in conversation[-_MAX_REPORT_HISTORY:]:
        role = str(msg.get("role") or "user").lower()
        if role not in ("user", "assistant"):
            continue
        content = str(msg.get("content") or "").strip()
        if not content:
            continue
        api_messages.append({"role": role, "content": content})

    if not any(m["role"] == "user" for m in api_messages):
        raise OpenAIServiceError("Nenhuma mensagem do usuário na conversa.", status_code=400)

    client = AsyncOpenAI(api_key=OPENAI_API_KEY, timeout=OPENAI_ORCAMENTO_TIMEOUT_SECONDS)
    t0 = time.perf_counter()
    input_audit = {
        "messages_count": len(api_messages),
        "budget_items": len(items) if isinstance(items, list) else 0,
    }

    json_object_hint = (
        '\n\nFORMATO DE SAÍDA (JSON único, sem markdown externo): '
        '{"reply": "<markdown>", "chart": {"type": "none|bar|pie", "title": "...", '
        '"value_label": "valor|quantidade|percentual", "data": [{"name": "...", "value": 0}]}}'
    )
    attempts: List[Tuple[str, Dict[str, Any] | None]] = [
        ("json_schema", {"type": "json_schema", "json_schema": REPORT_CHAT_JSON_SCHEMA}),
        ("json_object", {"type": "json_object"}),
    ]
    last_bad_request: BadRequestError | None = None
    parsed: Dict[str, Any] | None = None
    model_used = REPORT_CHAT_MODEL

    try:
        for fmt_name, response_format in attempts:
            messages = api_messages
            if fmt_name == "json_object":
                messages = [
                    {
                        **api_messages[0],
                        "content": api_messages[0]["content"] + json_object_hint,
                    },
                    *api_messages[1:],
                ]
            try:
                response = await client.chat.completions.create(
                    model=REPORT_CHAT_MODEL,
                    temperature=0.2,
                    max_tokens=4096,
                    response_format=response_format,
                    messages=messages,
                )
            except BadRequestError as exc:
                last_bad_request = exc
                logger.warning(
                    "OpenAI report chat %s falhou (model=%s): %s",
                    fmt_name,
                    REPORT_CHAT_MODEL,
                    exc,
                )
                if fmt_name == "json_schema":
                    continue
                raise OpenAIServiceError(
                    f"OpenAI rejeitou a requisição: {exc}",
                    status_code=400,
                    code="bad_request",
                ) from exc

            raw_content = response.choices[0].message.content or "{}"
            if raw_content.startswith("```"):
                raw_content = raw_content.strip("`").removeprefix("json").strip()
            candidate = json.loads(raw_content)
            if not isinstance(candidate, dict):
                raise ValueError("Resposta não é objeto JSON")
            parsed = candidate
            break

        if parsed is None:
            raise last_bad_request or ValueError("Nenhuma resposta da OpenAI")

        duration_ms = (time.perf_counter() - t0) * 1000
        chart = _normalize_report_chart(parsed.get("chart"))
        result = {
            "reply": str(parsed.get("reply") or "").strip(),
            "chart": chart,
            "response_type": "mixed" if chart else "text",
        }

        log_ai_exchange(
            operation="generate_report_chat",
            provider="openai",
            model=model_used,
            input_payload=input_audit,
            output_payload={
                "reply_chars": len(result["reply"]),
                "has_chart": chart is not None,
            },
            duration_ms=duration_ms,
        )
        return result, f"openai:{model_used}"

    except OpenAIServiceError:
        raise
    except RateLimitError as exc:
        raise OpenAIServiceError(
            "Limite de requisições da OpenAI atingido.",
            status_code=429,
            code="rate_limit",
        ) from exc
    except (APIConnectionError, APITimeoutError) as exc:
        raise OpenAIServiceError(
            "Falha de conexão com a OpenAI.",
            status_code=503,
            code="connection_error",
        ) from exc
    except (json.JSONDecodeError, OpenAIError, ValueError) as exc:
        raise OpenAIServiceError(
            f"Resposta inválida da OpenAI: {exc}",
            status_code=502,
            code="invalid_response",
        ) from exc
