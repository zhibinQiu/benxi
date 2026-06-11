"""上传文件类型 → KnowFlow 解析器推断。"""

from app.services.knowledge_parser_service import infer_parser_for_upload_file


def test_txt_uses_naive_plain_text():
    parser, layout = infer_parser_for_upload_file("notes.txt", "text/plain")
    assert parser == "naive"
    assert layout == "Plain Text"


def test_md_uses_naive_plain_text():
    parser, layout = infer_parser_for_upload_file("readme.md", "text/markdown")
    assert parser == "naive"
    assert layout == "Plain Text"


def test_pdf_uses_default_parser():
    parser, layout = infer_parser_for_upload_file("report.pdf", "application/pdf")
    assert parser == "naive"
    assert layout == "Plain Text"
