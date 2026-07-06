"""agentkit-skills 注册与调用测试。"""

import pytest

from agentkit_skills import (
    SkillDefinition,
    SkillInvocationContext,
    SkillInvocationResult,
    SkillReadiness,
    SkillSource,
    SkillToolSpec,
    SkillRegistry,
    invoke_skill_tool,
)


@pytest.mark.asyncio
async def test_invoke_registered_skill():
    registry = SkillRegistry()

    async def echo_handler(_ctx, params):
        return SkillInvocationResult(True, params.get("q", ""))

    registry.register(
        SkillDefinition(
            name="echo",
            title="Echo",
            description="",
            source=SkillSource.BUILTIN,
            readiness=SkillReadiness.READY,
            tools=(SkillToolSpec("run", "echo", handler=echo_handler),),
        )
    )

    out = await invoke_skill_tool(
        SkillInvocationContext(),
        skill_name="echo",
        tool_name="run",
        params={"q": "hi"},
        registry=registry,
    )
    assert out.ok and out.summary == "hi"
