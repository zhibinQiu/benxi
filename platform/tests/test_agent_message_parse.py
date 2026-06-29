"""agent_message_parse 单元测试。"""

from __future__ import annotations

from app.core.agent_message_parse import (
    DsmlStreamFilter,
    assistant_content_is_deliverable,
    content_has_dsml_markup,
    extract_embedded_tool_calls,
    has_mermaid_deliverable,
    looks_like_internal_agent_content,
    normalize_llm_assistant_message,
    sanitize_agent_user_reply,
)

SAMPLE_DSML = (
    "数据在 L246 行，格式是 ohlc = [[...]]。需要改用 re.DOTALL 并调整正则。\n\n"
    "<\uff5c\uff5cDSML\uff5c\uff5ctool_calls>\n"
    '<\uff5c\uff5cDSML\uff5c\uff5cinvoke name="update_uploaded_skill_file">\n'
    '<\uff5c\uff5cDSML\uff5c\uff5cparameter name="file_path" string="true">main.py</\uff5c\uff5cDSML\uff5c\uff5cparameter>\n'
    '<\uff5c\uff5cDSML\uff5c\uff5cparameter name="content" string="true">print("ok")</\uff5c\uff5cDSML\uff5c\uff5cparameter>\n'
    '<\uff5c\uff5cDSML\uff5c\uff5cparameter name="skill_name" string="true">carbon-price-scraper</\uff5c\uff5cDSML\uff5c\uff5cparameter>\n'
    "</\uff5c\uff5cDSML\uff5c\uff5cinvoke>\n"
    "</\uff5c\uff5cDSML\uff5c\uff5ctool_calls>"
)


def test_extract_embedded_tool_calls_from_dsml():
    stripped, calls = extract_embedded_tool_calls(SAMPLE_DSML)
    assert len(calls) == 1
    assert calls[0]["function"]["name"] == "update_uploaded_skill_file"
    args = calls[0]["function"]["arguments"]
    assert "main.py" in args
    assert "carbon-price-scraper" in args
    assert "DSML" not in stripped


def test_normalize_llm_assistant_message_promotes_embedded_calls():
    msg = normalize_llm_assistant_message({"role": "assistant", "content": SAMPLE_DSML})
    assert msg.get("tool_calls")
    assert msg["tool_calls"][0]["function"]["name"] == "update_uploaded_skill_file"


def test_sanitize_agent_user_reply_strips_internal_debug():
    assert sanitize_agent_user_reply(SAMPLE_DSML) == ""


def test_sanitize_agent_user_reply_keeps_user_facing_answer():
    text = "全国碳市场最新收盘价为 **82.41 元/吨**（2026-06-23）。"
    assert sanitize_agent_user_reply(text) == text


def test_looks_like_internal_agent_content():
    assert looks_like_internal_agent_content(SAMPLE_DSML)
    assert not looks_like_internal_agent_content("已创建 skill 并完成抓取。")


def test_has_mermaid_deliverable():
    text = "如下：\n```mermaid\nmindmap\n  root((把大象装进冰箱))\n```"
    assert has_mermaid_deliverable(text)


def test_sanitize_agent_user_reply_preserves_mermaid():
    text = "步骤说明如下：\n```mermaid\nmindmap\n  root((把大象装进冰箱))\n```"
    out = sanitize_agent_user_reply(text)
    assert "mindmap" in out
    assert "```mermaid" in out


def test_assistant_content_is_deliverable_for_instruction_only():
    mermaid = "```mermaid\nmindmap\n  root((test))\n```"
    assert assistant_content_is_deliverable(mermaid, instruction_only_skill=True)
    assert assistant_content_is_deliverable(
        "这是按技能说明生成的完整回答，包含三个步骤说明。",
        instruction_only_skill=True,
    )
    assert not assistant_content_is_deliverable("短", instruction_only_skill=True)


def test_extract_embedded_tool_calls_web_search_dsml():
    pipe = "\uff5c"
    tag = f"{pipe}{pipe}DSML{pipe}{pipe}"
    sample = (
        f"<{tag}tool_calls>\n"
        f'<{tag}invoke name="web_search">\n'
        f'<{tag}parameter name="query" string="true">虚拟电厂 关键技术</{tag}parameter>\n'
        f'<{tag}parameter name="max_items" string="false">8</{tag}parameter>\n'
        f"</{tag}invoke>\n"
        f"</{tag}tool_calls>"
    )
    stripped, calls = extract_embedded_tool_calls(sample)
    assert len(calls) == 1
    assert calls[0]["function"]["name"] == "web_search"
    assert "虚拟电厂" in calls[0]["function"]["arguments"]
    assert not content_has_dsml_markup(stripped)


def test_extract_embedded_tool_calls_ascii_pipe_dsml():
    sample = (
        "<||DSML||invoke name=\"web_search\">\n"
        "<||DSML||parameter name=\"query\" string=\"true\">碳市场</||DSML||parameter>\n"
        "</||DSML||invoke>"
    )
    _, calls = extract_embedded_tool_calls(sample)
    assert len(calls) == 1
    assert calls[0]["function"]["name"] == "web_search"


def test_dsml_stream_filter_strips_markup():
    filt = DsmlStreamFilter()
    pipe = "\uff5c"
    tag = f"{pipe}{pipe}DSML{pipe}{pipe}"
    chunk1 = f"报告摘要\n<{tag}tool_calls>\n<{tag}invoke name=\"web_search\">"
    chunk2 = (
        f'<{tag}parameter name="query" string="true">虚拟电厂</{tag}parameter>'
        f"</{tag}invoke>"
    )
    out1 = filt.feed(chunk1)
    out2 = filt.feed(chunk2)
    tail = filt.flush()
    assert "DSML" not in out1
    assert "DSML" not in out2
    assert "DSML" not in tail
    assert "报告摘要" in out1
