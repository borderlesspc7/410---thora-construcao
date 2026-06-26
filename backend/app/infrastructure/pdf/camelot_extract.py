from __future__ import annotations

import base64
import logging
from pathlib import Path
from typing import Any

import fitz

from app.infrastructure.pdf.table_extract import (
    count_nonempty_rows,
    normalize_table_rows,
    preview_text_for_rows,
)
from app.infrastructure.pdf.thumbnail import crop_thumbnail_base64

logger = logging.getLogger(__name__)

_camelot_module = None


def _get_camelot():
    global _camelot_module
    if _camelot_module is None:
        import camelot as camelot_module

        _camelot_module = camelot_module
    return _camelot_module


def _camelot_table_to_rows(camelot_table: Any) -> list[list[Any]]:
    df = camelot_table.df
    rows: list[list[Any]] = []
    for _, row in df.iterrows():
        rows.append(
            [
                str(cell).strip() if cell is not None and str(cell) != "nan" else ""
                for cell in row.tolist()
            ]
        )
    return rows


def detect_camelot_options(file_path: Path, max_pages: int) -> list[dict[str, Any]]:
    doc = fitz.open(str(file_path))
    try:
        page_count = doc.page_count
    finally:
        doc.close()

    pages_spec = f"1-{min(page_count, max_pages)}"
    tables = _get_camelot().read_pdf(str(file_path), pages=pages_spec, flavor="lattice")
    if len(tables) == 0:
        return []

    options: list[dict[str, Any]] = []
    for idx, table in enumerate(tables):
        page_num = int(table.page)
        x0, y0, x1, y1 = table._bbox
        camelot_rows = _camelot_table_to_rows(table)
        nonempty = count_nonempty_rows(camelot_rows)
        if nonempty < 3:
            continue
        try:
            b64 = crop_thumbnail_base64(file_path, page_num, (x0, y0, x1, y1))
        except Exception as exc:
            logger.warning("thumbnail Camelot falhou: %s", exc)
            b64 = ""
        from services.budget_scoring import score_budget_table_likelihood
        from app.infrastructure.pdf.table_extract import preview_rows_for_api

        budget_score = score_budget_table_likelihood(camelot_rows)
        options.append(
            {
                "id": f"table-{idx}",
                "pagina": page_num,
                "coordenadas": [x0, y0, x1, y1],
                "imagem_base64": b64,
                "nome_tabela": f"Tabela {idx + 1} (Pág {page_num}, {nonempty} linhas)",
                "num_pagina": page_num,
                "preview_texto": preview_text_for_rows(camelot_rows)
                or "Visualização disponível via imagem.",
                "row_count": nonempty,
                "budget_score": budget_score,
                "is_budget_likely": budget_score >= 18,
                "preview_rows": preview_rows_for_api(camelot_rows),
                "rows": camelot_rows,
                "source": "camelot",
            }
        )
    return options
