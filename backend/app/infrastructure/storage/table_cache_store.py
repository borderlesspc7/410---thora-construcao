from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.config import CACHE_DIR, DETECT_TABLES_CACHE_VERSION


class TableCacheStore:
    """Cache de candidatos de tabela por upload_id."""

    def __init__(self, base_dir: Path | None = None) -> None:
        self._base_dir = base_dir or CACHE_DIR
        self._base_dir.mkdir(parents=True, exist_ok=True)

    def _path(self, upload_id: str) -> Path:
        return self._base_dir / f"{upload_id}_tables.json"

    def get(self, upload_id: str) -> tuple[list[dict[str, Any]], int]:
        path = self._path(upload_id)
        if not path.is_file():
            return [], 0
        data = json.loads(path.read_text(encoding="utf-8"))
        return data.get("options") or [], int(data.get("version") or 0)

    def save(self, upload_id: str, options: list[dict[str, Any]]) -> None:
        payload = {
            "upload_id": upload_id,
            "version": DETECT_TABLES_CACHE_VERSION,
            "options": options,
        }
        self._path(upload_id).write_text(
            json.dumps(payload, ensure_ascii=False),
            encoding="utf-8",
        )

    def is_valid(self, upload_id: str) -> bool:
        options, version = self.get(upload_id)
        return bool(options) and version >= DETECT_TABLES_CACHE_VERSION
