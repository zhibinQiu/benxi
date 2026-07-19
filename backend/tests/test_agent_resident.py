"""专精 resident prompt 约束。"""

from __future__ import annotations

from app.core.agent_resident import build_specialist_resident_prompt


def test_orchestrator_resident_prompt_has_guardrails():
    text = build_specialist_resident_prompt("orchestrator")
    assert len(text) < 9000
    assert "小析" in text
    assert "基本原则" in text
    assert "完成用户的要求" in text
    assert "满足用户需求" in text or "编排" in text
    assert "复合任务" in text


def test_platform_resident_prompt_scoped():
    text = build_specialist_resident_prompt("platform")
    assert "基本原则" in text
    assert "完成用户的要求" in text
    assert "专精" in text or "本域" in text
    assert "invoke_skill" in text or "Skill" in text
