"""常驻层 prompt 约束。"""

from __future__ import annotations

from app.core.agent_resident import build_ai_home_resident_prompt


def test_resident_prompt_is_compact_and_has_guardrails():
    text = build_ai_home_resident_prompt()
    assert "小析" in text
    assert "绝对禁止" in text
    assert "平台文档库" in text
    assert "浏览器书签" in text
    assert len(text) < 1600
