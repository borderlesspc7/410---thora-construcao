import logging
import uuid

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from app.api.deps import get_current_user_id
from app.config import MAX_FILE_SIZE
from app.domain.schemas.upload import UploadResponse
from app.infrastructure.storage.upload_store import UploadStore

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["uploads"])

_upload_store = UploadStore()


@router.post("/upload", response_model=UploadResponse)
async def upload_pdf(
    file: UploadFile = File(...),
    user_id: str = Depends(get_current_user_id),
):
    if file.content_type != "application/pdf":
        raise HTTPException(status_code=400, detail="Apenas arquivos PDF são permitidos")

    contents = await file.read()
    if len(contents) > MAX_FILE_SIZE:
        max_mb = MAX_FILE_SIZE / 1024 / 1024
        raise HTTPException(
            status_code=413,
            detail=(
                f"Arquivo muito grande. Máximo: {max_mb:.0f}MB. "
                f"Tamanho: {len(contents) / 1024 / 1024:.2f}MB"
            ),
        )

    upload_id = str(uuid.uuid4())
    filename = file.filename or f"{upload_id}.pdf"

    _upload_store.save_pdf(
        upload_id,
        contents,
        user_id=user_id,
        filename=filename,
        content_type=file.content_type or "application/pdf",
    )

    logger.info("PDF salvo: %s (%.2f MB)", upload_id, len(contents) / 1024 / 1024)

    return UploadResponse(
        upload_id=upload_id,
        filename=filename,
        size=len(contents),
        message="Arquivo recebido com sucesso",
    )
