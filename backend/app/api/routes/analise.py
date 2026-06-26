from fastapi import APIRouter, Depends

from app.api.deps import get_current_user_id
from app.domain.schemas.analise import AnalisarLinhasRequest, AnalisarLinhasResponse, executar_analise_linhas

router = APIRouter(prefix="/api/orcamentos", tags=["analise"])


@router.post("/analisar-linhas", response_model=AnalisarLinhasResponse)
async def analisar_linhas_orcamento(
    payload: AnalisarLinhasRequest,
    _user_id: str = Depends(get_current_user_id),
):
    """Análise determinística de linhas orçamentárias (sem IA)."""
    return executar_analise_linhas(payload)
