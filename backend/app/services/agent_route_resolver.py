"""智能体路由解析 — 硬规则/Fast Path → Agent RAG → Skill RAG→倒排索引，LLM 作慢速兜底。

路由路径：
  1. Fast Path: 消息含已知 Skill 名 → O(1) 查倒排索引定位 Agent
  2. Agent Embedding RAG（agents.md；失败回退关键词）→ 专精
  3. Skill Embedding RAG → skill→agent 倒排索引聚合到专精
  4. 无匹配 → 调度智能体（自行决定直接回复或使用子智能体）

设计原则：
  - 硬规则与显式点名优先
  - 专精优先：先匹配专精 Agent，再匹配 Skill
  - 调度兜底：未命中时由调度智能体自主判断
  - LLM 路由（默认关闭）仅作更精确的慢速兜底
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
from app.services.agent_intent import should_orchestrator_reply_directly
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


def _match_agent_directly(
    message: str,
    db: Session | None = None,
    *,
    min_score: int = 4,
) -> str | None:
    """专精 Agent 直匹配：先 Embedding RAG（agents.md），失败再关键词。

    除非用户明确提及 Skill 名（Fast Path），否则优先根据 Agent 描述匹配。
    匹配到 Agent 后，由它自己决定使用哪些工具或 Skill 完成。

    Returns:
        agent_id 或 None（匹配不到专精）
    """
    from app.services.agent_skill_rag import rank_agents_by_embedding

    emb = rank_agents_by_embedding(db, message, limit=5)
    if emb:
        _score, entry = emb[0]
        agent_id = (entry.id or "").strip()
        if agent_id and agent_id != "orchestrator":
            return agent_id

    from app.core.routing_catalog_md import load_agents_routing_md, rank_routing_entries

    agents = load_agents_routing_md()
    ranked = rank_routing_entries(message, agents, limit=5)

    best_specialist: tuple[int, str] | None = None  # (score, agent_id)
    for score, agent_id in ranked:
        if score >= min_score:
            if best_specialist is None or score > best_specialist[0]:
                best_specialist = (score, agent_id)

    if best_specialist is not None:
        agent_id = best_specialist[1]
        if agent_id != "orchestrator":
            return agent_id
    return None


def _prior_specialist_for_follow_up(
    db: Session,
    user: User,
    chat_history: list[AiChatMessage] | None,
    *,
    index: dict[str, str] | None,
) -> str | None:
    """上一轮用户问题若本身会落到专精 Agent，则追问可延续该专精。

    Skill 创建等调度/技能开发话题不延续，避免「北京」类短追问被扩写成碳价主题。
    """
    from app.core.conversation_turn_context import last_user_message
    from app.services.agent_skill_router import is_skill_management_message

    prev = last_user_message(chat_history)
    if not prev or is_skill_management_message(prev):
        return None

    specialist = _match_agent_directly(prev, db)
    if specialist and specialist not in ("skill-dev", "orchestrator"):
        return specialist

    from app.services.agent_skill_routing import (
        pick_skill_route_scores,
        resolve_skill_routed_agent_scores,
    )

    scores = pick_skill_route_scores(
        resolve_skill_routed_agent_scores(db, user, prev, index=index),
        query=prev,
    )
    for item in scores:
        if item.agent_id not in ("", "orchestrator", "skill-dev"):
            return item.agent_id
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
    """单路由输出：硬规则 / Fast Path → Agent 描述 → Skill 语义召回。

    路由决策：
    1. Fast Path: 消息含已知 Skill 名 → 精准匹配对应 Agent
    2. 上传技能名匹配 → 路由到调度智能体执行
    3. Agent 优先: agents.md 描述关键词匹配 → 路由到专精
    4. Skill 语义召回（Embedding；失败回退关键词）→ 聚合到 Agent
    5. 兜底 → 调度智能体

    若上一轮已是专精领域，短追问用「上文主题 + 本轮」匹配，避免丢掉专精路由。
    """
    msg = (message or "").strip()

    if not msg:
        return [pick_route(db, "orchestrator", ROUTE_REASONS["orchestrator"])]

    # #知识问答 硬触发 → 调度层直接执行 knowledge-qa（不走模型选型）
    from app.services.agent_skill_router import match_knowledge_qa_hashtag

    if match_knowledge_qa_hashtag(msg) is not None:
        return [
            pick_route(
                db,
                "orchestrator",
                "知识问答 → knowledge-qa",
            )
        ]

    # 图表绘制：小析直接输出 Mermaid（非工具）— 仅看本轮原文
    from app.services.agent_skill_router import (
        is_diagram_generation_message,
        matches_scheduler_intent,
    )

    if is_diagram_generation_message(msg):
        return [pick_route(db, "orchestrator", "图表绘制：直接输出 Mermaid")]

    # 定时提醒 / 系统通知 → 平台操作专精（schedule_notification 等）
    if matches_scheduler_intent(msg):
        return [pick_route(db, "platform", ROUTE_REASONS["platform"])]

    from app.services.agent_skill_routing import (
        build_skill_agent_index,
    )

    if index is None:
        index = build_skill_agent_index(db)

    # 追问延续：仅当上一轮本身会落到专精时，才用合并问题做匹配
    from app.core.conversation_turn_context import (
        effective_question_for_retrieval,
        is_likely_follow_up,
    )

    route_query = msg
    prior_specialist = None
    if is_likely_follow_up(msg, chat_history):
        prior_specialist = _prior_specialist_for_follow_up(
            db, user, chat_history, index=index
        )
        if prior_specialist:
            route_query = (
                effective_question_for_retrieval(msg, chat_history).strip() or msg
            )

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

    # ── 3. Agent 优先匹配：agents.md Embedding RAG（失败回退关键词）──
    from app.services.agent_skill_router import is_skill_management_message
    if not is_skill_management_message(msg):
        specialist = _match_agent_directly(route_query, db)
        if specialist:
            reason = f"Agent RAG 匹配（`{specialist}`）"
            if prior_specialist and route_query != msg:
                reason = f"追问延续上文 · {reason}"
            return [pick_route(db, specialist, reason)]
        # 短追问扩写未命中时，仍可直接延续上一轮专精
        if prior_specialist:
            return [
                pick_route(
                    db,
                    prior_specialist,
                    f"追问延续上文 · Agent RAG 匹配（`{prior_specialist}`）",
                )
            ]

    # ── 4. Skill RAG → 倒排索引落 Agent（兜底）──
    from app.services.agent_skill_routing import (
        pick_skill_route_scores,
        resolve_skill_routed_agent_scores,
        skill_route_reason,
    )

    agent_scores = resolve_skill_routed_agent_scores(
        db, user, route_query, prior_outcomes=prior_outcomes, index=index,
    )
    scores = pick_skill_route_scores(agent_scores, query=route_query)
    if scores:
        matched_skills = set()
        for s in scores:
            matched_skills.update(s.matched_skills)

        specialist_dedicated = matched_skills - _ORCHESTRATOR_SKILLS

        if specialist_dedicated:
            non_orch = [s for s in scores if s.agent_id != "orchestrator"]
            if non_orch:
                best = non_orch[0]
                reason = skill_route_reason(best)
                if prior_specialist and route_query != msg:
                    reason = f"追问延续上文 · {reason}"
                return [pick_route(db, best.agent_id, reason)]

        orch_matched = [s for s in scores if s.agent_id == "orchestrator"]
        if orch_matched:
            return [pick_route(db, "orchestrator", skill_route_reason(orch_matched[0]))]

    # ── 5. 兜底：未匹配任何专精/Skill → 小析自行决定 ──
    return [pick_route(db, "orchestrator", "由小析直接处理")]


def pick_single_route_from_candidates(routes: list[AgentRoute]) -> AgentRoute:
    if not routes:
        raise ValueError("routes must not be empty")
    return routes[0]


async def resolve_agent_route_plan(
    db: Session,
    user: User,
    message: str,
    *,
    chat_history: list[AiChatMessage] | None = None,
    prior_outcomes: list[str] | None = None,
    force_replan: bool = False,
) -> AgentRoutePlan:
    """路由规划 — 硬规则/语义召回优先，LLM 仅作慢速兜底。

    主路径：
      1. Fast Path: 消息含已知 Skill 名 → O(1) 定位 Agent
      2. Agent 描述关键词 → 路由到专精
      3. Skill 语义召回 → 聚合到对应 Agent
      4. 无匹配 → 调度智能体

    LLM 路由（默认关闭，仅调试用）
      仅在主路径落到 orchestrator 且 LLM 可用时启用。
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
    from app.services.agent_skill_router import match_knowledge_qa_hashtag

    # #知识问答 硬触发必须进工具循环，禁止直答短路
    if match_knowledge_qa_hashtag(msg) is None:
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
    chat_history: list[AiChatMessage] | None = None,
) -> AgentRoute:
    return resolve_agent_routes(
        db,
        user,
        message,
        chat_history=chat_history,
    )[0]
