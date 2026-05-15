"""
Integração base com OpenAI para o fluxo de Orçamento Analítico.
Chave via OPENAI_API_KEY (nunca embutida no código).
"""

from __future__ import annotations

import json
import logging
import re
import time
from io import BytesIO
from typing import Any, Dict, List, Tuple

import pdfplumber
from openai import APIConnectionError, APITimeoutError, AsyncOpenAI, BadRequestError, OpenAIError, RateLimitError

from config import OPENAI_API_KEY, OPENAI_ORCAMENTO_MODEL, OPENAI_ORCAMENTO_TIMEOUT_SECONDS

from .ai_audit_logger import log_ai_exchange, truncate_rows_for_audit

logger = logging.getLogger(__name__)

_MAX_DETECTION_PAGES = 4
_MAX_DETECTION_CHARS_PER_PAGE = 3200
_MAX_TABLE_ROWS_FOR_PROMPT = 90
_MAX_CELL_CHARS = 120

DETECTION_SYSTEM_PROMPT = (
    "Você é um especialista em engenharia de custos. Sua tarefa é localizar tabelas relevantes "
    "de orçamento de obras em PDFs. Considere apenas as páginas iniciais fornecidas."
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
    "Você é um especialista em engenharia de custos e extração literal de planilhas orçamentárias. "
    "Sua tarefa é transcrever exatamente as linhas da tabela selecionada no PDF, sem resumir, "
    "sem inventar e sem omitir códigos ou descrições."
)

EXTRACTION_USER_PROMPT_HEADER = (
    "Extraia a tabela selecionada seguindo estas regras rigorosas:\n"
    "1) Mapeamento literal: preserve cada linha exatamente como escrita no PDF.\n"
    "2) Tratamento de células mescladas: se houver grupos como '1.1 Movimentação de Terra', "
    "mantenha a hierarquia no JSON com um campo de grupo ou repita o cabeçalho do grupo em cada item.\n"
    "3) Validação matemática interna: confira mentalmente Quantidade x Valor Unitário contra a coluna Total. "
    "Se houver divergência, reanalise a linha antes de responder.\n"
    "4) Limpeza de caracteres: normalize valores numéricos removendo R$, pontos de milhar e espaços. "
    "Retorne apenas o número decimal puro (ex.: 1.250,50 -> 1250.50).\n"
    "5) Foco na tabela selecionada: use apenas o contexto da tabela escolhida e ignore rodapés, "
    "números de página, logos e textos institucionais.\n"
    "6) Não resuma descrições, não altere códigos e não descarte linhas válidas.\n\n"
    "Formato obrigatório do JSON:\n"
    "{\n"
    '  "items": [\n'
    "    {\n"
    '      "Item": "1.1",\n'
    '      "Código": "12345",\n'
    '      "Grupo": "1 Movimentação de Terra",\n'
    '      "Descrição": "texto literal do PDF",\n'
    '      "Unidade": "m3",\n'
    '      "Quantidade": 10.0,\n'
    '      "Valor Unitário": 1250.5,\n'
    '      "Total": 12505.0\n'
    "    }\n"
    "  ],\n"
    '  "resumo": {\n'
    '    "total_items": 0,\n'
    '    "valor_total": 0,\n'
    '    "confianca": 0.0,\n'
    '    "metodo": "gpt-4o"\n'
    "  }\n"
    "}\n"
    "Se um item pertencer a um grupo, preserve o grupo em um campo próprio ou replique o cabeçalho do grupo "
    "em cada item para não perder contexto."
)


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


def _normalize_structured_items(raw_items: Any) -> List[Dict[str, Any]]:
    if not isinstance(raw_items, list):
        return []

    normalized: List[Dict[str, Any]] = []
    for index, item in enumerate(raw_items, start=1):
        if not isinstance(item, dict):
            continue

        item_number = item.get("Item") or item.get("item") or item.get("item_numero") or index
        codigo = item.get("Código") or item.get("codigo") or item.get("code") or ""
        descricao = item.get("Descrição") or item.get("descricao") or item.get("description") or ""
        unidade = item.get("Unidade") or item.get("unidade") or item.get("unit") or "un"
        quantidade = _coerce_number(item.get("Quantidade") or item.get("quantidade") or item.get("qty"))
        valor_unitario = _coerce_number(
            item.get("Valor Unitário")
            or item.get("valor_unitario")
            or item.get("valor_unitário")
            or item.get("unit_value")
        )
        total = _coerce_number(item.get("Total") or item.get("total") or item.get("valor_total"))
        if total <= 0 and quantidade and valor_unitario:
            total = quantidade * valor_unitario

        normalized.append(
            {
                "item": str(item_number),
                "codigo": str(codigo),
                "grupo": str(item.get("Grupo") or item.get("grupo") or item.get("grupo_hierarquico") or "").strip() or None,
                "descricao": str(descricao).strip(),
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
) -> Tuple[Dict[str, Any], str]:
    """
    Processa a tabela escolhida com GPT-4o e retorna JSON estruturado.
    """
    _ensure_api_key()
    t0 = time.perf_counter()
    client = _get_client()

    system_msg = EXTRACTION_SYSTEM_PROMPT
    user_msg = _build_selected_table_prompt(table_rows, table_page, table_id, table_name)
    input_audit = {
        "table_id": table_id,
        "table_name": table_name,
        "page": table_page,
        "rows_count": len(table_rows),
        "rows_truncated": truncate_rows_for_audit(table_rows, max_rows=10),
    }

    try:
        response = await client.chat.completions.create(
            model=OPENAI_ORCAMENTO_MODEL,
            temperature=0,
            max_tokens=2200,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system_msg},
                {
                    "role": "user",
                    "content": f"{EXTRACTION_USER_PROMPT_HEADER}\n\nCONTEXTO DA TABELA:\n{user_msg}",
                },
            ],
        )
        duration_ms = (time.perf_counter() - t0) * 1000
        raw_content = response.choices[0].message.content or "{}"
        parsed = _parse_json_content(raw_content)
        raw_items = parsed.get("items") if isinstance(parsed, dict) else []
        normalized_items = _normalize_structured_items(raw_items)
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
            "items": raw_items if isinstance(raw_items, list) else [],
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
        raise OpenAIServiceError("A requisição para a OpenAI foi rejeitada. Verifique o prompt ou a chave.", status_code=400, code="bad_request") from exc
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
        raise OpenAIServiceError("A OpenAI retornou uma resposta inválida ao processar a tabela selecionada.", status_code=502, code="invalid_response") from exc
