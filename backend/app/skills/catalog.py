"""Skill 目录聚合 — 内置 + 上传 + 权限/开关过滤。"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.permissions import user_has_permission
from app.core.report_skill_catalog import REPORT_SKILL_LABELS
from app.features.registry import ensure_plugins_loaded, get_plugin
from app.models.agent_skill import AgentSkill
from app.models.org import User
from app.skills.registry import all_builtin_skills, ensure_skills_loaded
from app.skills.routing import (
    SKILL_DISCOVERY_RULES,
    SKILL_LOADING_RULES,
    format_skill_route_line,
    uploaded_skill_tag,
)
from app.agentkit.skills.search import rank_skills_by_query, skill_query_tokens
from app.skills.types import SkillDefinition, SkillReadiness, SkillSource


def _binding_overrides(db: Session) -> dict[str, bool]:
    from app.models.agent_skill_binding import AgentSkillBinding

    try:
        rows = db.scalars(select(AgentSkillBinding)).all()
        return {row.name: row.enabled for row in rows}
    except Exception:
        db.rollback()
        return {}


def _is_feature_available(defn: SkillDefinition) -> bool:
    if not defn.feature_id:
        return True
    ensure_plugins_loaded()
    plugin = get_plugin(defn.feature_id)
    return bool(plugin and plugin.enabled)


def _effective_readiness(
    defn: SkillDefinition,
    *,
    user: User | None,
    db: Session | None,
    binding_overrides: dict[str, bool],
    admin_view: bool = False,
) -> SkillReadiness:
    if defn.source == SkillSource.BUILTIN:
        if defn.name in binding_overrides and not binding_overrides[defn.name]:
            return SkillReadiness.DISABLED
        if not _is_feature_available(defn):
            return SkillReadiness.DISABLED
        if defn.permission_code and db is not None and user is not None:
            if not admin_view and not user_has_permission(db, user, defn.permission_code):
                return SkillReadiness.NO_PERMISSION
        return defn.readiness
    return SkillReadiness.READY if defn.readiness == SkillReadiness.READY else defn.readiness


def resolve_skill_definition(
    db: Session,
    defn: SkillDefinition,
    *,
    user: User | None = None,
    admin_view: bool = False,
    bindings: dict[str, bool] | None = None,
) -> SkillDefinition:
    """返回带有效 readiness 的副本（frozen dataclass 需重建）。"""
    binding_overrides = bindings if bindings is not None else _binding_overrides(db)
    readiness = _effective_readiness(
        defn, user=user, db=db, binding_overrides=binding_overrides, admin_view=admin_view
    )
    return SkillDefinition(
        name=defn.name,
        title=defn.title,
        description=defn.description,
        source=defn.source,
        tools=defn.tools,
        orchestrated_tools=defn.orchestrated_tools,
        feature_id=defn.feature_id,
        permission_code=defn.permission_code,
        readiness=readiness,
        skill_id=defn.skill_id,
        route=defn.route,
        source_type=defn.source_type,
        catalog_visible=defn.catalog_visible,
        catalog_tier=defn.catalog_tier,
        created_at=defn.created_at,
        use_when=defn.use_when,
        dont_use_when=defn.dont_use_when,
        output=defn.output,
    )


def list_mcp_skill_definitions(
    db: Session, *, include_disabled: bool = False
) -> list[SkillDefinition]:
    from app.core.mcp.external_registry import list_mcp_skill_records
    from app.core.mcp.skill_builder import build_mcp_skill_definition

    rows = list_mcp_skill_records(db, include_disabled=include_disabled)
    return [build_mcp_skill_definition(row) for row in rows]


def list_uploaded_skill_definitions(
    db: Session, *, include_disabled: bool = False
) -> list[SkillDefinition]:
    stmt = select(AgentSkill).where(AgentSkill.scope == "system").order_by(
        AgentSkill.name.asc()
    )
    if not include_disabled:
        stmt = stmt.where(AgentSkill.enabled.is_(True))
    rows = db.scalars(stmt).all()
    return [
        SkillDefinition(
            name=row.name,
            title=REPORT_SKILL_LABELS.get(row.name, row.name),
            description=row.description,
            source=SkillSource.UPLOADED,
            tools=(),
            skill_id=row.id,
            readiness=SkillReadiness.READY if row.enabled else SkillReadiness.DISABLED,
            source_type=row.source_type,
            catalog_tier="resident",
            catalog_visible=not row.needs_review,
            created_at=row.created_at,
        )
        for row in rows
    ]


def list_all_skill_definitions(
    db: Session,
    *,
    user: User | None = None,
    admin_view: bool = False,
    include_disabled: bool = False,
    exclude_feature_stubs: bool = True,
    catalog_only: bool = False,
) -> list[SkillDefinition]:
    """列出 Skill 定义。

    exclude_feature_stubs: 排除翻译/对比等系统功能占位项。
    catalog_only: 仅返回应对外展示的技能（隐藏单原子工具映射项）。
    """
    ensure_skills_loaded()
    bindings = _binding_overrides(db)
    out: list[SkillDefinition] = []
    for defn in all_builtin_skills():
        if exclude_feature_stubs and defn.readiness == SkillReadiness.STUB:
            continue
        resolved = resolve_skill_definition(
            db, defn, user=user, admin_view=admin_view, bindings=bindings
        )
        if include_disabled or resolved.readiness != SkillReadiness.DISABLED:
            if catalog_only and not resolved.catalog_visible:
                continue
            out.append(resolved)
    for defn in list_uploaded_skill_definitions(db, include_disabled=include_disabled):
        if include_disabled or defn.readiness != SkillReadiness.DISABLED:
            if catalog_only and not defn.catalog_visible:
                continue
            out.append(defn)
    for defn in list_mcp_skill_definitions(db, include_disabled=include_disabled):
        resolved = resolve_skill_definition(
            db, defn, user=user, admin_view=admin_view, bindings=bindings
        )
        if include_disabled or resolved.readiness != SkillReadiness.DISABLED:
            if catalog_only and not resolved.catalog_visible:
                continue
            out.append(resolved)
    return out


def get_merged_skill_definition(
    db: Session, name: str, *, user: User | None = None, admin_view: bool = False
) -> SkillDefinition | None:
    ensure_skills_loaded()
    from app.skills.registry import get_skill

    defn = get_skill(name)
    if defn:
        return resolve_skill_definition(db, defn, user=user, admin_view=admin_view)
    row = db.scalar(select(AgentSkill).where(AgentSkill.name == name))
    if row:
        return SkillDefinition(
            name=row.name,
            title=REPORT_SKILL_LABELS.get(row.name, row.name),
            description=row.description,
            source=SkillSource.UPLOADED,
            tools=(),
            skill_id=row.id,
            readiness=SkillReadiness.READY if row.enabled else SkillReadiness.DISABLED,
            source_type=row.source_type,
            catalog_tier="resident",
            created_at=row.created_at,
        )
    from app.core.mcp.external_registry import get_mcp_skill_record
    from app.core.mcp.skill_builder import build_mcp_skill_definition

    mcp_record = get_mcp_skill_record(name, db)
    if mcp_record:
        return resolve_skill_definition(
            db,
            build_mcp_skill_definition(mcp_record),
            user=user,
            admin_view=admin_view,
        )
    return None


# 向后兼容：外部可能 from app.skills.catalog import _skill_query_tokens, rank_skills_by_query
# 真实实现在 agentkit-skills


def _skill_query_tokens(query: str) -> list[str]:
    return skill_query_tokens(query)


def _visible_catalog_skills(
    db: Session,
    user: User | None,
    *,
    admin_view: bool = False,
    skill_names: list[str] | None = None,
    resident_only: bool = True,
    query: str = "",
    uploaded_only: bool = False,
    limit: int | None = None,
    tier: str | None = None,
) -> list[SkillDefinition]:
    """目录可见技能：白名单、常驻层、关键词与来源过滤的统一入口。"""
    skills = list_all_skill_definitions(
        db, user=user, admin_view=admin_view, catalog_only=True
    )
    visible = [
        s
        for s in skills
        if s.readiness not in (SkillReadiness.DISABLED, SkillReadiness.NO_PERMISSION)
    ]
    if skill_names is not None:
        allow = {name.strip() for name in skill_names if (name or "").strip()}
        if allow:
            visible = [s for s in visible if s.name in allow]
            resident_only = False
    if tier:
        visible = [s for s in visible if s.catalog_tier == tier]
    elif resident_only:
        visible = [s for s in visible if s.catalog_tier == "resident"]
    if uploaded_only:
        visible = [s for s in visible if s.source == SkillSource.UPLOADED]

    tokens = skill_query_tokens(query)
    if tokens:
        visible = [
            skill for _, skill in rank_skills_by_query(query, visible, limit=limit)
        ]
    elif limit is not None and limit > 0:
        visible = visible[:limit]
    return visible


def _format_agent_catalog_prompt(
    db: Session,
    visible: list[SkillDefinition],
    *,
    resident_only: bool,
    lazy: bool = False,
) -> str:
    if lazy:
        lines = [SKILL_DISCOVERY_RULES, ""]
        if visible:
            lines.append("### 本轮相关 Skill（按需 invoke_skill；更多请 search_skills）")
            for skill in visible:
                tag = ""
                if skill.source == SkillSource.UPLOADED:
                    from app.services.agent_skill_service import uploaded_skill_has_script

                    tag = uploaded_skill_tag(
                        has_script=uploaded_skill_has_script(db, skill.name)
                    )
                elif skill.source == SkillSource.BUILTIN:
                    tag = "[builtin]"
                elif skill.source == SkillSource.MCP:
                    tag = "[mcp]"
                lines.append(format_skill_route_line(skill, tag=tag))
            lines.append("")
        lines.append(
            "完整 Skill/MCP 目录不在此常驻；需要时用 search_skills(query) 或 list_agent_skills 按需加载。"
        )
        return "\n".join(lines).rstrip()

    if not visible:
        return SKILL_LOADING_RULES

    from app.services.agent_skill_service import uploaded_skill_has_script

    lines = [
        "## available_skills（路由摘要，非 SKILL.md 正文）",
        SKILL_LOADING_RULES,
        "",
    ]
    builtin = [s for s in visible if s.source == SkillSource.BUILTIN]
    uploaded = [s for s in visible if s.source == SkillSource.UPLOADED]
    mcp_skills = [s for s in visible if s.source == SkillSource.MCP]

    if builtin:
        lines.append("### 内置（勿 load）")
        for skill in builtin:
            lines.append(format_skill_route_line(skill, tag="[builtin]"))
        lines.append("")

    if uploaded:
        lines.append("### 发展技能")
        for skill in uploaded:
            tag = uploaded_skill_tag(
                has_script=uploaded_skill_has_script(db, skill.name)
            )
            lines.append(format_skill_route_line(skill, tag=tag))
        lines.append("")

    if mcp_skills:
        lines.append("### 外部 MCP Skill")
        for skill in mcp_skills:
            lines.append(format_skill_route_line(skill, tag="[mcp]"))
        lines.append("")

    if resident_only:
        lines.append(
            "低频内置能力（翻译/报告/OCR 等）不在此列表；"
            "用户明确点名或 search_skills 命中后再处理，极低频请引导至对应功能页文档。"
        )

    return "\n".join(lines).rstrip()


def search_skill_routes(
    db: Session,
    user: User | None,
    query: str,
    *,
    tier: str | None = "extended",
    limit: int = 6,
) -> list[str]:
    """搜索 extended 层 Skill 路由行（供 search_tools 或管理端）。"""
    if not _skill_query_tokens(query):
        return []
    from app.services.agent_skill_service import uploaded_skill_has_script

    visible = _visible_catalog_skills(
        db,
        user,
        query=query,
        tier=tier,
        resident_only=False,
        limit=limit,
    )
    lines: list[str] = []
    for skill in visible:
        tag = ""
        if skill.source == SkillSource.UPLOADED:
            tag = uploaded_skill_tag(
                has_script=uploaded_skill_has_script(db, skill.name)
            )
        elif skill.source == SkillSource.BUILTIN:
            tag = "[builtin]"
        elif skill.source == SkillSource.MCP:
            tag = "[mcp]"
        else:
            tag = ""
        lines.append(format_skill_route_line(skill, tag=tag))
    return lines


def build_agent_catalog_prompt(
    db: Session,
    user: User | None = None,
    *,
    admin_view: bool = False,
    skill_names: list[str] | None = None,
    resident_only: bool = True,
    query: str = "",
    uploaded_only: bool = False,
    limit: int | None = None,
    lazy: bool = True,
    preview_limit: int = 4,
) -> str:
    """Discovery 阶段：默认按需目录（lazy）；lazy=False 时注入完整 resident 列表。"""
    effective_limit = limit
    if lazy and effective_limit is None:
        effective_limit = preview_limit if (query or "").strip() else 0
    visible = _visible_catalog_skills(
        db,
        user,
        admin_view=admin_view,
        skill_names=skill_names,
        resident_only=resident_only,
        query=query,
        uploaded_only=uploaded_only,
        limit=effective_limit,
    )
    return _format_agent_catalog_prompt(
        db, visible, resident_only=resident_only, lazy=lazy
    )


def set_builtin_binding(db: Session, name: str, *, enabled: bool) -> None:
    from app.models.agent_skill_binding import AgentSkillBinding

    row = db.get(AgentSkillBinding, name)
    if row:
        row.enabled = enabled
    else:
        db.add(AgentSkillBinding(name=name, enabled=enabled))
    db.commit()
