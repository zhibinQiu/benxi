"""常驻层 prompt 约束。"""

from __future__ import annotations

from app.core.agent_resident import build_ai_home_resident_prompt


def test_resident_prompt_has_guardrails_and_communication_style():
    text = build_ai_home_resident_prompt()
    assert len(text) < 1800
    assert "小析" in text
    assert "search_tools" in text
    assert "Skill 加载规则" in text
    assert "429" in text
    assert "禁止" in text
    assert "工具结束后单独生成" in text
    assert "当前会话窗口" in text
    assert "系统操作" in text
    assert "温柔" in text
    assert "mermaid" in text
