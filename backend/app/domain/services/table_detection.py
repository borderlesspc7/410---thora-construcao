from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from services.budget_scoring import score_budget_table_likelihood

from app.config import (
    DETECT_TABLES_MAX_CANDIDATES,
    DETECT_TABLES_MAX_PAGES,
    DISABLE_CAMELOT,
)
from app.infrastructure.pdf.camelot_extract import detect_camelot_options
from app.infrastructure.pdf.table_extract import (
    count_nonempty_rows,
    extract_tables_from_pdf,
    guess_table_name_from_preview,
    preview_rows_for_api,
    preview_text_for_rows,
)
from app.infrastructure.pdf.thumbnail import (
    crop_pdfplumber_bbox_base64,
    crop_thumbnail_base64,
    page_thumbnail_base64,
)

logger = logging.getLogger(__name__)

BUDGET_LIKELY_MIN_SCORE = 18


def _rows_fingerprint(entry: dict[str, Any]) -> str:
    rows = entry.get("rows") or []
    parts: list[str] = []
    for row in rows[:4]:
        parts.append("|".join(str(c).strip().lower() for c in row if str(c).strip()))
    return "#".join(parts)[:320]


def _bbox_overlap_ratio(
    a: tuple[float, ...] | list[float],
    b: tuple[float, ...] | list[float],
) -> float:
    if len(a) < 4 or len(b) < 4:
        return 0.0
    ax0, ay0, ax1, ay1 = float(a[0]), float(a[1]), float(a[2]), float(a[3])
    bx0, by0, bx1, by1 = float(b[0]), float(b[1]), float(b[2]), float(b[3])
    ix0, iy0 = max(ax0, bx0), max(ay0, by0)
    ix1, iy1 = min(ax1, bx1), min(ay1, by1)
    iw, ih = max(0.0, ix1 - ix0), max(0.0, iy1 - iy0)
    inter = iw * ih
    if inter <= 0:
        return 0.0
    area_a = max(1.0, (ax1 - ax0) * (ay1 - ay0))
    area_b = max(1.0, (bx1 - bx0) * (by1 - by0))
    return inter / min(area_a, area_b)


def _is_near_duplicate(candidate: dict[str, Any], kept: list[dict[str, Any]]) -> bool:
    cand_fp = _rows_fingerprint(candidate)
    cand_page = int(candidate.get("pagina") or 0)
    cand_bbox = candidate.get("bbox")

    for other in kept:
        if int(other.get("pagina") or 0) != cand_page:
            continue
        other_bbox = other.get("bbox")
        if cand_fp and cand_fp == _rows_fingerprint(other):
            if not cand_bbox or not other_bbox:
                return True
            if _bbox_overlap_ratio(cand_bbox, other_bbox) >= 0.35:
                return True
            continue
        if cand_bbox and other_bbox and _bbox_overlap_ratio(cand_bbox, other_bbox) >= 0.82:
            return True
    return False


def _dedupe_near_duplicates(scored: list[tuple[int, dict[str, Any]]]) -> list[dict[str, Any]]:
    """Remove só duplicatas da mesma região — mantém várias tabelas distintas na mesma página."""
    sorted_entries = sorted(scored, key=lambda item: -item[0])
    kept: list[dict[str, Any]] = []
    for _score, entry in sorted_entries:
        if _is_near_duplicate(entry, kept):
            continue
        kept.append(entry)
    return kept


def _table_index_on_page(table_id: str, page_num: int) -> int:
    import re

    match = re.search(r"table_(\d+)$", str(table_id or ""))
    if match:
        return int(match.group(1)) + 1
    match = re.search(r"^table-(\d+)$", str(table_id or ""))
    if match:
        return int(match.group(1)) + 1
    return page_num


def _attach_table_thumbnail(
    file_path: Path,
    option: dict[str, Any],
    bbox: Any,
    page_num: int,
) -> None:
    try:
        if bbox and len(bbox) >= 4:
            coords = tuple(float(v) for v in bbox[:4])
            if option.get("source") == "camelot":
                option["imagem_base64"] = crop_thumbnail_base64(file_path, page_num, coords)
            else:
                option["imagem_base64"] = crop_pdfplumber_bbox_base64(file_path, page_num, coords)
            option["coordenadas"] = list(coords)
            return
        option["imagem_base64"] = page_thumbnail_base64(file_path, page_num)
    except Exception as exc:
        logger.warning("thumbnail tabela pág %s: %s", page_num, exc)
        option["imagem_base64"] = None


def _enrich_option_metadata(option: dict[str, Any], rows: list[list[Any]]) -> None:
    budget_score = score_budget_table_likelihood(rows)
    nonempty = count_nonempty_rows(rows)
    option["row_count"] = nonempty
    option["budget_score"] = budget_score
    option["is_budget_likely"] = budget_score >= BUDGET_LIKELY_MIN_SCORE
    option["preview_rows"] = preview_rows_for_api(rows)


def _pdfplumber_detect_options(
    file_path: Path,
    min_nonempty_rows: int = 8,
    max_pages: int | None = DETECT_TABLES_MAX_PAGES,
) -> list[dict[str, Any]]:
    try:
        all_tables = extract_tables_from_pdf(file_path, max_pages=max_pages)
    except Exception as exc:
        logger.warning("pdfplumber detect: %s", exc)
        return []

    scored: list[tuple[int, dict[str, Any]]] = []
    for table in all_tables:
        rows = table.get("rows") or []
        nonempty = count_nonempty_rows(rows)
        budget_score = score_budget_table_likelihood(rows)
        min_rows_required = 4 if budget_score >= 35 else min_nonempty_rows
        if nonempty < min_rows_required:
            continue
        page_num = int(table.get("page") or 1)
        table_id = str(table.get("table_id") or f"page_{page_num}_table_0")
        table_idx = _table_index_on_page(table_id, page_num)
        preview = preview_text_for_rows(rows)
        section_name = str(table.get("section_name") or "").strip()
        if section_name:
            name = section_name[:72]
        else:
            name = guess_table_name_from_preview(preview, len(scored) + 1)
        option: dict[str, Any] = {
            "id": table_id,
            "pagina": page_num,
            "num_pagina": page_num,
            "nome_tabela": f"{name} (Pág {page_num}, tabela {table_idx}, {nonempty} linhas)",
            "preview_texto": preview,
            "coordenadas": None,
            "source": "pdfplumber",
            "row_count": nonempty,
            "budget_score": budget_score,
            "is_budget_likely": budget_score >= BUDGET_LIKELY_MIN_SCORE,
            "preview_rows": preview_rows_for_api(rows),
            "rows": rows,
            "bbox": table.get("bbox"),
        }
        _attach_table_thumbnail(file_path, option, table.get("bbox"), page_num)
        scored.append((budget_score, option))

    likely = [entry for score, entry in scored if score >= BUDGET_LIKELY_MIN_SCORE]
    fallback_limit = min(40, DETECT_TABLES_MAX_CANDIDATES)
    pool = likely if likely else [entry for _, entry in sorted(scored, key=lambda x: -x[0])[:fallback_limit]]
    options = _dedupe_near_duplicates([(int(o.get("budget_score") or 0), o) for o in pool])
    if len(options) > DETECT_TABLES_MAX_CANDIDATES:
        options = options[:DETECT_TABLES_MAX_CANDIDATES]
    if not likely and options:
        logger.warning(
            "detect-tables: nenhuma tabela com score alto; retornando %s candidatos",
            len(options),
        )
    options.sort(
        key=lambda o: (
            int(o.get("pagina") or 0),
            str(o.get("id") or ""),
            -int(o.get("budget_score") or 0),
            -int(o.get("row_count") or 0),
        )
    )
    return options


def detect_table_options(file_path: Path) -> tuple[list[dict[str, Any]], bool]:
    """Detecta candidatos: pdfplumber primeiro, Camelot como fallback."""
    options = _pdfplumber_detect_options(file_path)
    if options:
        logger.info("detect-tables: %s candidato(s) via pdfplumber", len(options))
        return options, False

    if DISABLE_CAMELOT:
        logger.warning("detect-tables: pdfplumber vazio e Camelot desativado")
        return [], False

    logger.info("detect-tables: tentando Camelot (máx. %s págs)", DETECT_TABLES_MAX_PAGES)
    try:
        options = detect_camelot_options(file_path, DETECT_TABLES_MAX_PAGES)
        for option in options:
            rows = option.get("rows") or []
            _enrich_option_metadata(option, rows)
        options = _dedupe_near_duplicates([(int(o.get("budget_score") or 0), o) for o in options])
    except Exception as exc:
        logger.warning("detect-tables: Camelot falhou: %s", exc)
        options = []

    return options, True


def public_options_from_raw(options: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Remove rows completas da resposta HTTP; mantém preview_rows e metadados."""
    public: list[dict[str, Any]] = []
    for option in options:
        entry = {k: v for k, v in option.items() if k not in {"rows", "bbox"}}
        if "preview_rows" not in entry and option.get("rows"):
            entry["preview_rows"] = preview_rows_for_api(option["rows"])
        public.append(entry)
    return public


def recommended_table_ids(options: list[dict[str, Any]]) -> list[str]:
    return [str(o["id"]) for o in options if o.get("is_budget_likely") and o.get("id")]


def strip_rows_from_options(options: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return public_options_from_raw(options)
