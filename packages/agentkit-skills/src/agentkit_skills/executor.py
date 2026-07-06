"""Skill 工具执行器 — 统一 dispatch 入口。"""

from __future__ import annotations

from typing import Any

from agentkit_skills.registry import get_skill as _get_skill
from agentkit_skills.types import (
    SkillDefinition,
    SkillInvocationContext,
    SkillInvocationResult,
    SkillReadiness,
)


class SkillNotFoundError(LookupError):
    """Skill 或 tool 不存在。"""


class SkillNotReadyError(PermissionError):
    """Skill 未就绪或无权限。"""


async def invoke_skill_definition(
    defn: SkillDefinition,
    ctx: SkillInvocationContext,
    *,
    tool_name: str,
    params: dict[str, Any] | None = None,
    admin_invoke: bool = False,
) -> SkillInvocationResult:
    """对已知 SkillDefinition 执行 tool dispatch。"""
    if defn.readiness == SkillReadiness.DISABLED:
        raise SkillNotReadyError(f"Skill `{defn.name}` 已禁用")
    if defn.readiness == SkillReadiness.NO_PERMISSION and not admin_invoke:
        raise SkillNotReadyError(f"无权限使用 skill `{defn.name}`")

    tool = next((t for t in defn.tools if t.name == tool_name), None)
    if not tool:
        raise SkillNotFoundError(f"Skill `{defn.name}` 无工具 `{tool_name}`")
    if not tool.handler:
        raise SkillNotReadyError(f"工具 `{defn.name}.{tool_name}` 尚未实现 handler")

    ctx.skill_name = defn.name
    return await tool.handler(ctx, dict(params or {}))


async def invoke_skill_tool(
    ctx: SkillInvocationContext,
    *,
    skill_name: str,
    tool_name: str,
    params: dict[str, Any] | None = None,
    admin_invoke: bool = False,
) -> SkillInvocationResult:
    """从注册表查找 Skill 并 dispatch tool（便捷入口）。"""
    defn = _get_skill(skill_name)
    if not defn:
        raise SkillNotFoundError(f"Skill 不存在: {skill_name}")
    return await invoke_skill_definition(
        defn, ctx, tool_name=tool_name, params=params, admin_invoke=admin_invoke
    )
