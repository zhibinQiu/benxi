"""父编排只委托、不直执。"""

from __future__ import annotations

import json

from app.services.agent_tool_loop import (
    _parent_must_delegate_error,
    _reject_parent_direct_steps,
    _should_delegate_to_subagent,
)


def test_orchestrator_must_not_direct_web_search():
    state = {"agent_id": "orchestrator"}
    assert _should_delegate_to_subagent(state, "web_search") is True
    assert _should_delegate_to_subagent(state, "invoke_context_subagent") is False


def test_isolated_subagent_can_direct_web_search():
    state = {"agent_id": "orchestrator", "isolated_subagent": True}
    assert _should_delegate_to_subagent(state, "web_search") is False


def test_specialist_can_direct_domain_tools():
    state = {"agent_id": "carbon"}
    assert _should_delegate_to_subagent(state, "web_search") is False


def test_parent_must_delegate_error_guides_to_subagent():
    raw = _parent_must_delegate_error("web_search")
    body = json.loads(raw)
    assert body["ok"] is False
    assert "invoke_context_subagent" in body["summary"]
    assert "kind=search" in body["summary"]


def test_reject_parent_direct_steps_indexes_by_tool_call_id():
    steps = [
        {"tool": "web_search", "arguments": {"query": "x"}, "tool_call_id": "c1"},
    ]
    out = _reject_parent_direct_steps(steps)
    assert "c1" in out
    assert out["c1"]["ok"] is False
    assert "invoke_context_subagent" in out["c1"]["summary"]
