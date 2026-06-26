from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


class AbcJobStore:
    """Repositório em memória para status de jobs ABC (demo / fase 1)."""

    def __init__(self) -> None:
        self._jobs: dict[str, dict[str, Any]] = {}

    def init_job(
        self,
        upload_id: str,
        *,
        user_id: str,
        filename: str,
        status: str = "uploading",
        message: str | None = None,
    ) -> dict[str, Any]:
        now = datetime.now(timezone.utc).isoformat()
        job = {
            "upload_id": upload_id,
            "user_id": user_id,
            "filename": filename,
            "status": status,
            "message": message,
            "created_at": now,
            "updated_at": now,
        }
        self._jobs[upload_id] = job
        return job

    def get(self, upload_id: str) -> dict[str, Any] | None:
        return self._jobs.get(upload_id)

    def update(self, upload_id: str, **fields: Any) -> dict[str, Any] | None:
        job = self._jobs.get(upload_id)
        if not job:
            return None
        job.update(fields)
        job["updated_at"] = datetime.now(timezone.utc).isoformat()
        return job

    def list_for_user(self, user_id: str) -> list[dict[str, Any]]:
        return [j for j in self._jobs.values() if str(j.get("user_id")) == str(user_id)]
