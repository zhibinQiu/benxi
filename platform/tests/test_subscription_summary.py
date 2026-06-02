"""订阅收录 AI 摘要 HTML 拼装。"""

from app.services.subscription_summary_service import (
    build_summary_html_block,
    content_html_has_ai_summary,
    plain_text_for_summary,
    prepend_ai_summary_to_content_html,
)


def test_prepend_ai_summary_and_replace():
    html = "<p>正文段落</p>"
    merged = prepend_ai_summary_to_content_html(html, "第一句。\n\n第二句。")
    assert content_html_has_ai_summary(merged)
    assert "第一句。" in merged
    assert "<p>正文段落</p>" in merged
    assert merged.index("subscription-ai-summary") < merged.index("正文段落")

    updated = prepend_ai_summary_to_content_html(merged, "新摘要内容。")
    assert updated.count("subscription-ai-summary") == 1
    assert "新摘要内容。" in updated
    assert "第一句。" not in updated


def test_plain_text_for_summary_includes_title_and_body():
    plain = plain_text_for_summary(
        title="测试标题",
        html_body="<p>正文<strong>加粗</strong></p>",
        fallback_summary="RSS 摘要",
    )
    assert "测试标题" in plain
    assert "加粗" in plain
