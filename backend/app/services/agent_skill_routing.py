"""调度路由 — LLM 读取 skills.md / agents.md 后规划 Skill 选型，反查专精 Agent。

Skill 路由三阶段：
  1. 信号层（agent_skill_router）：用户消息意图检测
  2. 规划层（本文件）：LLM 读取路由目录后选 Skill → 反查 Agent
  3. 评分层（agent_skill_match）：关键词召回 → 相似度归一化 → Agent 聚合评分"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from app.core.agent_profiles import AGENT_PROFILES
from app.core.llm_parse import parse_llm_json
from app.core.routing_catalog_md import (
    build_agents_catalog_text,
    format_skill_route_line as format_md_skill_line,
    load_skills_routing_md,
    rank_routing_entries,
    skills_routing_md_text,
)
from app.core.tool_skill_taxonomy import AGENT_DEFAULT_SKILLS
from app.models.org import User
from app.services.agent_profile_service import is_agent_enabled, resolve_agent_skill_names
from app.skills.catalog import list_all_skill_definitions, rank_skills_by_query
from app.skills.routing import format_skill_route_line, uploaded_skill_tag
from app.skills.types import SkillDefinition, SkillReadiness, SkillSource

_logger = logging.getLogger(__name__)

ROUTING_CONTEXT_MARKER = "【路由上下文】"
_COARSE_SKILL_LIMIT = 20
_FAILED_AGENT_PREFIX = "失败Agent："
RouteMode = Literal["single", "sequential", "parallel"]


class LlmSkillRoutePlan(BaseModel):
    """调度 LLM 输出的 Skill 级路由计划。"""

    orchestrator_direct: bool = False
    mode: RouteMode = "single"
    skills: list[str] = Field(default_factory=list, max_length=6)
    reason: str = ""

    @field_validator("skills", mode="before")
    @classmethod
    def _normalize_skills(cls, value: object) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            value = [value]
        if not isinstance(value, list):
            return []
        return [str(x).strip() for x in value if str(x).strip()]


@dataclass(frozen=True, slots=True)
class AgentRoutingScore:
    agent_id: str
    score: float
    matched_skills: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ResolvedSkillRoutes:
    mode: RouteMode
    items: tuple[tuple[str, str], ...]
    """(agent_id, reason)"""


def format_routing_context_line(failed_agent_ids: list[str]) -> str:
    ids = [x.strip() for x in failed_agent_ids if x.strip()]
    if not ids:
        return ""
    return f"{ROUTING_CONTEXT_MARKER} {_FAILED_AGENT_PREFIX}" + "、".join(ids)


def parse_failed_agents_from_text(text: str) -> list[str]:
    body = (text or "").strip()
    if _FAILED_AGENT_PREFIX not in body:
        return []
    segment = body.split(_FAILED_AGENT_PREFIX, 1)[-1].split("|", 1)[0].strip()
    return [x.strip() for x in segment.split("、") if x.strip()]


def build_routing_query(message: str, prior_outcomes: list[str] | None = None) -> str:
    parts = [(message or "").strip()]
    failed: list[str] = []
    for raw in (prior_outcomes or [])[-3:]:
        text = str(raw or "").strip()
        if not text:
            continue
        parts.append(text[:800])
        failed.extend(parse_failed_agents_from_text(text))
    if failed:
        parts.append("避免：" + "、".join(dict.fromkeys(failed)))
    return "\n".join(p for p in parts if p)


def build_skill_agent_index(db: Session) -> dict[str, frozenset[str]]:
    index: dict[str, set[str]] = {}
    for profile in AGENT_PROFILES:
        if profile.id == "orchestrator":
            continue
        if not is_agent_enabled(db, profile.id):
            continue
        for skill_name in resolve_agent_skill_names(db, profile.id):
            index.setdefault(skill_name, set()).add(profile.id)
    return {name: frozenset(agents) for name, agents in index.items()}


def _skill_route_line(defn: SkillDefinition, *, db: Session | None = None) -> str:
    md = load_skills_routing_md().get(defn.name)
    if md:
        tag = ""
        if defn.source == SkillSource.UPLOADED and db is not None:
            from app.services.agent_skill_service import uploaded_skill_has_script

            tag = uploaded_skill_tag(has_script=uploaded_skill_has_script(db, defn.name))
        elif defn.source == SkillSource.BUILTIN:
            tag = "[builtin]"
        return format_md_skill_line(md, tag=tag)
    tag = "[uploaded]" if defn.source == SkillSource.UPLOADED else ""
    return format_skill_route_line(defn, tag=tag)


def coarse_skill_candidates(
    db: Session,
    user: User,
    message: str,
    *,
    prior_outcomes: list[str] | None = None,
    limit: int = _COARSE_SKILL_LIMIT,
) -> list[SkillDefinition]:
    """关键词粗筛 Top-N，优先 skills.md，发展技能回退 SkillDefinition。"""
    query = build_routing_query(message, prior_outcomes)
    skills = [
        s
        for s in list_all_skill_definitions(db, user=user, catalog_only=False)
        if s.readiness not in (SkillReadiness.DISABLED, SkillReadiness.NO_PERMISSION)
    ]
    by_name = {s.name: s for s in skills}
    md = load_skills_routing_md()
    md_ranked = rank_routing_entries(query, md, limit=limit)
    matched: list[SkillDefinition] = []
    seen: set[str] = set()
    for score, sid in md_ranked:
        if score <= 0 or sid not in by_name:
            continue
        matched.append(by_name[sid])
        seen.add(sid)
    if matched:
        return matched[:limit]
    ranked = rank_skills_by_query(query, skills, limit=limit)
    return [skill for score, skill in ranked if score > 0][:limit]


def build_skill_route_catalog(
    skills: list[SkillDefinition],
    index: dict[str, frozenset[str]],
    *,
    db: Session | None = None,
) -> str:
    lines = [
        skills_routing_md_text().split("\n", 1)[0],
        "候选 Skill（仅可从下列 skill_id 选择，勿编造）：",
        "",
    ]
    for skill in skills:
        agents = "、".join(sorted(index.get(skill.name, frozenset()))) or "—"
        lines.append(f"{_skill_route_line(skill, db=db)} | Agents: {agents}")
    return "\n".join(lines)


def parse_llm_skill_route_plan(
    data: dict[str, object] | None,
    *,
    allowed: set[str],
) -> LlmSkillRoutePlan | None:
    if not isinstance(data, dict):
        return None
    try:
        plan = LlmSkillRoutePlan.model_validate(data)
    except Exception:
        return None
    skills = [sid for sid in plan.skills if sid in allowed]
    if not plan.orchestrator_direct and not skills:
        return None
    return plan.model_copy(update={"skills": skills})


def _pick_agent_for_skill(skill_name: str, agents: frozenset[str]) -> str | None:
    if not agents:
        return None
    if len(agents) == 1:
        return next(iter(agents))
    for agent_id, defaults in AGENT_DEFAULT_SKILLS.items():
        if skill_name in defaults and agent_id in agents:
            return agent_id
    return sorted(agents)[0]


def agents_from_skill_selection(
    skill_ids: list[str],
    index: dict[str, frozenset[str]],
) -> list[tuple[str, list[str]]]:
    """按 LLM 选定 Skill 顺序反查专精 Agent（同 Agent 合并 Skill）。"""
    order: list[str] = []
    grouped: dict[str, list[str]] = {}
    for skill_id in skill_ids:
        agent_id = _pick_agent_for_skill(skill_id, index.get(skill_id, frozenset()))
        if not agent_id:
            continue
        if agent_id not in grouped:
            order.append(agent_id)
            grouped[agent_id] = []
        if skill_id not in grouped[agent_id]:
            grouped[agent_id].append(skill_id)
    return [(agent_id, grouped[agent_id]) for agent_id in order]


def _route_reason_for_skills(skill_names: list[str], *, llm_reason: str = "") -> str:
    skills = "、".join(f"`{n}`" for n in skill_names[:4])
    base = f"Skill：{skills}" if skills else "Skill 路由"
    note = (llm_reason or "").strip()
    return f"{base}（{note}）" if note else base


def resolved_routes_from_skill_plan(
    plan: LlmSkillRoutePlan,
    index: dict[str, frozenset[str]],
) -> ResolvedSkillRoutes | None:
    if plan.orchestrator_direct:
        note = (plan.reason or "调度直接回答").strip()
        return ResolvedSkillRoutes(mode="single", items=(("orchestrator", note),))

    groups = agents_from_skill_selection(plan.skills, index)
    if not groups:
        return None

    mode: RouteMode = plan.mode
    if len(groups) == 1:
        mode = "single"

    items = tuple(
        (
            agent_id,
            _route_reason_for_skills(skill_names, llm_reason=plan.reason),
        )
        for agent_id, skill_names in groups
    )
    return ResolvedSkillRoutes(mode=mode, items=items)


def aggregate_agents_from_skills(
    ranked_skills: list[tuple[int, SkillDefinition]],
    skill_agent_index: dict[str, frozenset[str]],
    *,
    failed_agent_ids: frozenset[str] | None = None,
) -> list[AgentRoutingScore]:
    totals: dict[str, float] = {}
    matched: dict[str, list[str]] = {}
    failed = failed_agent_ids or frozenset()

    for relevance, skill in ranked_skills:
        if relevance <= 0:
            continue
        agents = skill_agent_index.get(skill.name)
        if not agents:
            continue
        for agent_id in agents:
            weight = float(relevance)
            if agent_id in failed:
                weight *= 0.35
            if weight > totals.get(agent_id, 0.0):
                totals[agent_id] = weight
            matched.setdefault(agent_id, []).append(skill.name)

    scores = [
        AgentRoutingScore(
            agent_id=agent_id,
            score=score,
            matched_skills=tuple(dict.fromkeys(matched.get(agent_id, []))),
        )
        for agent_id, score in totals.items()
    ]
    scores.sort(key=lambda item: (-item.score, len(item.matched_skills), item.agent_id))
    return scores


def _rank_skills_for_routing(
    query: str,
    skills: list[SkillDefinition],
    *,
    limit: int = 12,
) -> list[tuple[int, SkillDefinition]]:
    """skills.md 优先，发展技能回退 SkillDefinition 字段。"""
    by_name = {s.name: s for s in skills}
    md = load_skills_routing_md()
    ranked: list[tuple[int, SkillDefinition]] = []
    for score, sid in rank_routing_entries(query, md, limit=limit):
        if sid in by_name:
            ranked.append((score, by_name[sid]))
    if ranked:
        return ranked
    return rank_skills_by_query(query, skills, limit=limit)


def resolve_skill_routed_agent_scores(
    db: Session,
    user: User,
    message: str,
    *,
    prior_outcomes: list[str] | None = None,
) -> list[AgentRoutingScore]:
    query = build_routing_query(message, prior_outcomes)
    skills = [
        s
        for s in list_all_skill_definitions(db, user=user, catalog_only=False)
        if s.readiness not in (SkillReadiness.DISABLED, SkillReadiness.NO_PERMISSION)
    ]
    ranked = _rank_skills_for_routing(query, skills, limit=12)
    if not ranked:
        return []
    failed: set[str] = set()
    for raw in prior_outcomes or []:
        failed.update(parse_failed_agents_from_text(str(raw or "")))
    return aggregate_agents_from_skills(
        ranked,
        build_skill_agent_index(db),
        failed_agent_ids=frozenset(failed),
    )


def pick_skill_route_scores(
    scores: list[AgentRoutingScore],
    *,
    query: str = "",
    min_score: float = 1.0,
    limit: int = 4,
) -> list[AgentRoutingScore]:
    picked = [s for s in scores if s.score >= min_score]
    q = (query or "").lower()

    def _name_hits(skills: tuple[str, ...]) -> int:
        return sum(
            1
            for name in skills
            if name.replace("-", "") in q.replace(" ", "") or name.split("-")[0] in q
        )

    picked.sort(
        key=lambda item: (
            -item.score,
            -_name_hits(item.matched_skills),
            item.agent_id,
        )
    )
    if not picked:
        return []
    top = picked[0].score
    if top <= 1 and len(picked) > 1 and picked[1].score >= top:
        return []
    return picked[:limit]


def skill_route_reason(score: AgentRoutingScore) -> str:
    skills = "、".join(f"`{n}`" for n in score.matched_skills[:4])
    return f"Skill 匹配（{skills}）" if skills else "Skill 能力匹配"


async def llm_plan_routes_from_skills(
    db: Session,
    user: User,
    message: str,
    *,
    chat_history: list | None = None,
    prior_outcomes: list[str] | None = None,
) -> ResolvedSkillRoutes | None:
    """调度 LLM：读 skills.md + agents.md → 选 skill_id → 反查 Agent。"""
    from app.integrations.deepseek_client import chat_completion_message_async, is_configured

    if not is_configured():
        return None

    candidates = coarse_skill_candidates(
        db, user, message, prior_outcomes=prior_outcomes
    )
    if not candidates:
        return None

    index = build_skill_agent_index(db)
    allowed = {skill.name for skill in candidates}
    enabled_agents = frozenset(
        p.id
        for p in AGENT_PROFILES
        if p.id != "orchestrator" and is_agent_enabled(db, p.id)
    )
    skill_catalog = build_skill_route_catalog(candidates, index, db=db)
    agent_catalog = build_agents_catalog_text(enabled_ids=enabled_agents)
    catalog = f"{skill_catalog}\n\n{agent_catalog}"
    query = build_routing_query(message, prior_outcomes)

    from app.core.conversation_turn_context import is_likely_follow_up

    hist = ""
    if chat_history and is_likely_follow_up(message, chat_history):
        for msg in chat_history[-4:]:
            role = "用户" if getattr(msg, "role", "") == "user" else "助手"
            text = (getattr(msg, "content", "") or "").strip()[:160]
            if text:
                hist += f"{role}：{text}\n"

    system = (
        "你是平台调度层。根据用户目标，阅读【skills.md 候选】与【agents.md 专精目录】"
        "选出完成任务所需的 skill_id。\n"
        "你只选 Skill，不执行 Tool，不编造目录外的 skill_id；"
        "须同时核对 Skill 与专精 Agent 的 Use when / Don't，确保域一致。\n"
        "优先以【用户目标】当前句为准；仅当明显是追问/省略主语时再参考【近期对话】。\n"
        "若寒暄、常识、简单心算、基于上文追问可直接回答，设 orchestrator_direct=true 且 skills=[]。\n"
        "若均不匹配（置信度低），设 orchestrator_direct=true，勿强行选用无关 Skill。\n"
        '输出 JSON：{"orchestrator_direct":false,"mode":"single|sequential|parallel",'
        '"skills":["skill-id",...],"reason":"一句话"}\n'
        "规则：skills 1–4 个按执行先后；有依赖 → sequential，可并行 → parallel。"
    )
    user_prompt = f"【用户目标】\n{query[:900]}\n\n{catalog}"
    if hist:
        user_prompt = f"【近期对话】\n{hist}\n{user_prompt}"

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
        plan = parse_llm_skill_route_plan(parse_llm_json(content), allowed=allowed)
        if plan is None:
            return None
        return resolved_routes_from_skill_plan(plan, index)
    except Exception:
        _logger.exception("调度 Skill LLM 路由失败")
        return None
