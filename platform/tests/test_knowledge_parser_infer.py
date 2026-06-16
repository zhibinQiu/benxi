"""上传文件类型 → KnowFlow 解析器推断。"""

from app.services.knowledge_parser_service import infer_parser_for_upload_file


def test_txt_uses_default_layout_parser():
    parser, layout = infer_parser_for_upload_file("notes.txt", "text/plain")
    assert parser == "naive"
    assert layout == "DeepDOC"


def test_md_uses_default_layout_parser():
    parser, layout = infer_parser_for_upload_file("readme.md", "text/markdown")
    assert parser == "naive"
    assert layout == "DeepDOC"


def test_pdf_uses_default_parser():
    parser, layout = infer_parser_for_upload_file("report.pdf", "application/pdf")
    assert parser == "naive"
    assert layout == "DeepDOC"


def test_pdf_with_text_layer_uses_deepdoc():
    from app.integrations.article_pdf_export import markdown_text_to_pdf_bytes

    pdf = markdown_text_to_pdf_bytes("标题", "这是一段可提取文本。" * 5)
    parser, layout = infer_parser_for_upload_file(
        "text.pdf", "application/pdf"
    )
    assert parser == "naive"
    assert layout == "DeepDOC"


def test_docx_uses_layout_parser():
    parser, layout = infer_parser_for_upload_file(
        "memo.docx",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )
    assert parser == "naive"
    assert layout == "DeepDOC"


def test_ppt_uses_presentation_parser():
    parser, layout = infer_parser_for_upload_file(
        "slides.pptx",
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    )
    assert parser == "presentation"
    assert layout == "DeepDOC"


def test_png_uses_picture_parser():
    parser, layout = infer_parser_for_upload_file("scan.png", "image/png")
    assert parser == "picture"
    assert layout == "DeepDOC"


def test_xlsx_uses_table_parser_with_layout():
    parser, layout = infer_parser_for_upload_file(
        "data.xlsx",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    assert parser == "table"
    assert layout == "DeepDOC"
