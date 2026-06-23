"""Agent 工具上下文压缩测试。"""

from __future__ import annotations

import json

from app.core.agent_tool_context import (
    append_retrieval_context,
    build_retrieval_context_block,
    compress_tool_result_for_loop,
    inject_retrieval_context_message,
    trim_agent_loop_messages,
)


def test_compress_tool_result_strips_large_context():
    payload = {
        "ok": True,
        "summary": "命中 3 段",
        "data": {
            "context": "材料" * 2000,
            "hit_count": 3,
            "hits": [{"snippet": "a"}, {"snippet": "b"}],
        },
    }
    raw = json.dumps(payload, ensure_ascii=False)
    out = compress_tool_result_for_loop(raw, max_chars=1200)
    body = json.loads(out)
    data = body.get("data") or {}
    assert "context" not in data
    assert data.get("context_chars", 0) > 0
    assert data.get("context_preview")
    assert data.get("hits_count") == 2
    assert len(out) <= 1200


def test_append_retrieval_context_and_inject():
    loop_state: dict = {}
    append_retrieval_context(loop_state, "[1] 第一段材料")
    append_retrieval_context(loop_state, "[2] 第二段材料")
    block = build_retrieval_context_block(loop_state)
    assert "[1]" in block
    assert "[2]" in block

    messages = [{"role": "system", "content": "你是助手"}]
    out = inject_retrieval_context_message(messages, loop_state)
    assert any("【已检索材料】" in str(m.get("content") or "") for m in out)


def test_trim_agent_loop_messages_compresses_old_tools():
    old = json.dumps(
        {"ok": True, "summary": "旧结果", "data": {"context": "x" * 5000}},
        ensure_ascii=False,
    )
    recent = json.dumps(
        {"ok": True, "summary": "新结果", "data": {"context": "y" * 3000}},
        ensure_ascii=False,
    )
    rows = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "问题"},
        {"role": "assistant", "content": "调用工具", "tool_calls": [{"id": "1"}]},
        {"role": "tool", "tool_call_id": "1", "content": old},
        {"role": "assistant", "content": "再调用", "tool_calls": [{"id": "2"}]},
        {"role": "tool", "tool_call_id": "2", "content": recent},
    ]
    out = trim_agent_loop_messages(rows, max_total_chars=8000, keep_full_tool_results=1)
    assert len(out) >= 4
    tool_contents = [m["content"] for m in out if m.get("role") == "tool"]
    assert len(tool_contents) == 2
    assert len(tool_contents[0]) < len(old)
