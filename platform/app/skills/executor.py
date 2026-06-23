"""Skill 工具执行器 — 统一 dispatch 入口。"""

from __future__ import annotations

from typing import Any

from app.core.exceptions import bad_request, forbidden, not_found
from app.skills.catalog import get_merged_skill_definition
from app.skills.types import (
    SkillInvocationContext,
    SkillInvocationResult,
    SkillReadiness,
    SkillSource,
)


async def invoke_skill_tool(
    ctx: SkillInvocationContext,
    *,
    skill_name: str,
    tool_name: str,
    params: dict[str, Any] | None = None,
    admin_invoke: bool = False,
) -> SkillInvocationResult:
    """调用指定 skill 的 tool；uploaded skill 返回 SKILL.md 内容。"""
    defn = get_merged_skill_definition(
        ctx.db, skill_name, user=ctx.user, admin_view=admin_invoke
    )
    if not defn:
        raise not_found(f"Skill 不存在: {skill_name}")
    if defn.readiness == SkillReadiness.DISABLED:
        raise bad_request(f"Skill `{skill_name}` 已禁用")
    if defn.readiness == SkillReadiness.NO_PERMISSION and not admin_invoke:
        raise forbidden(f"无权限使用 skill `{skill_name}`")

    if defn.source == SkillSource.UPLOADED:
        return await _invoke_uploaded_skill(ctx, defn.skill_id, skill_name)

    tool = next((t for t in defn.tools if t.name == tool_name), None)
    if not tool:
        raise not_found(f"Skill `{skill_name}` 无工具 `{tool_name}`")
    if not tool.handler:
        raise bad_request(f"工具 `{skill_name}.{tool_name}` 尚未实现 handler")
    return await tool.handler(ctx, dict(params or {}))


async def _invoke_uploaded_skill(
    ctx: SkillInvocationContext,
    skill_id,
    skill_name: str,
) -> SkillInvocationResult:
    from app.services.agent_skill_service import get_skill_file_content

    if not skill_id:
        raise not_found(f"上传 skill `{skill_name}` 缺少 ID")
    file_out = get_skill_file_content(ctx.db, skill_id, "SKILL.md")
    body = file_out.text or ""
    return SkillInvocationResult(
        True,
        f"已加载上传 skill `{skill_name}` 的 SKILL.md",
        data={"skill_name": skill_name, "skill_md": body},
    )
