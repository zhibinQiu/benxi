"""Agent 工具去重与本轮上下文标识。"""

from __future__ import annotations

from app.core.agent_tool_context import (
    build_turn_executed_tools_context,
    lookup_cached_tool_result,
    record_executed_tool_call,
    tool_call_fingerprint,
)


def test_tool_call_fingerprint_stable_for_same_args():
    fp1 = tool_call_fingerprint("web_search", '{"query":"碳价"}')
    fp2 = tool_call_fingerprint("web_search", {"query": "碳价"})
    assert fp1 == fp2


def test_tool_call_fingerprint_differs_by_tool_or_args():
    base = tool_call_fingerprint("web_search", '{"query":"碳价"}')
    assert base != tool_call_fingerprint("knowledge_retrieve", '{"query":"碳价"}')
    assert base != tool_call_fingerprint("web_search", '{"query":"电价"}')


def test_record_and_lookup_cached_tool_result():
    loop_state: dict = {}
    record_executed_tool_call(
        loop_state,
        tool_name="web_search",
        raw_args='{"query":"北京碳价"}',
        result_text='{"ok":true,"summary":"命中 3 条"}',
        summary="命中 3 条",
        step_id="agent-tool-abc",
    )
    hit = lookup_cached_tool_result(
        loop_state, "web_search", '{"query":"北京碳价"}'
    )
    assert hit is not None
    assert "命中 3 条" in hit


def test_build_turn_executed_tools_context_lists_calls():
    loop_state = {
        "executed_tool_calls": [
            {
                "tool_name": "knowledge_retrieve",
                "args_preview": '{"query":"政策"}',
                "summary": "命中 2 条",
                "step_id": "agent-tool-x",
            }
        ]
    }
    block = build_turn_executed_tools_context(loop_state)
    assert "本轮对话已执行工具" in block
    assert "knowledge_retrieve" in block
    assert "勿重复调用" in block
