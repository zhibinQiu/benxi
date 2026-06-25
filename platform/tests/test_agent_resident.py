"""常驻层 prompt 约束。"""

from __future__ import annotations

from app.core.agent_resident import build_ai_home_resident_prompt


def test_resident_prompt_is_compact_and_has_guardrails():
    text = build_ai_home_resident_prompt()
    assert len(text) < 600
    assert "小析" in text
    assert "文档库" in text
    assert "以记忆为准" in text
    assert "禁止" in text
