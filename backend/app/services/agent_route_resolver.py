"""智能体路由解析。

标准化流程（能少则少）：
  1. 用户固定前缀指定智能体/技能（请让…： / 请使用…技能：）→ 硬定位
  2. 确定性硬规则（标签 / 画图 / 定时）
  3. 知识图谱可直答则止（仅分析冒号后正文）
  4. Skill Agentic RAG → 倒排索引落 Agent
  5. 无专精 Skill → LLM 读动态注入的 agents.md 选型
  6. 兜底 orchestrator

约束：Agent/Skill 业务偏好只写在 agents.md / skills.md，本模块只注入与解析。
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.agent.routing import (
    build_route_plan,
    infer_route_mode,
    pick_route,
    plan_orchestrator_direct,
)
from app.core.agent.types import ROUTE_REASONS, AgentRoute, AgentRoutePlan
from app.models.org import User
from app.schemas.ai_chat import AiChatMessage
from app.services.agent_intent import should_orchestrator_reply_directly
from app.services.agent_skill_routing import (
    AgentRoutingScore,
    ResolvedSkillRoutes,
    _ORCHESTRATOR_SKILLS,
    skill_route_reason,
)

_logger = logging.getLogger(__name__)

_ROUTE_PLAN_CACHE: dict[str, tuple[float, AgentRoutePlan]] = {}
_ROUTE_PLAN_CACHE_TTL = 60.0


def _route_cache_key(user_id: str, message: str) -> str:
    return f"{user_id}::{hash(message)}"


def _get_cached_route_plan(user_id: str, message: str) -> AgentRoutePlan | None:
    entry = _ROUTE_PLAN_CACHE.get(_route_cache_key(user_id, message))
    if entry is None:
        return None
    ts, plan = entry
    if time.monotonic() - ts > _ROUTE_PLAN_CACHE_TTL:
        _ROUTE_PLAN_CACHE.pop(_route_cache_key(user_id, message), None)
        return None
    return plan


def _set_cached_route_plan(user_id: str, message: str, plan: AgentRoutePlan) -> None:
    if len(_ROUTE_PLAN_CACHE) >= 512:
        _ROUTE_PLAN_CACHE.clear()
    _ROUTE_PLAN_CACHE[_route_cache_key(user_id, message)] = (time.monotonic(), plan)


def _attach_kg(plan: AgentRoutePlan, kg_text: str) -> AgentRoutePlan:
    if not kg_text or plan.kg_context_text:
        return plan
    return AgentRoutePlan(
        mode=plan.mode,
        routes=plan.routes,
        source=plan.source,
        missing_skill_tags=plan.missing_skill_tags,
        feasible_goal=plan.feasible_goal,
        unsupported_part=plan.unsupported_part,
        capability_gap_instruction=plan.capability_gap_instruction,
        missing_capability_receipt=plan.missing_capability_receipt,
        direct_reply=plan.direct_reply,
        kg_context_text=kg_text,
    )


def resolve_agent_route(
    db: Session,
    user: User,
    message: str,
    *,
    chat_history: list[AiChatMessage] | None = None,
) -> AgentRoute:
    return resolve_agent_routes(db, user, message, chat_history=chat_history)[0]


def resolve_agent_routes(
    db: Session,
    user: User,
    message: str,
    *,
    chat_history: list[AiChatMessage] | None = None,
) -> list[AgentRoute]:
    return resolve_agent_routes_from_skills(
        db, user, message, chat_history=chat_history
    )


def _resolve_hard_rule_routes(db: Session, message: str) -> list[AgentRoute] | None:
    """仅确定性触发，无打分、无领域偏好。"""
    msg = (message or "").strip()
    if not msg:
        return None
    from app.services.agent_skill_router import (
        is_diagram_generation_message,
        is_org_member_list_question,
        is_person_org_affiliation_question,
        match_knowledge_qa_hashtag,
        matches_scheduler_intent,
    )

    if match_knowledge_qa_hashtag(msg) is not None:
        return [pick_route(db, "orchestrator", "知识问答 → knowledge-qa")]
    if is_diagram_generation_message(msg):
        return [pick_route(db, "orchestrator", "图表绘制：直接输出 Mermaid")]
    # 人员归属 / 部门成员：必须走编排层本体语义中枢 + 知识图谱，禁止 platform/list_users
    if is_person_org_affiliation_question(msg) or is_org_member_list_question(msg):
        return [
            pick_route(
                db,
                "orchestrator",
                "人员组织归属/部门成员 → 本体语义中枢 + 知识图谱",
            )
        ]
    if matches_scheduler_intent(msg):
        return [pick_route(db, "platform", ROUTE_REASONS["platform"])]
    return None


@dataclass(frozen=True)
class SkillPathResult:
    """Skill 路径解析结果；source 由函数产出，禁止用 reason 字符串反推。"""

    routes: list[AgentRoute]
    source: str  # hard_rule | explicit_skill | uploaded_skill | skill_rag | orchestrator_default


def _explicit_skill_path(
    db: Session,
    user: User,
    message: str,
    *,
    chat_history: list[AiChatMessage] | None,
    index: dict[str, str],
) -> SkillPathResult | None:
    """消息显式含 skill 名或上传技能名 → 确定性路由。"""
    msg_lower = (message or "").strip().lower()
    for skill_name, agent_id in index.items():
        if skill_name and skill_name.lower() in msg_lower:
            return SkillPathResult(
                routes=[pick_route(db, agent_id, f"直接匹配 Skill `{skill_name}`")],
                source="explicit_skill",
            )

    from app.services.agent_planner import match_uploaded_skill_for_message, _skill_name_sets

    uploaded = _skill_name_sets(db, user) or set()
    matched = match_uploaded_skill_for_message(
        message, chat_history, uploaded_names=uploaded, exclude_research_context=False
    )
    if matched:
        return SkillPathResult(
            routes=[pick_route(db, "orchestrator", f"执行上传技能 `{matched}`")],
            source="uploaded_skill",
        )
    return None


def routes_from_skill_scores(
    db: Session,
    message: str,
    scores: list[AgentRoutingScore],
) -> list[AgentRoute]:
    """Skill RAG 分数 → Agent 路由（函数约束：专精优先于仅 orchestrator skill）。"""
    if not scores:
        return []

    matched: set[str] = set()
    for s in scores:
        matched.update(s.matched_skills)

    non_orch = [s for s in scores if s.agent_id != "orchestrator"]
    if matched - _ORCHESTRATOR_SKILLS and non_orch:
        from app.services.agent_skill_router import (
            is_compound_parallel_message,
            is_compound_sequential_message,
        )

        if len(non_orch) >= 2 and (
            is_compound_sequential_message(message)
            or is_compound_parallel_message(message)
        ):
            seen: set[str] = set()
            multi: list[AgentRoute] = []
            for s in non_orch:
                if s.agent_id in seen:
                    continue
                seen.add(s.agent_id)
                multi.append(pick_route(db, s.agent_id, skill_route_reason(s)))
                if len(multi) >= 3:
                    break
            if len(multi) >= 2:
                return multi
        best = non_orch[0]
        return [pick_route(db, best.agent_id, skill_route_reason(best))]

    orch = next((s for s in scores if s.agent_id == "orchestrator"), None)
    if orch is not None:
        return [pick_route(db, "orchestrator", skill_route_reason(orch))]
    return []


def resolve_skill_path(
    db: Session,
    user: User,
    message: str,
    *,
    chat_history: list[AiChatMessage] | None = None,
    prior_outcomes: list[str] | None = None,
    index: dict[str, str] | None = None,
    skip_hard_rules: bool = False,
) -> SkillPathResult:
    """Skill 路径：硬规则 → 显式名 → Agentic RAG → 倒排。无命中则 orchestrator。"""
    msg = (message or "").strip()
    if not msg:
        return SkillPathResult(
            routes=[pick_route(db, "orchestrator", ROUTE_REASONS["orchestrator"])],
            source="orchestrator_default",
        )

    if not skip_hard_rules:
        hard = _resolve_hard_rule_routes(db, msg)
        if hard is not None:
            return SkillPathResult(routes=hard, source="hard_rule")

    from app.services.agent_skill_routing import (
        build_skill_agent_index,
        pick_skill_route_scores,
        resolve_skill_routed_agent_scores,
    )

    if index is None:
        index = build_skill_agent_index(db)

    from app.core.conversation_turn_context import (
        effective_question_for_retrieval,
        is_likely_follow_up,
    )

    route_query = msg
    if is_likely_follow_up(msg, chat_history):
        route_query = (
            effective_question_for_retrieval(msg, chat_history).strip() or msg
        )

    explicit = _explicit_skill_path(
        db, user, msg, chat_history=chat_history, index=index
    )
    if explicit is not None:
        return explicit

    scores = pick_skill_route_scores(
        resolve_skill_routed_agent_scores(
            db, user, route_query, prior_outcomes=prior_outcomes, index=index
        ),
        query=route_query,
    )
    routed = routes_from_skill_scores(db, msg, scores)
    if routed:
        return SkillPathResult(routes=routed, source="skill_rag")
    return SkillPathResult(
        routes=[pick_route(db, "orchestrator", "由小析直接处理")],
        source="orchestrator_default",
    )


def resolve_agent_routes_from_skills(
    db: Session,
    user: User,
    message: str,
    *,
    chat_history: list[AiChatMessage] | None = None,
    prior_outcomes: list[str] | None = None,
    index: dict[str, str] | None = None,
    skip_hard_rules: bool = False,
) -> list[AgentRoute]:
    return resolve_skill_path(
        db,
        user,
        message,
        chat_history=chat_history,
        prior_outcomes=prior_outcomes,
        index=index,
        skip_hard_rules=skip_hard_rules,
    ).routes


def pick_single_route_from_candidates(routes: list[AgentRoute]) -> AgentRoute:
    if not routes:
        raise ValueError("routes must not be empty")
    return routes[0]


def _plan_from_routes(
    db: Session,
    message: str,
    routes: list[AgentRoute],
    *,
    source: str,
    settings,
) -> AgentRoutePlan:
    mode = infer_route_mode(message, len(routes), settings=settings)
    return build_route_plan(mode, routes, source=source, settings=settings)


def _plan_from_llm_resolved(
    db: Session,
    message: str,
    resolved: ResolvedSkillRoutes,
    *,
    force_replan: bool,
    settings,
) -> AgentRoutePlan:
    routes = [pick_route(db, aid, reason) for aid, reason in resolved.items]
    mode = resolved.mode or infer_route_mode(message, len(routes), settings=settings)
    source = "llm_agent_replan" if force_replan else "llm_agent"
    return build_route_plan(mode, routes, source=source, settings=settings)


def _maybe_orchestrator_direct(
    db: Session,
    message: str,
    chat_history: list[AiChatMessage] | None,
) -> AgentRoutePlan | None:
    """寒暄/极简题直答；知识问答标签禁止直答。"""
    from app.services.agent_skill_router import match_knowledge_qa_hashtag

    if match_knowledge_qa_hashtag(message) is not None:
        return None
    if should_orchestrator_reply_directly(message, chat_history):
        return plan_orchestrator_direct(db)
    return None


async def resolve_agent_route_plan(
    db: Session,
    user: User,
    message: str,
    *,
    chat_history: list[AiChatMessage] | None = None,
    prior_outcomes: list[str] | None = None,
    force_replan: bool = False,
) -> AgentRoutePlan:
    """统一异步路由入口。"""
    settings = get_settings()
    msg = (message or "").strip()
    if not msg:
        return plan_orchestrator_direct(db)

    uid = str(user.id) if hasattr(user, "id") else str(user)
    if not force_replan and not prior_outcomes:
        cached = _get_cached_route_plan(uid, msg)
        if cached is not None:
            return cached

    def _done(plan: AgentRoutePlan, *, kg: str = "") -> AgentRoutePlan:
        out = _attach_kg(plan, kg)
        if not force_replan:
            _set_cached_route_plan(uid, msg, out)
        return out

    _t0 = time.monotonic()
    outcomes = prior_outcomes if (force_replan or prior_outcomes) else None

    # 0) 前端固定前缀：请让 {智能体}： / 请使用 {技能} 技能： → 先硬定位
    from app.services.user_capability_directive import (
        analysis_text_for_semantic,
        resolve_user_capability_directive,
    )

    directive = None
    try:
        directive = resolve_user_capability_directive(db, msg, user=user)
    except Exception:
        _logger.exception("解析用户指定智能体/技能前缀失败，回退常规路由")
    analysis_msg = analysis_text_for_semantic(msg)
    if directive is not None and directive.resolved:
        if directive.kind == "agent" and directive.agent_id:
            routes = [
                pick_route(
                    db,
                    directive.agent_id,
                    f"用户指定智能体 `{directive.raw_label}`",
                )
            ]
            source = "user_agent_directive"
        else:
            agent_id = directive.agent_id or "orchestrator"
            routes = [
                pick_route(
                    db,
                    agent_id,
                    f"用户指定技能 `{directive.skill_name or directive.raw_label}`",
                )
            ]
            source = "user_skill_directive"
        plan = _plan_from_routes(db, msg, routes, source=source, settings=settings)
        # 用户已指定技能/智能体：能力选型走 Catalog，不再用 KG 探测掺进执行过程
        _logger.info("route %s %.1fs", source, time.monotonic() - _t0)
        return _done(plan, kg="")

    hard = _resolve_hard_rule_routes(db, msg)
    if hard is not None:
        plan = _plan_from_routes(db, msg, hard, source="hard_rule", settings=settings)
        _logger.info("route hard_rule %.1fs", time.monotonic() - _t0)
        return _done(plan)

    # KG：只用冒号后分析正文（无前缀则为全文）
    from app.semantic import try_direct_answer_from_decision
    from app.core.conversation_turn_context import effective_question_for_retrieval
    from app.services.agent_planner import (
        peek_cached_kg_direct_reply,
        peek_cached_kg_planning_text,
        resolve_kg_decision_context,
    )
    from app.services.agent_skill_router import should_skip_kg_probe

    kg_seed = analysis_msg or msg
    kg_q = effective_question_for_retrieval(kg_seed, chat_history).strip() or kg_seed
    kg_text = ""
    if kg_seed and not should_skip_kg_probe(kg_seed):
        kg_decision = await resolve_kg_decision_context(
            db, user, kg_seed, history=chat_history, mode="probe"
        )
        kg_text = (
            (kg_decision.planning_text(max_chars=1800) if kg_decision else "")
            or peek_cached_kg_planning_text(uid, kg_q)
        )
        kg_reply = (
            try_direct_answer_from_decision(kg_decision, kg_seed)
            or peek_cached_kg_direct_reply(uid, kg_q)
        )
        if kg_reply:
            return _done(
                AgentRoutePlan(
                    mode="single",
                    routes=(pick_route(db, "orchestrator", "知识图谱已命中，直接作答"),),
                    source="kg_direct",
                    direct_reply=kg_reply,
                    kg_context_text=kg_text,
                ),
                kg=kg_text,
            )

    from app.services.agent_skill_routing import build_skill_agent_index

    index = build_skill_agent_index(db)
    skill_path = resolve_skill_path(
        db,
        user,
        message,
        chat_history=chat_history,
        prior_outcomes=outcomes,
        index=index,
        skip_hard_rules=True,
    )
    routes = skill_path.routes
    if not routes:
        return _done(plan_orchestrator_direct(db), kg=kg_text)

    # 显式 / 上传 / 专精 Skill RAG → 直接落 Agent（source 由函数产出）
    accept_skill = skill_path.source in {"explicit_skill", "uploaded_skill"} or (
        skill_path.source == "skill_rag"
        and (routes[0].agent_id != "orchestrator" or len(routes) > 1)
    )
    if accept_skill:
        plan = _plan_from_routes(
            db, msg, routes, source=skill_path.source, settings=settings
        )
        _logger.info("route %s %.1fs", skill_path.source, time.monotonic() - _t0)
        return _done(plan, kg=kg_text)

    # 无专精 Skill → LLM（catalog 动态注入）
    from app.integrations.deepseek_client import is_configured
    from app.services.agent_skill_routing import llm_plan_agent_routes

    if is_configured():
        resolved = await llm_plan_agent_routes(
            db,
            message,
            chat_history=chat_history,
            prior_outcomes=outcomes,
        )
        if resolved is not None:
            if len(resolved.items) == 1 and resolved.items[0][0] == "orchestrator":
                direct = _maybe_orchestrator_direct(db, msg, chat_history)
                if direct is not None:
                    return _done(direct, kg=kg_text)
            plan = _plan_from_llm_resolved(
                db, msg, resolved, force_replan=force_replan, settings=settings
            )
            _logger.info("route llm_agent %.1fs", time.monotonic() - _t0)
            return _done(plan, kg=kg_text)

    direct = _maybe_orchestrator_direct(db, msg, chat_history)
    if direct is not None:
        return _done(direct, kg=kg_text)

    return _done(
        _plan_from_routes(
            db,
            msg,
            [pick_route(db, "orchestrator", "由小析直接处理")],
            source="orchestrator_fallback",
            settings=settings,
        ),
        kg=kg_text,
    )
