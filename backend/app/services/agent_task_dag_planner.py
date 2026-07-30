"""复合需求 → TaskDAG 规划与终稿综合。"""

from __future__ import annotations

import logging
import re
from typing import Any

from sqlalchemy.orm import Session

from app.agent.orchestrate.dag import TaskDAG, TaskNode, build_task_dag
from app.config import get_settings
from app.core.agent_profiles import AGENT_PROFILES, get_agent_profile
from app.core.llm_parse import parse_llm_json
from app.models.org import User
from app.services.agent_profile_service import is_agent_enabled
from app.services.agent_skill_router import (
    is_compound_parallel_message,
    is_compound_sequential_message,
)

_logger = logging.getLogger(__name__)

_NODE_ID_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9_-]{0,31}$")


def should_attempt_task_dag(
    message: str,
    *,
    route_count: int = 0,
    settings=None,
) -> bool:
    """简单单意图不走 DAG；复合信号或多路由候选时尝试。"""
    cfg = settings or get_settings()
    if not bool(getattr(cfg, "agent_task_dag_enabled", True)):
        return False
    msg = (message or "").strip()
    if not msg:
        return False
    if route_count > 1:
        return True
    return is_compound_sequential_message(msg) or is_compound_parallel_message(msg)


def _enabled_agent_ids(db: Session) -> set[str]:
    enabled = {
        p.id
        for p in AGENT_PROFILES
        if p.id == "orchestrator" or is_agent_enabled(db, p.id)
    }
    return enabled


def _title_for(agent_id: str, fallback: str = "") -> str:
    profile = get_agent_profile(agent_id)
    if profile and profile.title:
        return profile.title
    return fallback or agent_id


def parse_task_dag_payload(
    data: dict[str, Any] | None,
    *,
    allowed_agents: set[str],
    max_nodes: int = 4,
) -> TaskDAG | None:
    """解析 LLM/规则产出的 tasks JSON；非法依赖降级为无边；非法 agent 丢弃。"""
    if not isinstance(data, dict):
        return None
    raw_tasks = data.get("tasks")
    if not isinstance(raw_tasks, list) or not raw_tasks:
        return None

    max_n = max(1, int(max_nodes or 1))
    nodes_raw: list[dict[str, Any]] = []
    for item in raw_tasks[:max_n]:
        if not isinstance(item, dict):
            continue
        nid = str(item.get("id") or "").strip()
        agent_id = str(item.get("agent_id") or "").strip()
        if not nid or not _NODE_ID_RE.match(nid):
            continue
        if agent_id not in allowed_agents:
            continue
        if agent_id == "orchestrator" and len(raw_tasks) > 1:
            # 多节点计划里跳过纯调度占位
            continue
        goal = str(item.get("goal") or item.get("reason") or "").strip()
        title = str(item.get("title") or "").strip() or _title_for(agent_id)
        deps_raw = item.get("depends_on") or item.get("deps") or []
        if isinstance(deps_raw, str):
            deps = [deps_raw.strip()] if deps_raw.strip() else []
        elif isinstance(deps_raw, list):
            deps = [str(d).strip() for d in deps_raw if str(d).strip()]
        else:
            deps = []
        nodes_raw.append(
            {
                "id": nid,
                "title": title[:80],
                "agent_id": agent_id,
                "goal": goal[:500],
                "depends_on": deps,
                "reason": str(item.get("reason") or goal)[:240],
            }
        )

    if not nodes_raw:
        return None

    # 去重 id（保留先出现的）
    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    for n in nodes_raw:
        if n["id"] in seen:
            continue
        seen.add(n["id"])
        unique.append(n)

    id_set = {n["id"] for n in unique}
    # 非法依赖剥离
    for n in unique:
        n["depends_on"] = tuple(d for d in n["depends_on"] if d in id_set and d != n["id"])

    nodes = [
        TaskNode(
            id=n["id"],
            title=n["title"],
            agent_id=n["agent_id"],
            goal=n["goal"],
            depends_on=n["depends_on"],
            reason=n["reason"],
        )
        for n in unique
    ]

    try:
        return build_task_dag(nodes)
    except ValueError:
        # 环：降级为无依赖并行
        flat = [
            TaskNode(
                id=n.id,
                title=n.title,
                agent_id=n.agent_id,
                goal=n.goal,
                depends_on=(),
                reason=n.reason,
            )
            for n in nodes
        ]
        try:
            return build_task_dag(flat)
        except ValueError:
            return None


def dag_from_flat_routes(
    routes: list[Any],
    *,
    message: str,
    mode: str = "sequential",
) -> TaskDAG | None:
    """将扁平多路由计划转为线性或无边 DAG（无 LLM 时的降级）。"""
    if len(routes) < 2:
        return None
    sequential = (mode or "").lower() != "parallel" and (
        (mode or "").lower() == "sequential" or is_compound_sequential_message(message)
    )
    nodes: list[TaskNode] = []
    for idx, route in enumerate(routes, start=1):
        agent_id = getattr(route, "agent_id", None) or str(route)
        reason = getattr(route, "reason", "") or ""
        nid = f"t{idx}"
        deps: tuple[str, ...] = (f"t{idx - 1}",) if sequential and idx > 1 else ()
        nodes.append(
            TaskNode(
                id=nid,
                title=_title_for(agent_id),
                agent_id=agent_id,
                goal=reason or message[:200],
                depends_on=deps,
                reason=reason,
            )
        )
    try:
        return build_task_dag(nodes)
    except ValueError:
        return None


def agent_plan_detail_lines(dag: TaskDAG) -> str:
    """前端 agent_plan phase 用的编号步骤文案。"""
    lines: list[str] = []
    for i, n in enumerate(dag.nodes, start=1):
        dep = ""
        if n.depends_on:
            dep = f"（依赖 {', '.join(n.depends_on)}）"
        goal = (n.goal or n.reason or "").strip()
        suffix = f"：{goal}" if goal else ""
        lines.append(f"{i}. {n.title}{dep}{suffix}")
    return "\n".join(lines)


async def maybe_plan_task_dag(
    db: Session,
    user: User,
    message: str,
    *,
    chat_history: list | None = None,
    route_plan: Any | None = None,
) -> TaskDAG | None:
    """尝试为复合需求产出 TaskDAG；失败返回 None（走原有路由）。"""
    cfg = get_settings()
    routes = list(getattr(route_plan, "routes", None) or [])
    mode = str(getattr(route_plan, "mode", "") or "single")
    if not should_attempt_task_dag(message, route_count=len(routes), settings=cfg):
        return None

    allowed = _enabled_agent_ids(db)
    max_nodes = max(1, int(getattr(cfg, "agent_max_dag_nodes", 4) or 4))

    dag: TaskDAG | None = None
    if bool(getattr(cfg, "agent_dag_planner_llm_enabled", True)):
        dag = await _llm_plan_task_dag(
            db,
            message,
            chat_history=chat_history,
            allowed=allowed,
            max_nodes=max_nodes,
        )

    if dag is None and len(routes) > 1:
        dag = dag_from_flat_routes(routes, message=message, mode=mode)

    if dag is None or len(dag.nodes) < 2:
        return None
    # 波次内并行上限裁剪：过多独立根节点时保留前 N 个
    max_par = max(1, int(getattr(cfg, "agent_max_parallel_handoffs", 3) or 3))
    if len(dag.nodes) > max_nodes:
        kept = dag.nodes[:max_nodes]
        # 剥离指向被裁节点的依赖
        kept_ids = {n.id for n in kept}
        trimmed = [
            TaskNode(
                id=n.id,
                title=n.title,
                agent_id=n.agent_id,
                goal=n.goal,
                depends_on=tuple(d for d in n.depends_on if d in kept_ids),
                reason=n.reason,
            )
            for n in kept
        ]
        try:
            dag = build_task_dag(trimmed)
        except ValueError:
            return None
    # 同波 ready 过多时不在此裁剪节点，由 scheduler max_parallel 限流
    _ = max_par
    _ = user
    return dag


async def _llm_plan_task_dag(
    db: Session,
    message: str,
    *,
    chat_history: list | None,
    allowed: set[str],
    max_nodes: int,
) -> TaskDAG | None:
    from app.core.routing_catalog_md import build_agents_catalog_text
    from app.integrations.deepseek_client import chat_completion_message_async, is_configured

    if not is_configured():
        return None

    agent_catalog = build_agents_catalog_text(
        enabled_ids=frozenset(allowed),
        include_orchestrator=True,
    )
    hist = ""
    if chat_history:
        for msg in chat_history[-4:]:
            role = "User" if getattr(msg, "role", "") == "user" else "Assistant"
            text = (getattr(msg, "content", "") or "").strip()[:160]
            if text:
                hist += f"{role}: {text}\n"

    system = (
        "You are the platform task planner. Decompose the user request into a DAG of specialist tasks.\n"
        "Intermediate planning text must be English. Do not invent tool results.\n"
        "Output JSON only:\n"
        '{"tasks":[{"id":"t1","title":"short title","agent_id":"catalog-id",'
        '"goal":"what this node must achieve","depends_on":["t0"]}]}\n'
        f"Rules: 2–{max_nodes} tasks; agent_id must appear in the catalog; "
        "depends_on lists prior task ids (empty = can run in parallel); "
        "no cycles; independent subgoals use empty depends_on; ordered steps use depends_on.\n"
        "If the request is a single simple intent, return {\"tasks\":[]}."
    )
    user_prompt = (
        f"[User goal]\n{(message or '')[:900]}\n\n"
        f"[Agent catalog]\n{agent_catalog}"
    )
    if hist:
        user_prompt = f"[Recent dialogue]\n{hist}\n{user_prompt}"

    try:
        choice = await chat_completion_message_async(
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user_prompt},
            ],
            tools=None,
            temperature=0.1,
        )
        content = (((choice or {}).get("message") or {}).get("content") or "").strip()
        payload = parse_llm_json(content)
        return parse_task_dag_payload(
            payload,
            allowed_agents=allowed,
            max_nodes=max_nodes,
        )
    except Exception:
        _logger.exception("Task DAG LLM planner failed")
        return None


def fallback_join_replies(results: list[dict[str, Any]]) -> str:
    parts: list[str] = []
    for item in results:
        title = str(item.get("title") or item.get("agent_id") or "").strip()
        reply = str(item.get("reply") or "").strip()
        if not reply:
            continue
        parts.append(f"【{title}】\n{reply}" if title else reply)
    return "\n\n".join(parts).strip()


async def synthesize_dag_final_reply(
    user_message: str,
    results: list[dict[str, Any]],
) -> str:
    """综合多节点交付物为统一终稿；LLM 失败时结构化拼接。"""
    joined = fallback_join_replies(results)
    if not joined:
        return ""
    if len(results) == 1:
        return str(results[0].get("reply") or "").strip()

    from app.integrations.deepseek_client import chat_completion_message_async, is_configured

    if not is_configured():
        return joined

    blocks = []
    for item in results:
        title = str(item.get("title") or item.get("agent_id") or "task")
        reply = str(item.get("reply") or "").strip()
        if reply:
            blocks.append(f"### {title}\n{reply[:2000]}")
    system = (
        "You synthesize multi-agent task results into one coherent final reply for the user.\n"
        "Match the user's language. Do not invent facts beyond the provided results. "
        "Do not mention ROUTE. Do not mention internal agent ids."
    )
    user_prompt = (
        f"[User request]\n{(user_message or '')[:600]}\n\n"
        f"[Task results]\n" + "\n\n".join(blocks)
    )
    try:
        choice = await chat_completion_message_async(
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user_prompt},
            ],
            tools=None,
            temperature=0.2,
        )
        content = (((choice or {}).get("message") or {}).get("content") or "").strip()
        return content or joined
    except Exception:
        _logger.exception("DAG synthesizer failed")
        return joined


def build_node_user_message(
    user_message: str,
    node: TaskNode,
    parent_replies: list[tuple[str, str]],
) -> str:
    """将上游结论注入下游 hop 的用户消息。"""
    goal = (node.goal or "").strip()
    base = user_message.strip()
    if goal and goal not in base:
        base = f"{base}\n\n【本步目标】\n{goal}"
    if not parent_replies:
        return base
    parts = [base, ""]
    for title, reply in parent_replies:
        parts.append(f"【上游 {title} 结论】\n{reply[:1200]}")
    return "\n".join(parts).strip()
