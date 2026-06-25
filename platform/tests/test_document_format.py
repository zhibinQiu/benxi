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


def test_is_compareable_file():
    from app.core.document_format import is_compareable_file

    assert is_compareable_file("报告.pdf", "application/pdf")
    assert is_compareable_file("说明.docx")
    assert is_compareable_file("notes.txt", "text/plain")
    assert is_compareable_file("data.csv", "text/csv")
    assert is_compareable_file("sheet.xlsx")
    assert is_compareable_file("page.html", "text/html")
    assert is_compareable_file("scan.png", "image/png")
    assert not is_compareable_file("bundle.zip")
    assert not is_compareable_file("archive.rar")


def test_assert_allowed_upload_format():
    from app.core.document_format import assert_allowed_upload_format, is_allowed_upload_format
    import pytest
    from app.core.exceptions import AppError

    for name in ("a.pdf", "b.docx", "c.xlsx", "d.txt", "e.md"):
        assert is_allowed_upload_format(name)
        assert_allowed_upload_format(name)

    assert not is_allowed_upload_format("slide.pptx")
    assert not is_allowed_upload_format("photo.png", "image/png")
    with pytest.raises(AppError):
        assert_allowed_upload_format("slide.pptx")
