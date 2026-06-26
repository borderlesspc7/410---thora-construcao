import asyncio
import logging

from fastapi import APIRouter, Depends, Form, HTTPException

from app.api.deps import get_current_user_id
from app.domain.schemas.table import TableDetectResponse
from app.domain.services.table_detection import (
    detect_table_options,
    public_options_from_raw,
    recommended_table_ids,
)
from app.infrastructure.storage.table_cache_store import TableCacheStore
from app.infrastructure.storage.upload_store import UploadStore

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/orcamentos", tags=["tables"])

_upload_store = UploadStore()
_table_cache = TableCacheStore()


@router.post("/detect-tables", response_model=TableDetectResponse)
async def detect_orcamento_tables(
    upload_id: str = Form(...),
    user_id: str = Depends(get_current_user_id),
):
    upload_id = UploadStore.validate_upload_id(upload_id)
    _upload_store.assert_access(upload_id, user_id)
    file_path = _upload_store.ensure_pdf(upload_id)

    if _table_cache.is_valid(upload_id):
        options, _ = _table_cache.get(upload_id)
        public = public_options_from_raw(options)
        return TableDetectResponse(
            upload_id=upload_id,
            tables_found=len(public),
            options=public,
            mock_fallback=False,
            cached=True,
            recommended_table_ids=recommended_table_ids(options),
        )

    try:
        options, fallback_used = await asyncio.to_thread(detect_table_options, file_path)
    except Exception as exc:
        logger.error("detect-tables falhou: %s", exc)
        raise HTTPException(status_code=500, detail=f"Erro ao analisar PDF: {exc}") from exc

    _table_cache.save(upload_id, options)
    public = public_options_from_raw(options)

    return TableDetectResponse(
        upload_id=upload_id,
        tables_found=len(public),
        options=public,
        mock_fallback=fallback_used,
        cached=False,
        recommended_table_ids=recommended_table_ids(options),
    )


@router.get("/{upload_id}/table-candidates", response_model=TableDetectResponse)
async def get_table_candidates(
    upload_id: str,
    user_id: str = Depends(get_current_user_id),
):
    upload_id = UploadStore.validate_upload_id(upload_id)
    _upload_store.assert_access(upload_id, user_id)

    options, _ = _table_cache.get(upload_id)
    public = public_options_from_raw(options)
    return TableDetectResponse(
        upload_id=upload_id,
        tables_found=len(public),
        options=public,
        cached=True,
        recommended_table_ids=recommended_table_ids(options),
    )
