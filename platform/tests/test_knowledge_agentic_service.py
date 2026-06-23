"""Agentic RAG 编排与 JSON 解析。"""

import uuid
from unittest.mock import MagicMock, patch

from app.core.llm_parse import parse_llm_json
from app.services.knowledge_agentic_service import (
    RESULT_MARKER,
    _unique_queries,
    agentic_enabled,
    gather_for_knowledge_qa,
    iter_gather_for_knowledge_qa,
    iter_gather_for_report,
)
from app.services.knowledge_agentic_tools import ToolResult


def test_parse_llm_json_from_fence():
    raw = '说明\n```json\n{"sufficient": true, "gaps": ""}\n```'
    data = parse_llm_json(raw)
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


def test_gather_qa_second_round_uses_supplemental_queries(monkeypatch):
    """材料不足时第 2 轮应执行补充检索，而非一直停在「第 1 轮」。"""
    doc_id = uuid.UUID("00000000-0000-0000-0000-000000000101")
    eval_calls = {"n": 0}

    class _FakeDb:
        pass

    class _FakeUser:
        id = uuid.UUID("00000000-0000-0000-0000-000000000001")

    settings = type(
        "S",
        (),
        {
            "knowledge_agentic_enabled": True,
            "knowledge_agentic_max_rounds": 2,
            "knowledge_agentic_qa_max_sub_questions": 4,
            "knowledge_retrieval_top_k": 5,
        },
    )()

    monkeypatch.setattr(
        "app.services.knowledge_agentic_service.agentic_enabled",
        lambda: True,
    )
    monkeypatch.setattr(
        "app.services.knowledge_agentic_service.get_settings",
        lambda: settings,
    )
    monkeypatch.setattr(
        "app.services.knowledge_agentic_service._plan_qa_sub_questions",
        lambda **_: (["子问题 A"], "首轮规划"),
    )

    def _eval_sufficiency(**_):
        eval_calls["n"] += 1
        if eval_calls["n"] == 1:
            return False, "材料不足", ["补充子问题 B"]
        return True, "", []

    monkeypatch.setattr(
        "app.services.knowledge_agentic_service._evaluate_qa_sufficiency",
        _eval_sufficiency,
    )

    toolkit = MagicMock()
    toolkit.kg_planning_context.return_value = ToolResult(
        "kg_context", True, "无图谱", data=None
    )
    toolkit.retrieve.return_value = ToolResult(
        "retrieve", True, "命中 1 段", data={"mode": "hybrid"}
    )
    toolkit.accumulated_local_hits = [{"chunk_id": "c1", "content": "片段"}]

    with patch(
        "app.services.knowledge_agentic_service.KnowledgeAgenticToolkit",
        return_value=toolkit,
    ):
        events = list(
            iter_gather_for_knowledge_qa(
                _FakeDb(),
                _FakeUser(),
                [doc_id],
                "测试问题",
            )
        )

    retrieve_titles = [
        ev["title"]
        for ev in events
        if isinstance(ev, dict)
        and ev.get("phase") == "tool_call"
        and ev.get("tool") == "retrieve"
    ]
    assert retrieve_titles == [
        "第 1 轮 · 知识库检索",
        "第 2 轮 · 知识库检索",
    ]
    assert toolkit.retrieve.call_count == 2
    assert eval_calls["n"] == 2

    result = next(ev[RESULT_MARKER] for ev in events if isinstance(ev, dict) and RESULT_MARKER in ev)
    assert result.rounds_used == 2


def test_gather_report_second_round_uses_supplemental_queries(monkeypatch):
    """报告生成材料不足时第 2 轮应执行补充检索。"""
    doc_id = uuid.UUID("00000000-0000-0000-0000-000000000102")
    eval_calls = {"n": 0}

    class _FakeDb:
        pass

    class _FakeUser:
        id = uuid.UUID("00000000-0000-0000-0000-000000000001")

    settings = type(
        "S",
        (),
        {
            "knowledge_agentic_enabled": True,
            "knowledge_agentic_max_rounds": 2,
            "knowledge_agentic_report_max_sub_questions": 6,
            "knowledge_retrieval_top_k": 5,
        },
    )()

    monkeypatch.setattr(
        "app.services.knowledge_agentic_service.agentic_enabled",
        lambda: True,
    )
    monkeypatch.setattr(
        "app.services.knowledge_agentic_service.get_settings",
        lambda: settings,
    )
    monkeypatch.setattr(
        "app.services.knowledge_agentic_service._plan_report_gathering",
        lambda **_: (["本地 A"], [], "规划"),
    )

    def _eval(**kwargs):
        eval_calls["n"] += 1
        if eval_calls["n"] == 1:
            return False, "不足", ["补充本地 B"], []
        return True, None, [], []

    monkeypatch.setattr(
        "app.services.knowledge_agentic_service._evaluate_report_sufficiency",
        _eval,
    )

    toolkit = MagicMock()
    toolkit.kg_planning_context.return_value = ToolResult(
        "kg_context", True, "无", data=None
    )
    toolkit.version_metadata.return_value = ToolResult(
        "version_metadata", True, "无", data={}
    )
    toolkit.retrieve.return_value = ToolResult(
        "retrieve", True, "命中", data={"mode": "hybrid"}
    )
    toolkit.web_search.return_value = ToolResult("web_search", True, "命中", data=[])
    toolkit.accumulated_local_hits = [{"chunk_id": "c1", "content": "x"}]
    toolkit.accumulated_web_items = []
    toolkit.doc_titles.return_value = {}

    with patch(
        "app.services.knowledge_agentic_service.KnowledgeAgenticToolkit",
        return_value=toolkit,
    ):
        events = list(
            iter_gather_for_report(
                _FakeDb(),
                _FakeUser(),
                [doc_id],
                message="写报告",
                topic="主题",
                intent="initial",
                history=[],
                web_enabled=False,
            )
        )

    retrieve_titles = [
        ev["title"]
        for ev in events
        if isinstance(ev, dict)
        and ev.get("phase") == "tool_call"
        and ev.get("tool") == "retrieve"
    ]
    assert retrieve_titles == [
        "第 1 轮 · 知识库检索",
        "第 2 轮 · 知识库检索",
    ]
    assert toolkit.retrieve.call_count == 2
    assert eval_calls["n"] == 2

    result = next(
        ev[RESULT_MARKER] for ev in events if isinstance(ev, dict) and RESULT_MARKER in ev
    )
    assert result.rounds_used == 2
