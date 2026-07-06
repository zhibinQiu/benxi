"""PDF 文本层检测与解析器推断。"""

from __future__ import annotations

import pytest

from app.integrations.article_pdf_export import markdown_text_to_pdf_bytes
from app.integrations.pdf_text_layer import pdf_has_extractable_text
from app.services.knowledge_parser_service import infer_parser_for_upload_file


def test_reportlab_pdf_detected_without_text_extraction():
    pdf = markdown_text_to_pdf_bytes("短标题", "正文")
    assert b"ReportLab" in pdf[:2048]
    assert pdf_has_extractable_text(pdf) is True


def test_infer_parser_uses_deepdoc_for_platform_generated_pdf():
    pdf = markdown_text_to_pdf_bytes(
        "测试",
        "## 章节\n\n平台 Markdown 转 PDF 应使用 DeepDOC，以生成引用页截图。",
    )
    parser, layout = infer_parser_for_upload_file(
        "article.pdf", "application/pdf"
    )
    assert parser == "naive"
    assert layout == "DeepDOC"


def test_is_ocr_layout_failure_detects_paddleocr_pdf_error():
    from app.services.knowledge_sync_job_service import _is_ocr_layout_failure

    detail = (
        '12:28:07 [ERROR][Exception]: PaddleOCR API error: 500 - '
        '{"error":"PaddleOCR failed to recognize PDF"}'
    )
    assert _is_ocr_layout_failure(detail) is True
