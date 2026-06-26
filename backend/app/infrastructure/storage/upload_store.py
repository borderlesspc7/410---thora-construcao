from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

from fastapi import HTTPException

from app.config import UPLOAD_DIR


class UploadStore:
    """Persistência local de PDFs e metadados de upload."""

    def __init__(self, base_dir: Path | None = None) -> None:
        self._base_dir = base_dir or UPLOAD_DIR
        self._base_dir.mkdir(parents=True, exist_ok=True)

    def _pdf_path(self, upload_id: str) -> Path:
        return self._base_dir / f"{upload_id}.pdf"

    def _meta_path(self, upload_id: str) -> Path:
        return self._base_dir / f".meta_{upload_id}.json"

    @staticmethod
    def validate_upload_id(upload_id: str) -> str:
        try:
            uuid.UUID(upload_id)
            return upload_id
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="upload_id inválido") from exc

    def save_pdf(
        self,
        upload_id: str,
        pdf_bytes: bytes,
        *,
        user_id: str,
        filename: str,
        content_type: str,
    ) -> None:
        self._pdf_path(upload_id).write_bytes(pdf_bytes)
        meta = {
            "uploadId": upload_id,
            "userId": user_id,
            "filename": filename,
            "content_type": content_type,
        }
        self._meta_path(upload_id).write_text(
            json.dumps(meta, ensure_ascii=False),
            encoding="utf-8",
        )

    def load_meta(self, upload_id: str) -> dict[str, Any]:
        path = self._meta_path(upload_id)
        if not path.is_file():
            return {}
        return json.loads(path.read_text(encoding="utf-8"))

    def pdf_path(self, upload_id: str) -> Path:
        return self._pdf_path(upload_id)

    def ensure_pdf(self, upload_id: str) -> Path:
        path = self._pdf_path(upload_id)
        if not path.is_file():
            raise HTTPException(status_code=404, detail=f"Upload não encontrado: {upload_id}")
        return path

    def assert_access(self, upload_id: str, user_id: str) -> None:
        meta = self.load_meta(upload_id)
        owner = meta.get("userId")
        if not owner:
            return
        if str(owner) != str(user_id):
            raise HTTPException(status_code=403, detail="Acesso negado")
