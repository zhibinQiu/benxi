"""文章 PDF 导出。"""

from app.integrations.article_pdf_export import markdown_text_to_pdf_bytes
from app.integrations.html_document_export import html_body_to_pdf_bytes


def test_markdown_text_to_pdf_bytes_valid_pdf():
    md = "# 标题\n\n## 正文\n\n" + "这是测试正文。" * 40 + "\n\n---\n\n- **原文**：https://example.com"
    data = markdown_text_to_pdf_bytes("标题", md)
    assert data.startswith(b"%PDF")
    assert len(data) > 800


def test_html_body_to_pdf_bytes_from_html():
    html = "<p>" + "网页正文内容。" * 50 + "</p>"
    name, content, mime = html_body_to_pdf_bytes(
        "测试文章",
        html,
        summary="摘要",
        link="https://example.com/a",
        source_label="测试源",
        allow_refetch=False,
    )
    assert name.endswith(".pdf")
    assert mime == "application/pdf"
    assert content.startswith(b"%PDF")
