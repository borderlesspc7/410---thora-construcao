from __future__ import annotations

import logging
import re
from typing import Any

from app.infrastructure.pdf.table_extract import count_nonempty_rows, normalize_table_rows

logger = logging.getLogger(__name__)

_ITEM_CODE_RE = re.compile(r"^\d+(\.\d+)+")
_MAJOR_GROUP_RE = re.compile(r"^(\d+)\s+(.+)$")
_SUBTOTAL_RE = re.compile(r"\bitem\b", re.IGNORECASE)

MIN_SEGMENT_ROWS = 3


def _first_cell_text(row: list[Any]) -> str:
    for cell in row:
        text = str(cell).strip() if cell is not None else ""
        if text:
            return text.replace("\n", " ")
    return ""


def _nonempty_cell_count(row: list[Any]) -> int:
    return sum(1 for cell in row if cell is not None and str(cell).strip())


def _is_column_header_row(row: list[Any]) -> bool:
    text = " ".join(str(c).lower() for c in row if c is not None and str(c).strip())
    if not text:
        return False
    has_desc = "descri" in text
    has_item = "item" in text
    has_code = "código" in text or "codigo" in text
    return has_desc and (has_item or has_code)


def _is_major_group_header_row(row: list[Any]) -> bool:
    first = _first_cell_text(row)
    if not first or _ITEM_CODE_RE.match(first):
        return False
    match = _MAJOR_GROUP_RE.match(first)
    if not match:
        return False
    title = match.group(2).strip()
    letters = [ch for ch in title if ch.isalpha()]
    if len(letters) < 5:
        return False
    upper_ratio = sum(1 for ch in letters if ch.isupper()) / len(letters)
    if upper_ratio < 0.65:
        return False
    if _nonempty_cell_count(row) > 3:
        return False
    return True


def _is_subtotal_row(row: list[Any]) -> bool:
    cells = [str(c).strip() for c in row if c is not None and str(c).strip()]
    if not cells:
        return False
    joined = " ".join(cells).lower()
    if "total do grupo" in joined:
        return True
    if _SUBTOTAL_RE.search(joined) and any("r$" in c.lower() for c in cells):
        return True
    return False


def find_column_header_index(rows: list[list[Any]]) -> int | None:
    for idx, row in enumerate(rows[:6]):
        if _is_column_header_row(row):
            return idx
    return None


def find_section_split_starts(rows: list[list[Any]]) -> list[int]:
    """Índices onde começa uma nova planilha/grupo principal (ex.: '2 ADMINISTRAÇÃO…')."""
    starts: list[int] = []
    header_idx = find_column_header_index(rows)

    for idx, row in enumerate(rows):
        if header_idx is not None and idx <= header_idx:
            continue
        if _is_major_group_header_row(row):
            if not starts or starts[-1] != idx:
                starts.append(idx)

    if not starts:
        return [0]

    if header_idx is not None and header_idx not in starts:
        starts.insert(0, header_idx)
    elif 0 not in starts and (header_idx is None or header_idx > 0):
        # Mantém conteúdo antes do primeiro grupo detectado (ex.: cabeçalho institucional).
        first_group = min(i for i in starts if _is_major_group_header_row(rows[i]))
        if first_group > 0:
            starts.insert(0, 0)

    return sorted(set(starts))


def _rows_bbox(
    pdf_table: Any,
    start: int,
    end: int,
    fallback: tuple[float, float, float, float] | None,
) -> tuple[float, float, float, float] | None:
    table_bbox = getattr(pdf_table, "bbox", None)
    table_rows = getattr(pdf_table, "rows", None) or []
    if not table_rows or end > len(table_rows) or start >= end:
        return fallback if fallback else table_bbox

    try:
        top = float(table_rows[start].bbox[1])
        bottom = float(table_rows[end - 1].bbox[3])
        if table_bbox:
            x0, _, x1, _ = table_bbox
            return (float(x0), top, float(x1), bottom)
        row_bbox = table_rows[start].bbox
        return (float(row_bbox[0]), top, float(row_bbox[2]), bottom)
    except Exception as exc:
        logger.debug("bbox parcial falhou: %s", exc)
        return fallback if fallback else table_bbox


def _segment_name(rows: list[list[Any]], segment_index: int) -> str:
    for row in rows[:4]:
        first = _first_cell_text(row)
        if _is_major_group_header_row(row):
            return first
        if first and not _is_column_header_row(row) and len(first) > 4:
            return first[:80]
    return f"Seção {segment_index + 1}"


def split_pdfplumber_table(
    pdf_table: Any,
    page_index: int,
    *,
    table_seq: int,
    min_rows: int = MIN_SEGMENT_ROWS,
) -> list[dict[str, Any]]:
    """Divide tabela pdfplumber quando a página contém vários grupos de orçamento."""
    try:
        raw = pdf_table.extract()
    except Exception as exc:
        logger.debug("split extract falhou: %s", exc)
        return []

    if not raw:
        return []

    rows = normalize_table_rows(raw)
    if count_nonempty_rows(rows) < min_rows + 2:
        return []

    split_starts = find_section_split_starts(rows)
    if len(split_starts) <= 1:
        return []

    header_idx = find_column_header_index(rows)
    fallback_bbox = getattr(pdf_table, "bbox", None)
    fallback_tuple = tuple(float(v) for v in fallback_bbox[:4]) if fallback_bbox else None
    segments: list[dict[str, Any]] = []

    for seg_idx, start in enumerate(split_starts):
        end = split_starts[seg_idx + 1] if seg_idx + 1 < len(split_starts) else len(rows)
        seg_rows = [list(r) for r in rows[start:end]]

        if header_idx is not None and start > header_idx and not _is_column_header_row(seg_rows[0]):
            header_row = rows[header_idx]
            if not any(_is_column_header_row(r) for r in seg_rows[:2]):
                seg_rows.insert(0, list(header_row))
            start_for_bbox = start
        else:
            start_for_bbox = start

        if count_nonempty_rows(seg_rows) < min_rows:
            continue

        bbox = _rows_bbox(pdf_table, start_for_bbox, end, fallback_tuple)
        name = _segment_name(seg_rows, seg_idx)
        segments.append(
            {
                "rows": seg_rows,
                "bbox": bbox,
                "table_id": f"page_{page_index}_table_{table_seq}_sec_{seg_idx}",
                "section_name": name,
            }
        )

    if len(segments) <= 1:
        return []

    logger.info(
        "pág %s: tabela %s dividida em %s seções",
        page_index + 1,
        table_seq,
        len(segments),
    )
    return segments
