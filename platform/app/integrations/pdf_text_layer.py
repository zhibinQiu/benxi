"""PDF 文本层检测：区分扫描件与可选 Plain Text 解析的文本 PDF。"""

from __future__ import annotations


def is_platform_generated_pdf(content: bytes) -> bool:
    """平台/订阅导入用 ReportLab 生成的 PDF（有内嵌字体，PaddleOCR 常失败）。"""
    if not content.startswith(b"%PDF"):
        return False
    head = content[:4096]
    return b"ReportLab" in head or b"reportlab" in head.lower()


def _is_reportlab_text_pdf(content: bytes) -> bool:
    return is_platform_generated_pdf(content)


def pdf_has_extractable_text(content: bytes, *, min_chars: int = 40) -> bool:
    """PDF 是否含足够可提取文本（有文本层则无需 PaddleOCR 版面识别）。"""
    if not content or not content.startswith(b"%PDF"):
        return False
    if _is_reportlab_text_pdf(content):
        return True
    try:
        import fitz
    except ImportError:
        return False
    try:
        doc = fitz.open(stream=content, filetype="pdf")
    except Exception:
        return False
    try:
        if doc.page_count < 1:
            return False
        total = 0
        pages_to_scan = min(doc.page_count, 8)
        for idx in range(pages_to_scan):
            total += len(doc[idx].get_text("text").strip())
            if total >= min_chars:
                return True
        return total >= min_chars
    finally:
        doc.close()
