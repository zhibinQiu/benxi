"""已有 Skill 执行失败后的修复上下文注入。"""

from app.core.agent_tool_context import (
    append_skill_repair_context,
    build_skill_repair_context_block,
    inject_retrieval_context_message,
)
from app.services.agent_skill_router import is_inconclusive_skill_conclusion


def test_inconclusive_skill_conclusion_detects_failure_text():
    assert is_inconclusive_skill_conclusion("")
    assert is_inconclusive_skill_conclusion("无法获取价格")
    assert not is_inconclusive_skill_conclusion("上海碳价今日开盘 72.5 元/吨")


def test_skill_repair_context_injected_into_system_message():
    state: dict = {}
    append_skill_repair_context(state, skill_name="demo-skill", reason="脚本退出码 1")
    block = build_skill_repair_context_block(state)
    assert "demo-skill" in block
    assert "update_uploaded_skill_file" in block
    assert "create_skill" in block

    messages = inject_retrieval_context_message(
        [{"role": "system", "content": "base"}],
        state,
    )
    assert any("【Skill 修复" in str(m.get("content") or "") for m in messages)
