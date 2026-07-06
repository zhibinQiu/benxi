"""Skill 编写调研上下文管理。"""

from app.core.agent_tool_context import (
    append_skill_explore_context,
    build_skill_explore_context_block,
    has_skill_research_context,
    inject_retrieval_context_message,
)


def test_skill_explore_context_persists_in_system_message():
    state: dict = {}
    append_skill_explore_context(state, "页面快照：碳市场\nURL：https://example.com")
    block = build_skill_explore_context_block(state)
    assert "碳市场" in block
    messages = inject_retrieval_context_message(
        [{"role": "user", "content": "生成 skill"}],
        state,
    )
    system = [m for m in messages if m["role"] == "system"]
    assert system
    assert "Skill 编写调研材料" in system[0]["content"]


def test_has_skill_research_context_requires_explore_for_site_skill():
    state: dict = {}
    assert has_skill_research_context(state, needs_site_research=True) is False
    append_skill_explore_context(state, "探查完成")
    assert has_skill_research_context(state, needs_site_research=True) is True


def test_has_skill_research_context_skips_when_no_site_needed():
    assert has_skill_research_context({}, needs_site_research=False) is True
