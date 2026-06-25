"""系统智能体列表、配置与 Skill 白名单。"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.agent_config import (
    AGENT_MD_FILENAME,
    get_config_instruction_body,
    get_effective_agent_md,
    get_effective_description,
    validate_agent_md,
)
from app.core.agent_profiles import AGENT_PROFILES, AgentProfileDef, get_agent_profile
from app.core.exceptions import bad_request, not_found
from app.models.agent_profile_binding import AgentProfileBinding
from app.schemas.agent_profile import (
    AgentCatalogItemOut,
    AgentProfileDetailOut,
    AgentProfileOut,
    AgentRuntimeStatusOut,
)
from app.schemas.agent_skill import AgentSkillFileContentOut
from app.skills.catalog import list_all_skill_definitions
from app.services.agent_runtime_service import agent_runtime_status
from app.services.agent_tool_registry import _TOOL_CATEGORIES, list_agent_tools


def _binding_map(db: Session) -> dict[str, AgentProfileBinding]:
    try:
        rows = db.scalars(select(AgentProfileBinding)).all()
        return {row.agent_id: row for row in rows}
    except Exception:
        db.rollback()
        return {}


def _profile_tool_names(defn: AgentProfileDef) -> set[str]:
    if defn.tool_names:
        return set(defn.tool_names)
    if not defn.tool_categories:
        return set()
    categories = set(defn.tool_categories)
    return {
        name
        for name, category in _TOOL_CATEGORIES.items()
        if category in categories
    }


def _count_tools(db: Session, defn: AgentProfileDef) -> int:
    expected = _profile_tool_names(defn)
    if not expected:
        return 0
    tools = list_agent_tools(db, user=None)
    return sum(1 for tool in tools if tool.name in expected)


def _effective_skill_names(defn: AgentProfileDef, binding: AgentProfileBinding | None) -> list[str]:
    if binding is not None and binding.skill_names is not None:
        stored = [str(name).strip() for name in binding.skill_names if str(name).strip()]
        if stored or binding.skill_names == []:
            return stored
    return list(defn.default_skill_names)


def _validate_skill_names(db: Session, skill_names: list[str]) -> list[str]:
    registry = list_all_skill_definitions(
        db, admin_view=True, include_disabled=True, catalog_only=False
    )
    known = {defn.name for defn in registry}
    cleaned = []
    seen: set[str] = set()
    for raw in skill_names:
        name = (raw or "").strip()
        if not name or name in seen:
            continue
        if name not in known:
            raise bad_request(f"Skill 不存在: {name}")
        seen.add(name)
        cleaned.append(name)
    return cleaned


def _to_out(
    db: Session,
    defn: AgentProfileDef,
    binding: AgentProfileBinding | None,
) -> AgentProfileOut:
    enabled = binding.enabled if binding is not None else True
    status, active_count = agent_runtime_status(defn.id)
    config_md = binding.config_md if binding is not None else None
    return AgentProfileOut(
        id=defn.id,
        title=defn.title,
        description=get_effective_description(defn, config_md),
        enabled=enabled,
        status=AgentRuntimeStatusOut(status),
        skill_names=_effective_skill_names(defn, binding),
        default_skill_names=list(defn.default_skill_names),
        skills_configurable=defn.skills_configurable,
        tool_categories=[c.value for c in defn.tool_categories],
        tool_count=_count_tools(db, defn),
        active_conversations=active_count,
    )


def _to_detail_out(
    db: Session,
    defn: AgentProfileDef,
    binding: AgentProfileBinding | None,
) -> AgentProfileDetailOut:
    base = _to_out(db, defn, binding)
    return AgentProfileDetailOut(**base.model_dump(), files=[AGENT_MD_FILENAME])


def list_agent_profiles(db: Session) -> list[AgentProfileOut]:
    bindings = _binding_map(db)
    return [
        _to_out(db, defn, bindings.get(defn.id))
        for defn in sorted(AGENT_PROFILES, key=lambda item: item.sort_order)
    ]


def list_user_agent_catalog(db: Session) -> list[AgentCatalogItemOut]:
    """对话 Discovery：仅返回已启用的专精子智能体（不含调度器）。"""
    bindings = _binding_map(db)
    items: list[AgentCatalogItemOut] = []
    for defn in sorted(AGENT_PROFILES, key=lambda item: item.sort_order):
        if defn.id == "orchestrator":
            continue
        binding = bindings.get(defn.id)
        enabled = binding.enabled if binding is not None else True
        if not enabled:
            continue
        config_md = binding.config_md if binding is not None else None
        items.append(
            AgentCatalogItemOut(
                id=defn.id,
                title=defn.title,
                description=get_effective_description(defn, config_md),
            )
        )
    return items


def get_agent_profile_out(db: Session, agent_id: str) -> AgentProfileOut:
    defn = get_agent_profile(agent_id)
    if not defn:
        raise not_found(f"智能体不存在: {agent_id}")
    bindings = _binding_map(db)
    return _to_out(db, defn, bindings.get(defn.id))


def get_agent_profile_detail(db: Session, agent_id: str) -> AgentProfileDetailOut:
    defn = get_agent_profile(agent_id)
    if not defn:
        raise not_found(f"智能体不存在: {agent_id}")
    bindings = _binding_map(db)
    return _to_detail_out(db, defn, bindings.get(defn.id))


def get_agent_config_file(
    db: Session,
    agent_id: str,
    file_path: str,
) -> AgentSkillFileContentOut:
    defn = get_agent_profile(agent_id)
    if not defn:
        raise not_found(f"智能体不存在: {agent_id}")
    rel = (file_path or "").replace("\\", "/").strip().lstrip("./")
    if rel != AGENT_MD_FILENAME:
        raise not_found("文件不存在")
    binding = _binding_map(db).get(defn.id)
    config_md = binding.config_md if binding is not None else None
    text = get_effective_agent_md(defn, config_md)
    return AgentSkillFileContentOut(
        path=AGENT_MD_FILENAME,
        content_type="text/markdown",
        text=text,
    )


def update_agent_config_file(
    db: Session,
    agent_id: str,
    file_path: str,
    content: str,
) -> AgentSkillFileContentOut:
    defn = get_agent_profile(agent_id)
    if not defn:
        raise not_found(f"智能体不存在: {agent_id}")
    rel = (file_path or "").replace("\\", "/").strip().lstrip("./")
    if rel != AGENT_MD_FILENAME:
        raise bad_request("仅支持编辑 AGENT.md")
    validated = validate_agent_md(defn.id, content)

    row = db.get(AgentProfileBinding, defn.id)
    if row is None:
        row = AgentProfileBinding(
            agent_id=defn.id,
            enabled=True,
            skill_names=list(defn.default_skill_names),
        )
        db.add(row)
    row.config_md = validated
    db.commit()
    db.refresh(row)
    return AgentSkillFileContentOut(
        path=AGENT_MD_FILENAME,
        content_type="text/markdown",
        text=validated,
    )


def resolve_agent_instruction_body(db: Session, agent_id: str) -> str | None:
    """运行时专精正文（自定义 AGENT.md body）。"""
    defn = get_agent_profile(agent_id)
    if not defn:
        return None
    binding = _binding_map(db).get(defn.id)
    config_md = binding.config_md if binding is not None else None
    return get_config_instruction_body(defn, config_md)


def patch_agent_profile(
    db: Session,
    agent_id: str,
    *,
    enabled: bool | None = None,
    skill_names: list[str] | None = None,
) -> AgentProfileOut:
    defn = get_agent_profile(agent_id)
    if not defn:
        raise not_found(f"智能体不存在: {agent_id}")
    if skill_names is not None and not defn.skills_configurable:
        raise bad_request(f"智能体 `{agent_id}` 不支持配置 Skills")

    row = db.get(AgentProfileBinding, defn.id)
    if row is None:
        row = AgentProfileBinding(
            agent_id=defn.id,
            enabled=True,
            skill_names=list(defn.default_skill_names),
        )
        db.add(row)

    if enabled is not None:
        row.enabled = enabled
    if skill_names is not None:
        row.skill_names = _validate_skill_names(db, skill_names)

    db.commit()
    db.refresh(row)
    return _to_out(db, defn, row)


def resolve_agent_tool_names(db: Session, agent_id: str) -> set[str]:
    """运行时按智能体解析可用原子工具（Phase 2 调度层使用）。"""
    defn = get_agent_profile(agent_id)
    if not defn:
        return set()
    binding = _binding_map(db).get(defn.id)
    if binding is not None and not binding.enabled:
        return set()
    return _profile_tool_names(defn)


def resolve_agent_skill_names(db: Session, agent_id: str) -> list[str]:
    """运行时按智能体解析 Skill 白名单（Phase 2 调度层使用）。"""
    defn = get_agent_profile(agent_id)
    if not defn:
        return []
    binding = _binding_map(db).get(defn.id)
    if binding is not None and not binding.enabled:
        return []
    return _effective_skill_names(defn, binding)


def is_agent_enabled(db: Session, agent_id: str) -> bool:
    defn = get_agent_profile(agent_id)
    if not defn:
        return False
    binding = _binding_map(db).get(defn.id)
    if binding is None:
        return True
    return bool(binding.enabled)
