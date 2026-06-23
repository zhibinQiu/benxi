"""Skill 注册表 API 层 — 统一列表、内置启停、工具试调用。"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.models.org import User
from app.schemas.agent_skill import (
    SkillInvokeOut,
    SkillKindOut,
    SkillReadinessOut,
    SkillSourceOut,
    UnifiedSkillOut,
)
from app.skills.catalog import list_all_skill_definitions, set_builtin_binding
from app.skills.executor import invoke_skill_tool
from app.skills.types import SkillInvocationContext, SkillReadiness, SkillSource


def _skill_kind(defn) -> SkillKindOut:
    if defn.source == SkillSource.BUILTIN:
        return SkillKindOut.BUILTIN
    return SkillKindOut.DEVELOPED


def _to_unified(defn) -> UnifiedSkillOut:
    enabled = defn.readiness not in (
        SkillReadiness.DISABLED,
        SkillReadiness.NO_PERMISSION,
    )
    if defn.source == SkillSource.BUILTIN:
        enabled = defn.readiness != SkillReadiness.DISABLED
    return UnifiedSkillOut(
        name=defn.name,
        title=defn.title,
        description=defn.description,
        source=SkillSourceOut(defn.source.value),
        kind=_skill_kind(defn),
        enabled=enabled,
        readiness=SkillReadinessOut(defn.readiness.value),
        feature_id=defn.feature_id,
        permission_code=defn.permission_code,
        route=defn.route,
        orchestrated_tools=list(defn.orchestrated_tools),
        skill_id=defn.skill_id,
        source_type=defn.source_type,
    )


def list_unified_skills(
    db: Session,
    *,
    user: User | None = None,
    include_disabled: bool = True,
) -> list[UnifiedSkillOut]:
    rows = list_all_skill_definitions(
        db, user=user, admin_view=True, include_disabled=include_disabled, catalog_only=True
    )
    return [_to_unified(defn) for defn in rows]


async def invoke_skill(
    db: Session,
    user: User,
    *,
    skill_name: str,
    tool_name: str,
    params: dict[str, Any] | None = None,
) -> SkillInvokeOut:
    ctx = SkillInvocationContext(db=db, user=user)
    result = await invoke_skill_tool(
        ctx,
        skill_name=skill_name,
        tool_name=tool_name,
        params=params,
        admin_invoke=True,
    )
    return SkillInvokeOut(
        ok=result.ok,
        summary=result.summary,
        data=result.data,
        error=result.error,
    )


def patch_builtin_skill(db: Session, name: str, *, enabled: bool) -> UnifiedSkillOut:
    from app.core.exceptions import not_found
    from app.skills.catalog import get_merged_skill_definition
    from app.skills.registry import get_skill

    if not get_skill(name):
        raise not_found(f"内置 skill `{name}` 不存在")
    set_builtin_binding(db, name, enabled=enabled)
    defn = get_merged_skill_definition(db, name, admin_view=True)
    assert defn is not None
    return _to_unified(defn)
