"""发展技能 SKILL.md 自动注入。"""

from __future__ import annotations

from app.services.agent_tools import (
    build_skill_md_context_block,
    maybe_inject_skill_md,
)


def test_build_skill_md_context_block():
    block = build_skill_md_context_block("demo-skill", "# 说明\n直接运行 main.py")
    assert "demo-skill" in block
    assert "无需 load_uploaded_skill" in block
    assert "main.py" in block


def test_build_skill_md_context_block_instruction_only():
    block = build_skill_md_context_block(
        "mermaid-diagram",
        "# Mermaid",
        has_script=False,
    )
    assert "勿" in block and "run_skill_script" in block


def test_maybe_inject_skill_md_skips_duplicate():
    loop_state: dict = {"injected_skill_mds": ["demo-skill"]}
    messages = [{"role": "user", "content": "hi"}]

    class _Db:
        pass

    out = maybe_inject_skill_md(_Db(), None, loop_state, messages, "demo-skill")
    assert out == messages
    assert len(out) == 1
