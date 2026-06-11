"""文档格式标签。"""

from app.core.document_format import version_file_format_label


def test_format_from_extension():
    assert version_file_format_label("报告.pdf") == "pdf"
    assert version_file_format_label("说明.docx") == "word"
    assert version_file_format_label("notes.txt") == "txt"


def test_format_from_mime():
    assert version_file_format_label("file", "application/pdf") == "pdf"


def test_assert_compatible_version_format():
    from app.core.document_format import assert_compatible_version_format
    import pytest
    from app.core.exceptions import AppError

    assert_compatible_version_format(
        existing_file_name="a.pdf",
        existing_mime="application/pdf",
        new_file_name="b.pdf",
        new_mime="application/pdf",
    )
    with pytest.raises(AppError):
        assert_compatible_version_format(
            existing_file_name="a.pdf",
            existing_mime="application/pdf",
            new_file_name="b.docx",
            new_mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
