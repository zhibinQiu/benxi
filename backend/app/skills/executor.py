"""Skill 工具执行器 — catalog 解析 + agentkit dispatch。"""

from __future__ import annotations

from typing import Any

from agentkit_skills.executor import (
    SkillNotFoundError,
    SkillNotReadyError,
    invoke_skill_definition,
)

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

    if defn.source == SkillSource.UPLOADED:
        return await _invoke_uploaded_skill(ctx, defn.skill_id, skill_name)

    try:
        return await invoke_skill_definition(
            defn,
            ctx,
            tool_name=tool_name,
            params=params,
            admin_invoke=admin_invoke,
        )
    except SkillNotFoundError as exc:
        raise not_found(str(exc)) from exc
    except SkillNotReadyError as exc:
        msg = str(exc)
        if "已禁用" in msg:
            raise bad_request(msg) from exc
        if "无权限" in msg:
            raise forbidden(msg) from exc
        raise bad_request(msg) from exc


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
