"""系统智能体列表、配置与 Skill 白名单。"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.agent_config import (
    AGENT_MD_FILENAME,
    STYLE_MD_FILENAME,
    get_config_instruction_body,
    get_effective_agent_md,
    get_effective_description,
    get_effective_style_md,
    validate_agent_md,
)
from app.core.agent_profiles import AGENT_PROFILES, AgentProfileDef, get_agent_profile
from app.core.exceptions import bad_request, not_found
from app.core.tool_skill_taxonomy import (
    SKILL_RUNTIME_TOOL_NAMES,
    skill_runtime_tools_for_agent,
)
from app.models.agent_profile_binding import AgentProfileBinding
from app.schemas.agent_profile import (
    AgentCatalogItemOut,
    AgentProfileDetailOut,
    AgentProfileOut,
    AgentRuntimeStatusOut,
)
from app.schemas.agent_skill import AgentSkillFileContentOut
from app.skills.catalog import get_merged_skill_definition, list_all_skill_definitions
from app.services.agent_runtime_service import agent_runtime_status
from app.services.agent_tool_registry import list_agent_tools


def _binding_map(db: Session) -> dict[str, AgentProfileBinding]:
    try:
        rows = db.scalars(select(AgentProfileBinding)).all()
        return {row.agent_id: row for row in rows}
    except Exception:
        db.rollback()
        return {}


def _effective_skill_names(defn: AgentProfileDef, binding: AgentProfileBinding | None) -> list[str]:
    if binding is not None and binding.skill_names is not None:
        stored = [str(name).strip() for name in binding.skill_names if str(name).strip()]
        if stored:
            return stored
    return list(defn.default_skill_names)


def resolve_agent_internal_atomic_tools(db: Session, agent_id: str) -> set[str]:
    """专精 Agent 经 Skill 可触达的全局原子 Tool（管理/KG 同步用，非 LLM 暴露）。"""
    skill_names = resolve_agent_skill_names(db, agent_id)
    atomic: set[str] = set()
    for name in skill_names:
        defn = get_merged_skill_definition(db, name, admin_view=True)
        if defn and defn.orchestrated_tools:
            atomic.update(defn.orchestrated_tools)
    from app.core.agent_profiles import _SPECIALIST_AGENT_IDS

    if agent_id in _SPECIALIST_AGENT_IDS:
        atomic.add("request_orchestrator_assist")
    return atomic


def _count_internal_tools(db: Session, defn: AgentProfileDef) -> int:
    expected = resolve_agent_internal_atomic_tools(db, defn.id)
    if not expected:
        return 0
    tools = list_agent_tools(db, user=None)
    return sum(1 for tool in tools if tool.name in expected)


def _count_internal_tools_prefetched(
    defn: AgentProfileDef,
    tool_name_set: set[str],
    known_skill_names: set[str],
    skill_def_map: dict[str, object],
) -> int:
    """使用预取数据计算工具数，避免 N+1 查询。"""
    expected = _resolve_atomic_tools_prefetched(defn.id, known_skill_names, skill_def_map)
    if not expected:
        return 0
    return sum(1 for name in expected if name in tool_name_set)


def _resolve_atomic_tools_prefetched(
    agent_id: str,
    known_skill_names: set[str],
    skill_def_map: dict[str, object],
) -> set[str]:
    """使用预取数据解析原子工具，避免 N+1。"""
    defn = get_agent_profile(agent_id)
    if not defn:
        return set()
    skill_names = defn.default_skill_names
    atomic: set[str] = set()
    for name in skill_names:
        if name not in known_skill_names:
            continue
        skill_defn = skill_def_map.get(name)
        if skill_defn and getattr(skill_defn, 'orchestrated_tools', None):
            atomic.update(skill_defn.orchestrated_tools)
    from app.core.agent_profiles import _SPECIALIST_AGENT_IDS

    if agent_id in _SPECIALIST_AGENT_IDS:
        atomic.add("request_orchestrator_assist")
    return atomic


def _to_out_with_prefetched(
    db: Session,
    defn: AgentProfileDef,
    binding: AgentProfileBinding | None,
    *,
    all_tools: list[object],
    tool_name_set: set[str],
    all_skill_defs: list[object],
    known_skill_names: set[str],
) -> AgentProfileOut:
    """使用预取数据的 _to_out 变体，避免 list_agent_tools 在每个 Agent 上重复调用。"""
    skill_def_map = {s.name: s for s in all_skill_defs}
    enabled = binding.enabled if binding is not None else True
    service_enabled = binding.service_enabled if binding is not None else True
    status, active_count = agent_runtime_status(defn.id)
    config_md = binding.config_md if binding is not None else None
    skill_names = _effective_skill_names(defn, binding)
    return AgentProfileOut(
        id=defn.id,
        title=defn.title,
        description=get_effective_description(defn, config_md),
        enabled=enabled,
        service_enabled=service_enabled,
        status=AgentRuntimeStatusOut(status),
        skill_names=skill_names,
        default_skill_names=list(defn.default_skill_names),
        skills_configurable=defn.skills_configurable,
        tool_categories=[],
        tool_count=_count_internal_tools_prefetched(
            defn, tool_name_set, known_skill_names, skill_def_map
        ),
        active_conversations=active_count,
    )


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
    service_enabled = binding.service_enabled if binding is not None else True
    status, active_count = agent_runtime_status(defn.id)
    config_md = binding.config_md if binding is not None else None
    skill_names = _effective_skill_names(defn, binding)
    return AgentProfileOut(
        id=defn.id,
        title=defn.title,
        description=get_effective_description(defn, config_md),
        enabled=enabled,
        service_enabled=service_enabled,
        status=AgentRuntimeStatusOut(status),
        skill_names=skill_names,
        default_skill_names=list(defn.default_skill_names),
        skills_configurable=defn.skills_configurable,
        tool_categories=[],
        tool_count=_count_internal_tools(db, defn),
        active_conversations=active_count,
    )


def _to_detail_out(
    db: Session,
    defn: AgentProfileDef,
    binding: AgentProfileBinding | None,
) -> AgentProfileDetailOut:
    base = _to_out(db, defn, binding)
    return AgentProfileDetailOut(**base.model_dump(), files=[AGENT_MD_FILENAME, STYLE_MD_FILENAME])


def list_agent_profiles(db: Session) -> list[AgentProfileOut]:
    bindings = _binding_map(db)
    # 预取全量数据，避免每个 Agent 重复扫描工具/技能注册表（N+1 优化）
    all_tools = list_agent_tools(db, user=None)
    all_skill_defs = list_all_skill_definitions(
        db, admin_view=False, catalog_only=False
    )
    known_skill_names = {s.name for s in all_skill_defs}
    tool_name_set = {t.name for t in all_tools}
    return [
        _to_out_with_prefetched(
            db, defn, bindings.get(defn.id),
            all_tools=all_tools,
            tool_name_set=tool_name_set,
            all_skill_defs=all_skill_defs,
            known_skill_names=known_skill_names,
        )
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
    binding = _binding_map(db).get(defn.id)
    if rel == AGENT_MD_FILENAME:
        config_md = binding.config_md if binding is not None else None
        text = get_effective_agent_md(defn, config_md)
        return AgentSkillFileContentOut(
            path=AGENT_MD_FILENAME,
            content_type="text/markdown",
            text=text,
        )
    elif rel == STYLE_MD_FILENAME:
        style_md = binding.style_md if binding is not None else None
        text = get_effective_style_md(defn, style_md)
        return AgentSkillFileContentOut(
            path=STYLE_MD_FILENAME,
            content_type="text/markdown",
            text=text,
        )
    else:
        raise not_found("文件不存在")


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

    row = db.get(AgentProfileBinding, defn.id)
    if row is None:
        row = AgentProfileBinding(
            agent_id=defn.id,
            enabled=True,
            skill_names=list(defn.default_skill_names),
        )
        db.add(row)

    if rel == AGENT_MD_FILENAME:
        validated = validate_agent_md(defn.id, content)
        row.config_md = validated
        db.commit()
        db.refresh(row)
        return AgentSkillFileContentOut(
            path=AGENT_MD_FILENAME,
            content_type="text/markdown",
            text=validated,
        )
    elif rel == STYLE_MD_FILENAME:
        validated = (content or "").strip()
        row.style_md = validated if validated else None
        db.commit()
        db.refresh(row)
        return AgentSkillFileContentOut(
            path=STYLE_MD_FILENAME,
            content_type="text/markdown",
            text=validated or "",
        )
    else:
        raise bad_request(f"不支持的文件: {rel}")


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
    service_enabled: bool | None = None,
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
    if service_enabled is not None:
        row.service_enabled = service_enabled
    if skill_names is not None:
        row.skill_names = _validate_skill_names(db, skill_names)

    db.commit()
    db.refresh(row)
    return _to_out(db, defn, row)


def resolve_agent_tool_names(db: Session, agent_id: str) -> set[str]:
    """兼容别名：返回 Skill 运行时层 + 内部原子 Tool 名（KG 同步 / 旧测试）。"""
    defn = get_agent_profile(agent_id)
    if not defn:
        return set()
    binding = _binding_map(db).get(defn.id)
    if binding is not None and not binding.enabled:
        return set()
    runtime = set(skill_runtime_tools_for_agent(defn.id))
    internal = resolve_agent_internal_atomic_tools(db, agent_id)
    return runtime | internal


def resolve_agent_skill_names(db: Session, agent_id: str) -> list[str]:
    """运行时按智能体解析 Skill 白名单。"""
    defn = get_agent_profile(agent_id)
    if not defn:
        return []
    binding = _binding_map(db).get(defn.id)
    if binding is not None and not binding.enabled:
        return []
    names = _effective_skill_names(defn, binding)
    known = {
        skill.name
        for skill in list_all_skill_definitions(
            db, admin_view=False, catalog_only=False
        )
    }
    return [name for name in names if name in known]


def resolve_agent_runtime_tool_names(db: Session, agent_id: str) -> set[str]:
    """LLM 可见的 Skill 运行时 Tool（不含全局原子 Tool）。"""
    defn = get_agent_profile(agent_id)
    if not defn:
        return set()
    binding = _binding_map(db).get(defn.id)
    if binding is not None and not binding.enabled:
        return set()
    names = set(skill_runtime_tools_for_agent(defn.id))
    if "invoke_skill" in names:
        from app.services.agent_skill_runtime import _callable_skill_names

        skills = resolve_agent_skill_names(db, agent_id)
        if not _callable_skill_names(db, user=None, skill_names=skills):  # type: ignore[arg-type]
            names.discard("invoke_skill")
    return {n for n in names if n in SKILL_RUNTIME_TOOL_NAMES or n in {"request_orchestrator_assist"}}


def is_agent_enabled(db: Session, agent_id: str) -> bool:
    defn = get_agent_profile(agent_id)
    if not defn:
        return False
    binding = _binding_map(db).get(agent_id)
    if binding is None:
        return True
    return bool(binding.enabled)


def is_agent_service_enabled(db: Session, agent_id: str) -> bool:
    """AIP 对外服务是否开放（需同时启用内部智能体）。"""
    if not is_agent_enabled(db, agent_id):
        return False
    binding = _binding_map(db).get(agent_id)
    if binding is None:
        return True
    return bool(binding.service_enabled)
