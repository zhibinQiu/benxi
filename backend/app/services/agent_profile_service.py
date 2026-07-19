"""系统智能体列表、配置与 Skill 白名单。"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any

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
    ToolCategory,
    _TOOL_CATEGORIES,
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


@dataclass(frozen=True)
class _BindingInfo:
    """进程级缓存用纯数据结构 — 替代跨 session 的 ORM 对象。"""
    agent_id: str
    enabled: bool
    service_enabled: bool = True
    skill_names: list[str] = field(default_factory=list)
    runtime_tool_names: list[str] = field(default_factory=list)
    config_md: str | None = None


# 手动 TTL 缓存 — 避免 ORM 对象跨越 session 成为 detached
_binding_cache: dict[str, tuple[float, dict[str, _BindingInfo]]] = {}
_BINDING_CACHE_TTL = 3.0


def _invalidate_binding_cache() -> None:
    _binding_cache.clear()


def _binding_map(db: Session) -> dict[str, _BindingInfo]:
    """返回 {agent_id: _BindingInfo}，进程级 TTL 缓存避免 ORM 跨 session detached。"""
    now = time.monotonic()
    cached = _binding_cache.get("_")
    if cached is not None and now - cached[0] < _BINDING_CACHE_TTL:
        return cached[1]
    try:
        rows = db.scalars(select(AgentProfileBinding)).all()
        result: dict[str, _BindingInfo] = {}
        for row in rows:
            result[row.agent_id] = _BindingInfo(
                agent_id=row.agent_id or "",
                enabled=bool(row.enabled),
                service_enabled=bool(getattr(row, 'service_enabled', True)),
                skill_names=list(row.skill_names) if row.skill_names is not None else [],
                runtime_tool_names=list(row.runtime_tool_names) if row.runtime_tool_names is not None else [],
                config_md=str(row.config_md) if row.config_md else None,
            )
        _binding_cache["_"] = (now, result)
        return result
    except Exception:
        db.rollback()
        return {}


def _effective_skill_names(defn: AgentProfileDef, binding: _BindingInfo | None) -> list[str]:
    if binding is not None and binding.skill_names is not None:
        stored = [str(name).strip() for name in binding.skill_names if str(name).strip()]
        if stored:
            return stored
    return list(defn.default_skill_names)


def _effective_runtime_tool_names(defn: AgentProfileDef, binding: _BindingInfo | None) -> list[str]:
    """动态工具名：优先从 DB binding 读取，无绑定或为空时回退 AgentProfileDef 默认值。

    与 _effective_skill_names 一致：空列表视为"未设置"，回退默认值。
    用户如需清空工具列表，应停用智能体或在多智能体界面管理。
    """
    if binding is not None and binding.runtime_tool_names is not None:
        stored = [str(name).strip() for name in binding.runtime_tool_names if str(name).strip()]
        if stored:
            return stored
    return list(defn.default_runtime_tool_names)


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





# ── 工具名 → 类别映射 ─────────────────────────────────

_RUNTIME_TOOL_CATEGORY: dict[str, str] = {
    "invoke_skill": "skill",
    "load_uploaded_skill": "skill",
    "run_skill_script": "skill",
    "create_skill": "skill_mgmt",
    "update_uploaded_skill_file": "skill_mgmt",
    "delete_uploaded_skill": "skill_mgmt",
    "list_agent_skills": "skill",
    "find_skills": "skill",
    "request_orchestrator_assist": "orchestration",
}

def _tool_names_to_categories(tool_names: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for name in tool_names:
        cat = _RUNTIME_TOOL_CATEGORY.get(name)
        if cat is None:
            tc = _TOOL_CATEGORIES.get(name)
            cat = tc.value if tc else "other"
        if cat not in seen:
            seen.add(cat)
            result.append(cat)
    return result


# ── 实际运行时 LLM 可见的工具名称 ──────────────────────────

def _resolve_runtime_tool_names(
    defn: AgentProfileDef,
    *,
    skill_names: list[str],
    db: Session | None = None,
    known_skill_names: set[str] | None = None,
    skill_def_map: dict[str, object] | None = None,
    binding: _BindingInfo | None = None,
) -> list[str]:
    """返回该 Agent 运行时 LLM 实际可见的工具名列表。

    从 DB binding 或 AgentProfileDef 默认值读取完整工具列表，
    再根据技能挂载情况过滤不可用的 invoke_skill。
    """
    aid = defn.id
    # 动态解析工具列表（binding 优先，否则走 AgentProfileDef 默认值）
    all_tools = _effective_runtime_tool_names(defn, binding)
    if not all_tools:
        return []

    names: list[str] = []
    for tool in all_tools:
        if tool == "invoke_skill":
            callable_skill_names = _callable_skill_names_for_names(
                skill_names,
                known_skill_names=known_skill_names,
                skill_def_map=skill_def_map,
                db=db,
            )
            if not callable_skill_names:
                continue  # 无可调用 Skill 时隐藏 invoke_skill
        names.append(tool)
    return sorted(set(names))


def _callable_skill_names_for_names(
    skill_names: list[str],
    *,
    known_skill_names: set[str] | None = None,
    skill_def_map: dict[str, object] | None = None,
    db: Session | None = None,
) -> list[str]:
    """返回有 handler 的可调用内置 Skill 名。"""
    out: list[str] = []
    for name in skill_names:
        slug = (name or "").strip()
        if not slug:
            continue
        if known_skill_names is not None and slug not in known_skill_names:
            continue
        if skill_def_map is not None:
            defn = skill_def_map.get(slug)
        elif db is not None:
            from app.skills.catalog import get_merged_skill_definition
            defn = get_merged_skill_definition(db, slug, admin_view=True)
        else:
            defn = None
        if defn and getattr(defn, "tools", None):
            out.append(slug)
    return out


def _count_runtime_tools(
    defn: AgentProfileDef,
    *,
    skill_names: list[str],
    db: Session | None = None,
    known_skill_names: set[str] | None = None,
    skill_def_map: dict[str, object] | None = None,
) -> int:
    """统计运行时 LLM 可见的工具数量。"""
    names = _resolve_runtime_tool_names(
        defn,
        skill_names=skill_names,
        db=db,
        known_skill_names=known_skill_names,
        skill_def_map=skill_def_map,
    )
    return len(names)


def _to_out_with_prefetched(
    db: Session,
    defn: AgentProfileDef,
    binding: _BindingInfo | None,
    *,
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
    runtime_names = _resolve_runtime_tool_names(
        defn,
        skill_names=skill_names,
        db=db,
        known_skill_names=known_skill_names,
        skill_def_map=skill_def_map,
        binding=binding,
    )
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
        runtime_tool_names=runtime_names,
        default_runtime_tool_names=list(defn.default_runtime_tool_names),
        tool_categories=_tool_names_to_categories(runtime_names),
        tool_count=len(runtime_names),
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
    binding: _BindingInfo | None,
) -> AgentProfileOut:
    enabled = binding.enabled if binding is not None else True
    service_enabled = binding.service_enabled if binding is not None else True
    status, active_count = agent_runtime_status(defn.id)
    config_md = binding.config_md if binding is not None else None
    skill_names = _effective_skill_names(defn, binding)
    runtime_names = _resolve_runtime_tool_names(
        defn,
        skill_names=skill_names,
        db=db,
        binding=binding,
    )
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
        runtime_tool_names=runtime_names,
        default_runtime_tool_names=list(defn.default_runtime_tool_names),
        tool_categories=_tool_names_to_categories(runtime_names),
        tool_count=len(runtime_names),
        active_conversations=active_count,
    )


def _to_detail_out(
    db: Session,
    defn: AgentProfileDef,
    binding: _BindingInfo | None,
) -> AgentProfileDetailOut:
    base = _to_out(db, defn, binding)
    return AgentProfileDetailOut(**base.model_dump(), files=[AGENT_MD_FILENAME, STYLE_MD_FILENAME])


def list_agent_profiles(db: Session) -> list[AgentProfileOut]:
    bindings = _binding_map(db)
    all_skill_defs = list_all_skill_definitions(
        db, admin_view=False, catalog_only=False
    )
    known_skill_names = {s.name for s in all_skill_defs}
    return [
        _to_out_with_prefetched(
            db, defn, bindings.get(defn.id),
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
        _invalidate_binding_cache()
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
        _invalidate_binding_cache()
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
    runtime_tool_names: list[str] | None = None,
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
    if runtime_tool_names is not None:
        row.runtime_tool_names = [str(name).strip() for name in runtime_tool_names if str(name).strip()]

    db.commit()
    db.refresh(row)
    _invalidate_binding_cache()
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


def resolve_effective_runtime_tool_names(db: Session | None, agent_id: str) -> list[str]:
    """供外部调用：按 DB binding（优先）或 AgentProfileDef 默认值返回该智能体运行时工具名列表。"""
    defn = get_agent_profile(agent_id)
    if not defn:
        return []
    if db is not None:
        try:
            bindings = _binding_map(db)
            return _effective_runtime_tool_names(defn, bindings.get(defn.id))
        except Exception:
            db.rollback()
    return list(defn.default_runtime_tool_names)


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
    """LLM 可见的 Skill 运行时 Tool（不含全局原子 Tool，动态解析）。"""
    defn = get_agent_profile(agent_id)
    if not defn:
        return set()
    binding = _binding_map(db).get(defn.id)
    if binding is not None and not binding.enabled:
        return set()
    all_tools = resolve_effective_runtime_tool_names(db, agent_id)
    runtime_only = {n for n in all_tools if n in SKILL_RUNTIME_TOOL_NAMES}
    if "invoke_skill" in runtime_only:
        from app.services.agent_skill_runtime import _callable_skill_names

        skills = resolve_agent_skill_names(db, agent_id)
        if not _callable_skill_names(db, user=None, skill_names=skills):  # type: ignore[arg-type]
            runtime_only.discard("invoke_skill")
    return runtime_only


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
