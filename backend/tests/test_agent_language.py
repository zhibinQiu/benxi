"""语言策略与 workflow 智能体标注。"""

from __future__ import annotations

from app.core.agent_language import (
    assistant_language_rules,
    looks_like_chinese,
    stamp_workflow_agent,
)


def test_looks_like_chinese_prefers_cjk():
    assert looks_like_chinese("孩子想学金融怎么办？") is True
    assert looks_like_chinese("How should my kid learn finance?") is False
    assert looks_like_chinese("") is True


def test_assistant_language_rules_zh_requires_chinese_thinking():
    text = assistant_language_rules(user_message="请帮我查一下就业数据")
    assert "简体中文" in text
    assert "思考" in text


def test_stamp_workflow_agent_from_loop_state():
    data: dict = {"phase": "thinking_delta", "delta": "x"}
    stamp_workflow_agent(data, loop_state={"agent_id": "report"})
    assert data["agent_id"] == "report"
    assert data["agent_title"] == "报告撰写"
