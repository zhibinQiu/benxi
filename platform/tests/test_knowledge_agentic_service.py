"""Agentic RAG 编排与 JSON 解析。"""

from unittest.mock import patch

from app.services.knowledge_agentic_service import (
    _parse_llm_json,
    _unique_queries,
    agentic_enabled,
    gather_for_knowledge_qa,
)


def test_parse_llm_json_from_fence():
    raw = '说明\n```json\n{"sufficient": true, "gaps": ""}\n```'
    data = _parse_llm_json(raw)
    assert data is not None
    assert data["sufficient"] is True


def test_unique_queries_dedupes():
    out = _unique_queries(["A", "a", "B", "  "], limit=3)
    assert out == ["A", "B"]


def test_gather_qa_fallback_without_llm(monkeypatch):
    monkeypatch.setattr(
        "app.services.knowledge_agentic_service.agentic_enabled",
        lambda: False,
    )

    class _FakeDb:
        pass

    class _FakeUser:
        id = "00000000-0000-0000-0000-000000000001"

    with patch(
        "app.services.knowledge_agentic_tools.retrieve_hits_for_qa",
        return_value=([], "none"),
    ):
        result = gather_for_knowledge_qa(
            _FakeDb(),
            _FakeUser(),
            [],
            "测试问题",
        )
    assert result.plan_reasoning == "单路检索"
    assert result.sub_questions == ["测试问题"]


def test_agentic_enabled_respects_config(monkeypatch):
    monkeypatch.setattr(
        "app.services.knowledge_agentic_service.is_configured",
        lambda: True,
    )
    monkeypatch.setattr(
        "app.services.knowledge_agentic_service.get_settings",
        lambda: type("S", (), {"knowledge_agentic_enabled": False})(),
    )
    assert agentic_enabled() is False
