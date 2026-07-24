"""工作时记忆（Harness）与系统记忆分离测试。"""

from __future__ import annotations

from app.services.agent_working_memory import WORKING_MEMORY_MARKER, WorkingMemory


def test_working_memory_format_distinct_from_system_memory():
    wm = WorkingMemory()
    wm.add("规划方案：双碳智能体", "Agent RAG 匹配（`carbon`）", agent_id="orchestrator")
    wm.add("未能完成，交还调度", "缺少有效证据", agent_id="carbon")
    block = wm.format_prompt_block()
    assert WORKING_MEMORY_MARKER in block
    assert "【用户记忆】" not in block
    assert "carbon" in block
    assert "非 MEMORY.md" in block


def test_working_memory_dedupes_identical_steps():
    wm = WorkingMemory()
    wm.add("开始执行", "第 1 轮", agent_id="carbon")
    wm.add("开始执行", "第 1 轮", agent_id="carbon")
    assert len(wm.steps) == 1
