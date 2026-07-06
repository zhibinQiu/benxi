# pip install agentkit-skills
"""演示 Skill 插件的注册与调用。"""

import asyncio

from agentkit_skills import (
    SkillDefinition,
    SkillInvocationContext,
    SkillInvocationResult,
    SkillReadiness,
    SkillSource,
    SkillToolSpec,
    invoke_skill_tool,
    register_skill,
)


async def echo_handler(ctx: SkillInvocationContext, params: dict) -> SkillInvocationResult:
    """回显参数的测试 handler。"""
    msg = params.get("message", "hello")
    return SkillInvocationResult(ok=True, summary=f"Echo: {msg}")


# 注册 Skill
register_skill(SkillDefinition(
    name="echo-skill",
    title="回显测试",
    description="测试用回显 Skill",
    source=SkillSource.BUILTIN,
    readiness=SkillReadiness.READY,
    tools=(SkillToolSpec(
        name="echo",
        description="回显输入消息",
        handler=echo_handler,
    ),),
))

# 调用 Skill
result = asyncio.run(invoke_skill_tool(
    SkillInvocationContext(conversation_id="c1"),
    skill_name="echo-skill",
    tool_name="echo",
    params={"message": "AgentKit 通用化"},
))
print(f"调用结果: ok={result.ok}, summary={result.summary}")
