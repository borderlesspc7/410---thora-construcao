from typing import Any

from pydantic import BaseModel, Field

from app.domain.services.orcamento_analise import analisar_linhas_orcamento


class ContextoAnaliseRequest(BaseModel):
    bdi_global_percent: float | None = None
    tolerancia_monetaria: float = 0.02
    tolerancia_percentual: float = 0.5


class AnalisarLinhasRequest(BaseModel):
    linhas: list[dict[str, Any]] = Field(default_factory=list)
    contexto: ContextoAnaliseRequest | None = None


class AnalisarLinhasResponse(BaseModel):
    versao_modelo: str
    contexto: dict[str, Any]
    linhas: list[dict[str, Any]]
    resumo: dict[str, int]


def executar_analise_linhas(payload: AnalisarLinhasRequest) -> AnalisarLinhasResponse:
    contexto = payload.contexto or ContextoAnaliseRequest()
    resultado = analisar_linhas_orcamento(
        payload.linhas,
        bdi_global=contexto.bdi_global_percent,
        tolerancia_monetaria=contexto.tolerancia_monetaria,
        tolerancia_percentual=contexto.tolerancia_percentual,
    )
    return AnalisarLinhasResponse(**resultado)
