"""文档格式标签。"""

from app.core.document_format import version_file_format_label


def test_format_from_extension():
    assert version_file_format_label("报告.pdf") == "pdf"
    assert version_file_format_label("说明.docx") == "word"
    assert version_file_format_label("notes.txt") == "txt"


def test_format_from_mime():
    assert version_file_format_label("file", "application/pdf") == "pdf"
