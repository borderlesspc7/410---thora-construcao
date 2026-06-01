"""
Estado em memória de jobs de Orçamento Analítico (progresso + resultado).
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

_ANALITICO_JOBS: Dict[str, Dict[str, Any]] = {}


def get_job(upload_id: str) -> Optional[Dict[str, Any]]:
    return _ANALITICO_JOBS.get(upload_id)


def init_job(upload_id: str) -> Dict[str, Any]:
    job: Dict[str, Any] = {
        "status": "processing",
        "upload_id": upload_id,
        "pages_total": 0,
        "pages_done": 0,
        "current_page": None,
        "message": "Iniciando análise…",
        "result": None,
        "error": None,
        "cached": False,
    }
    _ANALITICO_JOBS[upload_id] = job
    return job


def update_job(upload_id: str, **fields: Any) -> None:
    job = _ANALITICO_JOBS.get(upload_id)
    if not job:
        return
    job.update(fields)


def make_progress_callback(upload_id: str):
    def _callback(payload: Dict[str, Any]) -> None:
        update_job(
            upload_id,
            pages_total=int(payload.get("pages_total") or 0),
            pages_done=int(payload.get("pages_done") or 0),
            current_page=payload.get("current_page"),
            message=str(payload.get("message") or ""),
        )

    return _callback


def complete_job(upload_id: str, result: Dict[str, Any]) -> None:
    update_job(
        upload_id,
        status="completed",
        result=result,
        pages_done=result.get("resumo", {}).get("paginas_processadas")
        or _ANALITICO_JOBS.get(upload_id, {}).get("pages_done"),
        message="Análise concluída",
    )


def fail_job(upload_id: str, error: str) -> None:
    logger.error("Orçamento analítico — job %s falhou: %s", upload_id, error)
    update_job(
        upload_id,
        status="failed",
        error=error,
        message=error[:240] if error else "Falha na análise",
    )


def clear_job(upload_id: str) -> None:
    _ANALITICO_JOBS.pop(upload_id, None)
