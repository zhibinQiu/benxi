"""引用溯源：优先 KnowFlow 切片图；兜底从平台 PDF 裁剪区域并加半透明高亮。"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# 与前端 ComparePdfPreview 的 modify 高亮一致（rgba 234,179,8）
_HIGHLIGHT_COLOR = (1.0, 0.84, 0.0)
_HIGHLIGHT_OPACITY = 0.38
_CROP_MARGIN_PT = 14


def _normalize_pair(a: float, b: float, size: float) -> tuple[float, float]:
    lo = min(a, b) * size
    hi = max(a, b) * size
    return lo, hi


def ragflow_bbox_to_fitz_rect(
    bbox: list[float],
    page_width: float,
    page_height: float,
):
    """RAGFlow/KnowFlow positions[1:5]：left, right, top, bottom（0~1 或 0~1000 归一化）。"""
    try:
        import fitz
    except ImportError as e:
        raise RuntimeError("pymupdf 未安装") from e

    nums = [float(x) for x in bbox[:4]]
    if len(nums) < 4 or any(not __import__("math").isfinite(n) for n in nums):
        return None

    left, right, top, bottom = nums
    if left > right:
        left, right = right, left
    if top > bottom:
        top, bottom = bottom, top

    pw = float(page_width)
    ph = float(page_height)
    max_v = max(left, right, top, bottom)

    if max_v <= 1.05:
        sx, sy = pw, ph
    elif max_v <= 1000:
        sx, sy = pw / 1000.0, ph / 1000.0
    else:
        sx = sy = 1.0

    x0 = left * sx
    x1 = right * sx
    ty0 = top * sy
    ty1 = bottom * sy
    rect = fitz.Rect(x0, ph - ty1, x1, ph - ty0)
    if rect.width > 2 and rect.height > 2:
        return rect
    return None


def bbox_to_fitz_rect(
    bbox: list[float],
    page_width: float,
    page_height: float,
    *,
    bbox_format: str = "auto",
):
    """将 OCR / 归一化 bbox 转为 PyMuPDF Rect（左下角原点）。"""
    fmt = (bbox_format or "auto").strip().lower()
    if fmt in ("ragflow", "ragflow_lrtb", "lrtb"):
        return ragflow_bbox_to_fitz_rect(bbox, page_width, page_height)

    try:
        import fitz
    except ImportError as e:
        raise RuntimeError("pymupdf 未安装") from e

    nums = [float(x) for x in bbox[:4]]
    if len(nums) < 4 or any(not __import__("math").isfinite(n) for n in nums):
        return None

    x0, y0, x1, y1 = nums
    pw = float(page_width)
    ph = float(page_height)
    max_v = max(abs(x0), abs(y0), abs(x1), abs(y1))
    min_v = min(x0, y0, x1, y1)

    if fmt == "auto" and max_v <= 1000 and min_v >= 0:
        if nums[0] <= nums[1] and nums[2] <= nums[3]:
            rag_rect = ragflow_bbox_to_fitz_rect(bbox, pw, ph)
            if rag_rect and rag_rect.width > 4 and rag_rect.height > 4:
                return rag_rect

    if max_v <= 1.05 and min_v >= 0:
        x0, x1 = _normalize_pair(x0, x1, pw)
        ty0, ty1 = _normalize_pair(y0, y1, ph)
        return fitz.Rect(x0, ph - ty1, x1, ph - ty0)

    if max_v <= 1000 and min_v >= 0:
        sx = pw / 1000.0
        sy = ph / 1000.0
        x0, x1 = _normalize_pair(x0, x1, sx)
        ty0, ty1 = _normalize_pair(y0, y1, sy)
        return fitz.Rect(x0, ph - ty1, x1, ph - ty0)

    if y0 <= y1 and max_v > 1.05:
        top = min(y0, y1)
        bottom = max(y0, y1)
        return fitz.Rect(min(x0, x1), ph - bottom, max(x0, x1), ph - top)

    rect = fitz.Rect(min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1))
    if rect.width > 1 and rect.height > 1:
        return rect
    return None


def _apply_pdf_highlight_annot(page, rect) -> None:
    """在页面上绘制半透明高亮块（get_pixmap 可稳定渲染，优于 highlight annot）。"""
    try:
        shape = page.new_shape()
        shape.draw_rect(rect)
        shape.finish(
            color=_HIGHLIGHT_COLOR,
            fill=_HIGHLIGHT_COLOR,
            fill_opacity=_HIGHLIGHT_OPACITY,
            width=0.75,
            stroke_opacity=0.85,
        )
        shape.commit()
    except Exception:
        page.draw_rect(
            rect,
            color=_HIGHLIGHT_COLOR,
            width=1.0,
            overlay=True,
        )


def apply_image_highlight_wash(
    image_bytes: bytes,
    content_type: str = "image/jpeg",
) -> tuple[bytes, str]:
    """KnowFlow 切片图整图即为引用区域，叠加半透明黄层模拟高亮注释。"""
    if not image_bytes:
        return image_bytes, content_type

    try:
        import fitz
    except ImportError:
        return image_bytes, content_type

    ct = (content_type or "image/jpeg").split(";")[0].strip().lower()
    filetype = "jpeg"
    if "png" in ct:
        filetype = "png"
    elif "webp" in ct:
        filetype = "webp"

    try:
        doc = fitz.open(stream=image_bytes, filetype=filetype)
    except Exception:
        return image_bytes, content_type

    try:
        if doc.page_count < 1:
            return image_bytes, content_type
        page = doc[0]
        rect = page.rect
        shape = page.new_shape()
        inset = fitz.Rect(
            rect.x0 + 2,
            rect.y0 + 2,
            rect.x1 - 2,
            rect.y1 - 2,
        )
        shape.draw_rect(inset)
        shape.finish(
            color=_HIGHLIGHT_COLOR,
            fill=_HIGHLIGHT_COLOR,
            fill_opacity=0.22,
            width=3.5,
            stroke_opacity=0.95,
        )
        shape.commit()
        pix = page.get_pixmap(alpha=False)
        out_type = "image/png" if filetype == "png" else "image/jpeg"
        out_bytes = pix.tobytes("png" if filetype == "png" else "jpeg")
        return out_bytes, out_type
    except Exception as exc:
        logger.debug("切片图高亮叠加失败: %s", exc)
        return image_bytes, content_type
    finally:
        doc.close()


def _clip_rect_for_bbox(page_rect, highlight_rect, *, margin: float = _CROP_MARGIN_PT):
    import fitz

    m = float(margin)
    clip = fitz.Rect(
        max(page_rect.x0, highlight_rect.x0 - m),
        max(page_rect.y0, highlight_rect.y0 - m),
        min(page_rect.x1, highlight_rect.x1 + m),
        min(page_rect.y1, highlight_rect.y1 + m),
    )
    if clip.width > 4 and clip.height > 4:
        return clip
    return None


def render_pdf_page_image(
    pdf_bytes: bytes,
    *,
    page_num: int = 1,
    bbox: list[float] | None = None,
    bbox_format: str = "auto",
    highlight_bbox: bool = True,
    crop_to_bbox: bool = True,
    highlight_text: str | None = None,
    zoom: float = 2.0,
) -> tuple[bytes, str]:
    """渲染 PDF 页为 PNG；有 bbox 时裁剪到引用区域（同 KnowFlow 切片图）并加半透明高亮。"""
    if not pdf_bytes or not pdf_bytes.startswith(b"%PDF"):
        raise ValueError("无效的 PDF 内容")

    try:
        import fitz  # pymupdf
    except ImportError as e:
        raise RuntimeError("pymupdf 未安装，无法渲染引用页截图") from e

    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    try:
        if doc.page_count < 1:
            raise ValueError("PDF 无页面")
        page_index = max(0, min(doc.page_count - 1, int(page_num or 1) - 1))
        page = doc[page_index]
        pw = float(page.rect.width)
        ph = float(page.rect.height)

        highlight_rect = None
        if bbox and len(bbox) >= 4 and highlight_bbox:
            highlight_rect = bbox_to_fitz_rect(bbox, pw, ph, bbox_format=bbox_format)
            if highlight_rect and highlight_rect.width > 4 and highlight_rect.height > 4:
                _apply_pdf_highlight_annot(page, highlight_rect)

        if highlight_rect is None and highlight_text:
            query = " ".join((highlight_text or "").split())
            if len(query) >= 4:
                try:
                    rects = page.search_for(query[:120])
                except Exception:
                    rects = []
                if not rects and len(query) > 8:
                    rects = page.search_for(query[:40])
                if rects:
                    highlight_rect = rects[0]
                    if highlight_bbox:
                        _apply_pdf_highlight_annot(page, highlight_rect)

        matrix = fitz.Matrix(zoom, zoom)
        clip = None
        if highlight_rect and crop_to_bbox:
            clip = _clip_rect_for_bbox(page.rect, highlight_rect)
        if clip is not None:
            pix = page.get_pixmap(matrix=matrix, clip=clip, alpha=False)
        else:
            pix = page.get_pixmap(matrix=matrix, alpha=False)
        return pix.tobytes("png"), "image/png"
    finally:
        doc.close()
