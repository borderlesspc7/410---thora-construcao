"""
Integração base com OpenAI para o fluxo de Orçamento Analítico.
Chave via OPENAI_API_KEY (nunca embutida no código).
"""

from __future__ import annotations

import base64
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
    "1. IDENTIFICAÇÃO DE COLUNAS POR CABEÇALHO: Localize horizontalmente onde começam e terminam as colunas 'UNID', 'QUANT', 'PREÇO UNITÁRIO' e 'PREÇO TOTAL'.\n"
    "2. EXTRAÇÃO BASEADA EM LINHA: Para cada linha, garanta que o valor extraído pertence estritamente ao eixo vertical daquela coluna. Se uma célula estiver vazia, retorne 0.0. NUNCA puxe o valor da coluna vizinha para preencher um buraco.\n"
    "3. RIGOR COM NÚMEROS E UNIDADES: A coluna 'Unidade' deve conter apenas siglas (M2, M3, UN, M, CHP, CHI, etc). Se a quantidade ou preço contiver letras (ex: '422,33 CHP'), separe o número para a coluna correta e a sigla para a coluna de unidade.\n"
    "4. LIMPEZA MATEMÁTICA: Remova qualquer símbolo monetário ('R$') e converta os números do padrão brasileiro para o formato float universal (ex: de '1.234,56' para '1234.56'). Retorne APENAS NÚMEROS nos campos de quantidade e valores.\n"
    "5. FÓRMULA DE CONSISTÊNCIA (SANITY CHECK): Verifique se Quantidade * Valor Unitário = Valor Total (com margem de erro de arredondamento). Se o cálculo não bater, RE-ESCANEIE a linha, pois houve erro de leitura ou deslocamento de coluna.\n"
    "6. DIFERENCIE GRUPOS DE ITENS: Se a linha for apenas o título de um grupo (ex: '1. SERVIÇOS PRELIMINARES'), classifique o campo tipo como 'grupo'. Se for um serviço com quantidade e valor, classifique como 'item'.\n"
    "7. REMOÇÃO DE LIXO: Ignore completamente linhas que contenham 'GDF', 'Processo SEI', cabeçalhos de tabela repetidos no meio da página, 'RESUMO GERAL', 'COMPOSIÇÕES', 'MAPA DE COTAÇÃO' e 'BDI'. Foque 100% no ORÇAMENTO DETALHADO.\n\n"
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
                        "codigo": {"type": ["string", "null"]},
                        "descricao": {"type": "string"},
                        "unidade": {"type": ["string", "null"]},
                        "quantidade": {"type": "number"},
                        "valor_unitario": {"type": "number"},
                        "valor_total": {"type": "number"}
                    },
                    "required": ["item", "tipo", "banco", "codigo", "descricao", "unidade", "quantidade", "valor_unitario", "valor_total"],
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


def _normalize_structured_items(raw_items: Any) -> List[Dict[str, Any]]:
    if not isinstance(raw_items, list):
        return []

    normalized: List[Dict[str, Any]] = []
    for index, item in enumerate(raw_items, start=1):
        if not isinstance(item, dict):
            continue

        item_number = item.get("item") or item.get("Item") or item.get("item_numero") or index
        tipo = item.get("tipo") or "item"
        banco = item.get("banco") or ""
        codigo = item.get("codigo") or item.get("Código") or item.get("code") or ""
        descricao = item.get("descricao") or item.get("Descrição") or item.get("description") or ""
        unidade = item.get("unidade") or item.get("Unidade") or item.get("unit") or "un"
        quantidade = _coerce_number(item.get("quantidade") or item.get("Quantidade") or item.get("qty"))
        valor_unitario = _coerce_number(
            item.get("valor_unitario")
            or item.get("Valor Unitário")
            or item.get("valor_unitário")
            or item.get("unit_value")
        )
        total = _coerce_number(item.get("valor_total") or item.get("Total") or item.get("total"))
        if total <= 0 and quantidade and valor_unitario:
            total = quantidade * valor_unitario

        # Se for grupo, tentamos manter o formato antigo de grupo ou apenas repassamos
        grupo_val = ""
        if tipo == "grupo":
            grupo_val = str(descricao).strip()
        else:
            grupo_val = str(item.get("grupo") or item.get("Grupo") or item.get("grupo_hierarquico") or "").strip()

        normalized.append(
            {
                "item": str(item_number),
                "tipo": str(tipo).strip(),
                "banco": str(banco).strip(),
                "codigo": str(codigo),
                "grupo": grupo_val or None,
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

    EXTRACTION_SYSTEM_PROMPT = (
        "Você é um Extrator de Dados Analíticos de Engenharia. Você receberá imagens de planilhas de orçamento. Sua tarefa é transcrever os dados com 100% de precisão visual e matemática.\n\n"
        "REGRA 1 - LEITURA VISUAL: Leia a tabela da ESQUERDA para a DIREITA, acompanhando a linha visual da grade. Nunca misture dados de uma linha com a de baixo.\n"
        "REGRA 2 - IDENTIFICAÇÃO DE PADRÃO: As colunas seguem esta ordem lógica: [ITEM] -> [DESCRIÇÃO] -> [UNIDADE (ex: M, M2, UN, CHP)] -> [QUANTIDADE] -> [PREÇO UNITÁRIO] -> [PREÇO TOTAL].\n"
        "REGRA 3 - ANCORAGEM PELA UNIDADE: Procure a coluna de UNIDADE (sempre letras como UN, M2, Mês). O número que está imediatamente à esquerda ou direita dela é a QUANTIDADE. O valor financeiro maior no final da linha é o TOTAL.\n"
        "REGRA 4 - RASTREAMENTO MATEMÁTICO (OBRIGATÓRIO): Antes de gerar a saída de uma linha, multiplique internamente [QUANTIDADE] x [PREÇO UNITÁRIO]. Se o resultado não for igual ao [PREÇO TOTAL] (tolerância de R$ 0,50), você alinhou as colunas errado. Corrija o alinhamento antes de formatar o JSON.\n"
        "REGRA 5 - SANEAMENTO: Remova 'R$' e converta valores para float (ex: '20.308,75' vira 20308.75).\n\n"
        "Traga APENAS os itens que possuem número de ITEM (ex: 1.1, 2.3). Ignore textos soltos, assinaturas e cabeçalhos."
    )

    system_msg = EXTRACTION_SYSTEM_PROMPT
    user_msg = _build_selected_table_prompt(table_rows, table_page, table_id, table_name)
    
    try:
        base64_image = _pdf_page_to_base64_image(pdf_content, table_page)
    except Exception as e:
        logger.warning(f"Falha ao gerar imagem da página {table_page}: {e}")
        base64_image = None

    input_audit = {
        "table_id": table_id,
        "table_name": table_name,
        "page": table_page,
        "rows_count": len(table_rows),
        "rows_truncated": truncate_rows_for_audit(table_rows, max_rows=10),
        "has_image": bool(base64_image)
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
                            "url": f"data:image/jpeg;base64,{base64_image}",
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
