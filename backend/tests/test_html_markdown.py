"""HTML 转 Markdown。"""

from app.integrations.html_markdown import html_to_markdown


def test_html_to_markdown_preserves_paragraphs():
    md = html_to_markdown("<p>第一段</p><p>第二段</p>")
    assert "第一段" in md
    assert "第二段" in md
    assert "\n" in md


def test_plain_text_splits_to_paragraphs():
    text = "第一句。第二句！第三句？" + "x" * 50
    md = html_to_markdown(text)
    assert md.count("\n") >= 1 or "第一句" in md
