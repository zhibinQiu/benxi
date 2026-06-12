"""文档对比文本抽取。"""

import uuid

from app.integrations.text_extract import extract_text_from_bytes


def test_extract_plain_text():
    doc_id = uuid.uuid4()
    parsed = extract_text_from_bytes(
        b"line one\n\nline two",
        document_id=doc_id,
        file_name="notes.txt",
        mime_type="text/plain",
    )
    assert parsed.parse_quality == "text_layer"
    assert "line one" in parsed.full_text
    assert "line two" in parsed.full_text


def test_extract_html():
    doc_id = uuid.uuid4()
    parsed = extract_text_from_bytes(
        b"<html><body><p>Hello</p><p>World</p></body></html>",
        document_id=doc_id,
        file_name="page.html",
        mime_type="text/html",
    )
    assert parsed.full_text
    assert "Hello" in parsed.full_text
    assert "World" in parsed.full_text


def test_extract_image_requests_ocr():
    doc_id = uuid.uuid4()
    parsed = extract_text_from_bytes(
        b"\x89PNG\r\n",
        document_id=doc_id,
        file_name="scan.png",
        mime_type="image/png",
    )
    assert parsed.parse_quality == "ocr_required"
    assert parsed.full_text == ""
