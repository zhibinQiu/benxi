"""agent_runtime — 规划/对话运行时日期时间注入。"""

import re

from app.core.agent_runtime import build_runtime_context, format_planning_datetime_block


def test_format_planning_datetime_block():
    text = format_planning_datetime_block()
    assert text.startswith("【当前日期时间】")
    assert re.search(r"\d{4}-\d{2}-\d{2}", text)
    assert "周" in text
    assert "CST" in text


def test_build_runtime_context_includes_weekday():
    text = build_runtime_context(channel="report")
    assert "【运行时】" in text
    assert "当前时间：" in text
    assert "周" in text
    assert "report" in text
