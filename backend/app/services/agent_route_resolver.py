"""智能体路由解析 — 关键词优先，LLM 作慢速兜底。

路由路径（全部基于关键词匹配，毫秒级完成）：
  1. Fast Path: 消息含已知 Skill 名 → O(1) 查倒排索引定位 Agent
  2. Agent 描述关键词匹配 → 路由到专精（由它决定使用哪些 Skill）
  3. Skill 关键词评分 → 聚合到对应 Agent
  4. 无关键词匹配 → 调度智能体（自行决定直接回复或使用子智能体）

设计原则：
  - 关键词优先：能通过关键词匹配的，不走 LLM
  - 专精优先：先匹配专精 Agent，再匹配 Skill
  - 调度兜底：全部关键词未命中，由调度智能体自主判断
  - LLM 路由（默认关闭）仅在关键词兜底后作为更精确的兜底
"""

from __future__ import annotations

import logging
import time

from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.agent.routing import (
    build_route_plan,
    pick_route,
    plan_orchestrator_direct,
)
from app.core.agent.types import ROUTE_REASONS, AgentRoute, AgentRoutePlan
from app.models.org import User
from app.schemas.ai_chat import AiChatMessage
from app.services.agent_intent import AgentToolPlan, should_orchestrator_reply_directly
from app.services.agent_skill_routing import _ORCHESTRATOR_SKILLS

_logger = logging.getLogger(__name__)

# ── 路由结果缓存（内存级，TTL 60 秒）──────────────────────────────────────
_ROUTE_PLAN_CACHE: dict[str, tuple[float, AgentRoutePlan]] = {}
_ROUTE_PLAN_CACHE_TTL = 60.0


def _route_cache_key(user_id: str, message: str) -> str:
    return f"{user_id}::{hash(message)}"


def _get_cached_route_plan(user_id: str, message: str) -> AgentRoutePlan | None:
    key = _route_cache_key(user_id, message)
    entry = _ROUTE_PLAN_CACHE.get(key)
    if entry is None:
        return None
    ts, plan = entry
    if time.monotonic() - ts > _ROUTE_PLAN_CACHE_TTL:
        _ROUTE_PLAN_CACHE.pop(key, None)
        return None
    return plan


def _set_cached_route_plan(user_id: str, message: str, plan: AgentRoutePlan) -> None:
    if len(_ROUTE_PLAN_CACHE) >= 512:
        _ROUTE_PLAN_CACHE.clear()
    key = _route_cache_key(user_id, message)
    _ROUTE_PLAN_CACHE[key] = (time.monotonic(), plan)


def _match_agent_directly(message: str, *, min_score: int = 4) -> str | None:
    """Agent 优先匹配：根据 agents.md 描述匹配专精 Agent。

    除非用户明确提及 Skill 名（Fast Path），否则优先根据 Agent 描述（Use when）
    匹配对应 Agent。匹配到 Agent 后，由它自己决定使用哪些工具或 Skill 完成。

    Returns:
        agent_id 或 None（匹配不到专精）
    """
    from app.core.routing_catalog_md import load_agents_routing_md, rank_routing_entries

    agents = load_agents_routing_md()
    ranked = rank_routing_entries(message, agents, limit=5)
    msg = (message or "").lower()

    best_specialist: tuple[int, str] | None = None  # (score, agent_id)
    for score, agent_id in ranked:
        if score >= min_score:
            if best_specialist is None or score > best_specialist[0]:
                best_specialist = (score, agent_id)

    if best_specialist is not None:
        agent_id = best_specialist[1]
        # skill-dev 安全守卫：仅当明确技能开发意图时路由
        if agent_id == "skill-dev":
            is_dev_intent = any(
                kw in msg
                for kw in ("创建技能", "生成技能", "开发技能", "编写技能",
                           "创建一个skill", "生成一个skill", "开发一个skill")
            )
            if not is_dev_intent:
                return None
        return agent_id
    return None


def resolve_agent_routes_from_skills(
    db: Session,
    user: User,
    message: str,
    *,
    chat_history: list[AiChatMessage] | None = None,
    prior_outcomes: list[str] | None = None,
    index: dict[str, str] | None = None,
) -> list[AgentRoute]:
    """关键词路由 — 始终保持单路由输出（关键词优先，不加 LLM 判断）。

    路由决策（全部基于关键词，O(1)~O(n) 快速路径）：
    1. Fast Path: 消息含已知 Skill 名 → 精准匹配对应 Agent
    2. 上传技能名匹配 → 路由到调度智能体执行
    3. Agent 优先: agents.md 描述关键词匹配 → 路由到专精（由它决定用哪些 Skill）
    4. Skill 关键词评分 → 聚合到 Agent → 选取分数最高的专精
    5. 兜底 → 调度智能体（由调度自行决定直接回复或使用子智能体）
    """
    msg = (message or "").strip()

    if not msg:
        return [pick_route(db, "orchestrator", ROUTE_REASONS["orchestrator"])]

    # ── 1. Fast Path: 消息中直接包含技能名 → 精准匹配 ──
    from app.services.agent_skill_routing import (
        build_skill_agent_index,
    )

    if index is None:
        index = build_skill_agent_index(db)

    msg_lower = msg.lower()
    for skill_name, agent_id in index.items():
        if skill_name in msg_lower:
            return [pick_route(db, agent_id, f"直接匹配 Skill `{skill_name}`")]

    # ── 2. 上传技能名匹配 ──
    from app.services.agent_planner import match_uploaded_skill_for_message, _skill_name_sets

    uploaded_names = _skill_name_sets(db, user) or set()
    matched_skill = match_uploaded_skill_for_message(
        msg, chat_history, uploaded_names=uploaded_names, exclude_research_context=False
    )
    if matched_skill:
        return [pick_route(db, "orchestrator", f"执行上传技能 `{matched_skill}`")]

    # ── 3. Agent 优先匹配：根据 agents.md 描述直接匹配专精 Agent ──
    from app.services.agent_skill_router import is_skill_management_message
    if not is_skill_management_message(msg):
        specialist = _match_agent_directly(msg)
        if specialist:
            return [pick_route(db, specialist, f"Agent 描述匹配（`{specialist}`）")]

    # ── 4. Skill 关键词评分路由（兜底） ──
    from app.services.agent_skill_routing import (
        pick_skill_route_scores,
        resolve_skill_routed_agent_scores,
        skill_route_reason,
    )

    agent_scores = resolve_skill_routed_agent_scores(
        db, user, message, prior_outcomes=prior_outcomes, index=index,
    )
    scores = pick_skill_route_scores(agent_scores, query=msg)
    if scores:
        matched_skills = set()
        for s in scores:
            matched_skills.update(s.matched_skills)

        specialist_dedicated = matched_skills - _ORCHESTRATOR_SKILLS

        if specialist_dedicated:
            non_orch = [s for s in scores if s.agent_id != "orchestrator"]
            if non_orch:
                best = non_orch[0]
                # skill-dev 安全守卫
                if best.agent_id == "skill-dev":
                    is_dev_intent = any(
                        kw in msg_lower
                        for kw in ("创建技能", "生成技能", "开发技能", "编写技能",
                                   "创建一个skill", "生成一个skill", "开发一个skill")
                    )
                    if not is_dev_intent:
                        return [pick_route(db, "orchestrator", "非技能开发请求，由调度智能体处理")]

                return [pick_route(db, best.agent_id, skill_route_reason(best))]

        orch_matched = [s for s in scores if s.agent_id == "orchestrator"]
        if orch_matched:
            return [pick_route(db, "orchestrator", skill_route_reason(orch_matched[0]))]

    # ── 5. 兜底：关键词未匹配任何专精/Skill → 调度智能体自行决定 ──
    return [pick_route(db, "orchestrator", "由调度智能体直接处理")]


def pick_single_route_from_candidates(
    routes: list[AgentRoute],
    _intent_plan: AgentToolPlan | None = None,
) -> AgentRoute:
    if not routes:
        raise ValueError("routes must not be empty")
    return routes[0]


async def resolve_agent_route_plan(
    db: Session,
    user: User,
    message: str,
    *,
    intent_plan: AgentToolPlan | None = None,
    chat_history: list[AiChatMessage] | None = None,
    prior_outcomes: list[str] | None = None,
    force_replan: bool = False,
) -> AgentRoutePlan:
    """路由规划 — 关键词优先，LLM 仅作慢速兜底。

    关键词匹配路径（毫秒级，一次完成）：
      1. Fast Path: 消息含已知 Skill 名 → O(1) 定位 Agent
      2. Agent 描述关键词 → 路由到专精
      3. Skill 关键词评分 → 聚合到对应 Agent
      4. 无匹配 → 调度智能体（由调度自行决定直接回复或使用子智能体）

    LLM 路由（默认关闭，仅调试用）
      仅在关键词路由返回 orchestrator 且 LLM 可用时启用，作为更精确的智能判断。
    """
    settings = get_settings()
    msg = (message or "").strip()

    if not msg:
        return plan_orchestrator_direct(db)

    # 首次非重试路由尝试命中缓存，避免重复
    uid_str = str(user.id) if hasattr(user, "id") else str(user)
    if not force_replan and not prior_outcomes:
        cached = _get_cached_route_plan(uid_str, msg)
        if cached is not None:
            return cached

    _t0 = time.monotonic()
    outcomes = prior_outcomes if (force_replan or prior_outcomes) else None

    # 构建倒排索引（一次复用）
    from app.services.agent_skill_routing import build_skill_agent_index

    index = build_skill_agent_index(db)

    # ── Fast Path: 直接匹配已知 Skill 名（O(1)，完全绕过后两阶段）──
    msg_lower = msg.lower()
    for skill_name, agent_id in index.items():
        if skill_name in msg_lower:
            routes = [pick_route(db, agent_id, f"直接匹配 Skill `{skill_name}`")]
            plan = build_route_plan("single", routes, source="skill_fast", settings=settings)
            _logger.info("Fast Path routing in %.1fs msg=%s skill=%s agent=%s",
                         time.monotonic() - _t0, msg[:40], skill_name, agent_id)
            if not force_replan:
                _set_cached_route_plan(uid_str, msg, plan)
            return plan

    # ── 关键词路由（Agent 优先 → Skill 兜底，始终返回单路由）──
    routes = resolve_agent_routes_from_skills(
        db,
        user,
        message,
        chat_history=chat_history,
        prior_outcomes=outcomes,
        index=index,
    )
    if not routes:
        return plan_orchestrator_direct(db)

    route = routes[0]

    # 关键词路由已匹配到专精 Agent → 直接返回
    if route.agent_id != "orchestrator":
        plan = build_route_plan("single", routes, source="skill_keyword", settings=settings)
        elapsed = time.monotonic() - _t0
        _logger.info("Keyword routing done in %.1fs msg=%s route=%s", elapsed, msg[:40], plan)
        if not force_replan:
            _set_cached_route_plan(uid_str, msg, plan)
        return plan

    # ── 关键词路由返回 orchestrator → 检查是否可以直接答复 ──
    direct = should_orchestrator_reply_directly(msg, chat_history)
    if direct:
        return plan_orchestrator_direct(db)

    # ── LLM 路由（调试用，默认关闭） ──
    if settings.agent_routing_llm_enabled:
        from app.integrations.deepseek_client import is_configured
        from app.services.agent_skill_routing import llm_plan_routes_from_skills

        if is_configured():
            resolved = await llm_plan_routes_from_skills(
                db,
                user,
                message,
                chat_history=chat_history,
                prior_outcomes=outcomes,
                index=index,
            )
            if resolved is not None:
                if len(resolved.items) == 1 and resolved.items[0][0] == "orchestrator":
                    return plan_orchestrator_direct(db)
                agent_id, reason = resolved.items[0]
                routes = [pick_route(db, agent_id, reason)]
                source = "llm_skill_replan" if force_replan else "llm_skill"
                plan = build_route_plan("single", routes, source=source, settings=settings)
                elapsed = time.monotonic() - _t0
                _logger.info("LLM routing done in %.1fs msg=%s route=%s",
                             elapsed, msg[:40], plan)
                if not force_replan:
                    _set_cached_route_plan(uid_str, msg, plan)
                return plan
            _logger.info("LLM routing returned None, falling back to orchestrator")

    # ── 全部匹配失败 → 调度智能体兜底（自行决定直接回复或使用子智能体）──
    reason = (route.reason or "").strip()
    source = "skill_upload" if reason.startswith("执行上传技能") else "skill_keyword"
    plan = build_route_plan("single", routes, source=source, settings=settings)
    elapsed = time.monotonic() - _t0
    _logger.info("Orchestrator fallback in %.1fs msg=%s route=%s", elapsed, msg[:40], plan)
    if not force_replan:
        _set_cached_route_plan(uid_str, msg, plan)
    return plan


def resolve_agent_routes(
    db: Session,
    user: User,
    message: str,
    *,
    intent_plan: AgentToolPlan | None = None,
    chat_history: list[AiChatMessage] | None = None,
) -> list[AgentRoute]:
    """同步 Skill 路由（测试与兼容）。"""
    routes = resolve_agent_routes_from_skills(
        db,
        user,
        message,
        chat_history=chat_history,
    )
    return routes


def resolve_agent_route(
    db: Session,
    user: User,
    message: str,
    *,
    intent_plan: AgentToolPlan | None = None,
    chat_history: list[AiChatMessage] | None = None,
) -> AgentRoute:
    return resolve_agent_routes(
        db,
        user,
        message,
        intent_plan=intent_plan,
        chat_history=chat_history,
    )[0]
