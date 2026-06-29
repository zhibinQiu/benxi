"""子智能体 resident prompt 测试。"""

from __future__ import annotations

from app.core.agent_resident import build_specialist_resident_prompt


def test_specialist_prompt_shorter_than_monolith():
    mono = __import__(
        "app.core.agent_resident", fromlist=["build_ai_home_resident_prompt"]
    ).build_ai_home_resident_prompt()
    research = build_specialist_resident_prompt("research")
    platform = build_specialist_resident_prompt("platform")
    diagram = build_specialist_resident_prompt("diagram")
    report = build_specialist_resident_prompt("report")
    assert len(research) < len(mono) + 80
    assert "knowledge_retrieve" in research
    assert "list_document_folders" in platform
    assert "mermaid-diagram" in diagram
    assert "report-feasibility" in report or "templates/outline" in report
