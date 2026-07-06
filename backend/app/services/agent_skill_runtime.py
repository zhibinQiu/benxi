"""Skill 运行时层 — 组装 LLM 可见的 Skill 调度 Tool（非全局原子 Tool）。"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.agent_tool_args import (
    ORCHESTRATION_TOOL_NAMES,
    SKILL_RUNTIME_TOOL_NAMES,
    build_tool_specs,
)
from app.core.tool_skill_taxonomy import (
    agent_atomic_tool_names,
    skill_runtime_tools_for_agent,
)
from app.models.org import User
from app.skills.catalog import get_merged_skill_definition


def _callable_skill_names(
    db: Session,
    user: User,
    skill_names: list[str],
) -> list[str]:
    """返回带 handler 的可 invoke 内置 Skill（playbook-only 不在此列）。"""
    out: list[str] = []
    for name in skill_names:
        slug = (name or "").strip()
        if not slug:
            continue
        defn = get_merged_skill_definition(
            db, slug, user=user, admin_view=user is None
        )
        if not defn or not defn.tools:
            continue
        out.append(slug)
    return out


def build_agent_runtime_tool_specs(
    db: Session,
    user: User,
    *,
    agent_id: str | None = None,
    allowed_skill_names: list[str] | None = None,
    allowed_runtime_tools: set[str] | None = None,
) -> list[dict]:
    """专精 Agent 运行时：Skill 运行时层 Tool + 白名单原子 Tool。"""
    from app.config import get_settings
    from app.integrations.browser_automation.browser_config import get_browser_rpa_config

    aid = (agent_id or "").strip()
    runtime_allow = (
        allowed_runtime_tools
        if allowed_runtime_tools is not None
        else skill_runtime_tools_for_agent(aid)
    )

    names: list[str] = []
    if "invoke_skill" in runtime_allow:
        skill_list = list(allowed_skill_names or [])
        if _callable_skill_names(db, user, skill_list):
            names.append("invoke_skill")
    for tool in SKILL_RUNTIME_TOOL_NAMES:
        if tool == "invoke_skill":
            continue
        if tool not in runtime_allow:
            continue
        if tool == "run_skill_script" and not get_settings().agent_skill_script_enabled:
            continue
        names.append(tool)

    if "request_orchestrator_assist" in runtime_allow:
        names.extend(ORCHESTRATION_TOOL_NAMES)

    # 追加专精 Agent 可直接调用的全局原子 Tool（绕过 invoke_skill 间接层）
    atomic_names = agent_atomic_tool_names(aid)
    if atomic_names:
        names.extend(atomic_names)

    specs = build_tool_specs(names)
    # 去重保序
    seen: set[str] = set()
    out: list[dict] = []
    for spec in specs:
        fn = spec.get("function") or {}
        n = str(fn.get("name") or "")
        if n and n not in seen:
            seen.add(n)
            out.append(spec)
    return out


def resolve_runtime_tools_for_agent(
    db: Session,
    agent_id: str,
    *,
    skill_names: list[str],
) -> set[str]:
    """解析专精 Agent 可用的 Skill 运行时 Tool 名集合。"""
    runtime = set(skill_runtime_tools_for_agent(agent_id))
    if "invoke_skill" in runtime:
        if not _callable_skill_names(db, user=None, skill_names=skill_names):  # type: ignore[arg-type]
            runtime.discard("invoke_skill")
    return runtime
