from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import get_current_user_id
from app.domain.schemas.abc import AbcBatchRegisterRequest, AbcJobUpdateRequest
from app.infrastructure.storage.abc_job_store import AbcJobStore
from app.infrastructure.storage.upload_store import UploadStore

router = APIRouter(prefix="/api/abc-analysis", tags=["abc-stubs"])

_abc_jobs = AbcJobStore()
_upload_store = UploadStore()

_VALID_STATUSES = {
    "uploading",
    "detecting",
    "awaiting_selection",
    "queued",
    "processing",
    "completed",
    "failed",
}


@router.post("/batch-register")
async def abc_batch_register(
    payload: AbcBatchRegisterRequest,
    user_id: str = Depends(get_current_user_id),
):
    registered: list[dict] = []
    for item in payload.jobs:
        upload_id = UploadStore.validate_upload_id(item.upload_id)
        _upload_store.assert_access(upload_id, user_id)
        job = _abc_jobs.init_job(
            upload_id,
            user_id=user_id,
            filename=item.filename,
            status="uploading",
            message="Arquivo recebido — aguardando detecção de tabelas…",
        )
        registered.append(job)
    return {"status": "success", "jobs": registered}


@router.patch("/{upload_id}")
async def abc_update_job(
    upload_id: str,
    payload: AbcJobUpdateRequest,
    user_id: str = Depends(get_current_user_id),
):
    upload_id = UploadStore.validate_upload_id(upload_id)
    _upload_store.assert_access(upload_id, user_id)

    job = _abc_jobs.get(upload_id)
    if not job:
        meta = _upload_store.load_meta(upload_id)
        job = _abc_jobs.init_job(
            upload_id,
            user_id=user_id,
            filename=str(meta.get("filename") or f"{upload_id}.pdf"),
        )

    fields: dict = {}
    if payload.status:
        if payload.status not in _VALID_STATUSES:
            raise HTTPException(status_code=400, detail="Status inválido")
        fields["status"] = payload.status
    if payload.message is not None:
        fields["message"] = payload.message
    if payload.tables_found is not None:
        fields["tables_found"] = payload.tables_found
    if payload.error is not None:
        fields["error"] = payload.error

    if fields:
        _abc_jobs.update(upload_id, **fields)

    updated = _abc_jobs.get(upload_id)
    return {"status": "success", "job": updated}
