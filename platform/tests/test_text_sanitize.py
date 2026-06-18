"""sanitize_db_text helper."""

from app.core.text_sanitize import sanitize_db_text


def test_sanitize_db_text_strips_nul():
    assert sanitize_db_text("a\x00b\x00c") == "abc"
    assert sanitize_db_text(None) == ""
    assert sanitize_db_text("正常文本") == "正常文本"
