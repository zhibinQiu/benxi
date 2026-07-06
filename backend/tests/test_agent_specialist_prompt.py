"""子智能体 resident prompt 测试。"""

from __future__ import annotations

from app.core.agent_resident import build_specialist_resident_prompt


def test_specialist_prompts_are_scoped_and_compact():
    platform = build_specialist_resident_prompt("platform")
    report = build_specialist_resident_prompt("report")
    assert "document" in platform.lower() or "文档" in platform
    assert "report" in report.lower()
