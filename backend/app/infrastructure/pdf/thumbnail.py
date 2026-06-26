from __future__ import annotations

import base64
import logging
from pathlib import Path

import fitz

from app.config import (
    TABLE_PREVIEW_MAX_SCALE,
    TABLE_PREVIEW_MIN_SCALE,
    TABLE_PREVIEW_PAGE_SCALE,
    TABLE_PREVIEW_TARGET_WIDTH_PX,
)

logger = logging.getLogger(__name__)


def resolve_matrix_scale_for_bbox(
    bbox: tuple[float, float, float, float],
    *,
    target_width_px: int = TABLE_PREVIEW_TARGET_WIDTH_PX,
    min_scale: float = TABLE_PREVIEW_MIN_SCALE,
    max_scale: float = TABLE_PREVIEW_MAX_SCALE,
) -> float:
    """Calcula escala PyMuPDF para a prévia ter largura alvo em pixels (zoom nítido no frontend)."""
    x0, y0, x1, y1 = bbox
    width_pt = abs(float(x1) - float(x0))
    height_pt = abs(float(y1) - float(y0))
    if width_pt < 1:
        return max(min_scale, 3.0)
    scale_by_width = target_width_px / width_pt
    # Tabelas muito altas: limita escala para não gerar PNG gigante
    if height_pt > 0:
        max_height_px = 4000
        scale_by_height = max_height_px / height_pt
        scale_by_width = min(scale_by_width, scale_by_height)
    return max(min_scale, min(max_scale, scale_by_width))


def _render_clip_png(
    file_path: Path,
    page_num: int,
    rect: fitz.Rect,
    matrix_scale: float,
) -> str:
    doc = fitz.open(str(file_path))
    try:
        page = doc[page_num - 1]
        matrix = fitz.Matrix(matrix_scale, matrix_scale)
        pix = page.get_pixmap(clip=rect, matrix=matrix, alpha=False)
        return base64.b64encode(pix.tobytes("png")).decode("utf-8")
    finally:
        doc.close()


def page_thumbnail_base64(
    file_path: Path,
    page_num: int,
    matrix_scale: float | None = None,
) -> str:
    scale = matrix_scale if matrix_scale is not None else TABLE_PREVIEW_PAGE_SCALE
    doc = fitz.open(str(file_path))
    try:
        page = doc[page_num - 1]
        pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
        return base64.b64encode(pix.tobytes("png")).decode("utf-8")
    finally:
        doc.close()


def crop_pdfplumber_bbox_base64(
    file_path: Path,
    page_num: int,
    bbox: tuple[float, float, float, float],
    matrix_scale: float | None = None,
) -> str:
    """Recorte com bbox pdfplumber: (x0, top, x1, bottom), origem no topo da página."""
    x0, top, x1, bottom = bbox
    rect = fitz.Rect(x0, top, x1, bottom)
    scale = matrix_scale if matrix_scale is not None else resolve_matrix_scale_for_bbox(bbox)
    logger.debug("thumbnail pdfplumber pág %s escala %.2f", page_num, scale)
    return _render_clip_png(file_path, page_num, rect, scale)


def crop_thumbnail_base64(
    file_path: Path,
    page_num: int,
    bbox: tuple[float, float, float, float],
    matrix_scale: float | None = None,
) -> str:
    """Recorte de região da tabela (coordenadas Camelot, origem inferior)."""
    doc = fitz.open(str(file_path))
    try:
        page = doc[page_num - 1]
        x0, y0, x1, y1 = bbox
        rect = fitz.Rect(x0, page.rect.height - y1, x1, page.rect.height - y0)
        # Converte para escala usando dimensões na página PDF
        pdf_bbox = (rect.x0, rect.y0, rect.x1, rect.y1)
        scale = matrix_scale if matrix_scale is not None else resolve_matrix_scale_for_bbox(pdf_bbox)
        logger.debug("thumbnail camelot pág %s escala %.2f", page_num, scale)
    finally:
        doc.close()
    return _render_clip_png(file_path, page_num, rect, scale)
