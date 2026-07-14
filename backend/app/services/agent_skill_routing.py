"""调度路由 — LLM 读取 skills.md / agents.md 后规划 Skill 选型，反查专精 Agent。

Skill 路由三阶段：
  1. 信号层（agent_skill_router）：用户消息意图检测
  2. 规划层（本文件）：LLM 读取路由目录后选 Skill → 反查 Agent
  3. 评分层（agent_skill_match）：关键词召回 → 相似度归一化 → Agent 聚合评分

倒排索引：```skill_name → agent_id```（一对一，一个 Skill 只会分配给一个 Agent）。
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from app.core.agent_profiles import AGENT_PROFILES
from app.core.llm_parse import parse_llm_json
from app.core.routing_catalog_md import (
    _truncate as _truncate_md,
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

# ── 进程级倒排索引缓存 ─────────────────────────────────────────────────────
# skill_name → agent_id（一对一）；None 表示尚未构建
_SKILL_AGENT_INDEX: dict[str, str] | None = None
_SKILL_INDEX_TS: float = 0.0
_SKILL_INDEX_TTL = 60.0  # 秒

# ── 无专精声明的 Skill → 兜底 orchestrator ────────────────────────────────
_ORCHESTRATOR_SKILLS: frozenset[str] = frozenset({
    "knowledge-research", "free-web-ai", "mermaid-diagram",
    "pdf-translate", "speech-to-text", "text-to-speech", "ocr",
    "document-compare", "report-generation", "data-analysis",
    "smart-data-query",
})


def clear_skill_agent_index_cache() -> None:
    global _SKILL_AGENT_INDEX, _SKILL_INDEX_TS
    _SKILL_AGENT_INDEX = None
    _SKILL_INDEX_TS = 0.0


def build_skill_agent_index(db: Session) -> dict[str, str]:
    """构建 skill_name → agent_id 倒排索引（一对一）。
    
    同一 Skill 被多个 Agent 声明时取 AGENT_DEFAULT_SKILLS 优先的那个，
    并记 warning 日志提醒管理员修复。
    """
    global _SKILL_AGENT_INDEX, _SKILL_INDEX_TS
    now = time.monotonic()
    if _SKILL_AGENT_INDEX is not None and now - _SKILL_INDEX_TS < _SKILL_INDEX_TTL:
        return _SKILL_AGENT_INDEX

    index: dict[str, str] = {}
    # 先按默认绑定填写（优先级低）
    for agent_id, defaults in AGENT_DEFAULT_SKILLS.items():
        for name in defaults:
            if name not in index:
                index[name] = agent_id

    # 再查 DB（优先级高，覆盖默认）
    for profile in AGENT_PROFILES:
        if profile.id == "orchestrator":
            continue
        if not is_agent_enabled(db, profile.id):
            continue
        for skill_name in resolve_agent_skill_names(db, profile.id):
            existing = index.get(skill_name)
            if existing is not None and existing != profile.id:
                _logger.warning(
                    "Skill `%s` 被多个 Agent 声明: %s 和 %s，取 %s（按 %s 优先）",
                    skill_name, existing, profile.id, existing,
                    "AGENT_DEFAULT_SKILLS 绑定" if skill_name in AGENT_DEFAULT_SKILLS.get(existing, ()) else "DB 注册次序",
                )
                # 已有绑定时不覆盖（先到先得）
                if skill_name in AGENT_DEFAULT_SKILLS.get(profile.id, ()):
                    index[skill_name] = profile.id
                continue
            index[skill_name] = profile.id

    _SKILL_AGENT_INDEX = index
    _SKILL_INDEX_TS = now
    return index


def lookup_agent_for_skill(skill_name: str, index: dict[str, str]) -> str:
    """从倒排索引查找 Skill 对应的 Agent，无匹配时返回 orchestrator。"""
    agent = index.get(skill_name)
    if agent is not None:
        return agent
    if skill_name in _ORCHESTRATOR_SKILLS:
        return "orchestrator"
    return "orchestrator"


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
    index: dict[str, str],
    *,
    db: Session | None = None,
) -> str:
    """构建 LLM 可见的技能目录（已绑定专精 Agent）。"""
    lines = [
        "候选 Skill（仅可从下列 skill_id 选择，勿编造）：",
        "",
    ]
    for skill in skills:
        agent = index.get(skill.name, "orchestrator")
        use = (skill.use_when or skill.description or "").strip()
        short_use = _truncate_md(use) if use else ""
        tag = ""
        if skill.source == SkillSource.UPLOADED and db is not None:
            from app.services.agent_skill_service import uploaded_skill_has_script
            tag = uploaded_skill_tag(has_script=uploaded_skill_has_script(db, skill.name))
        elif skill.source == SkillSource.BUILTIN:
            tag = "[builtin]"
        name_part = f"`{skill.name}`"
        if tag:
            name_part = f"{name_part} {tag}"
        line = f"- {name_part}"
        if short_use:
            line += f" {short_use}"
        line += f" → {agent}"
        lines.append(line)
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
    return plan.model_copy(update={"skills": skills}) if skills != plan.skills else plan


def _pick_agent_for_skill(skill_name: str, index: dict[str, str]) -> str:
    return lookup_agent_for_skill(skill_name, index)


def agents_from_skill_selection(
    skill_ids: list[str],
    index: dict[str, str],
) -> list[tuple[str, list[str]]]:
    """按 LLM 选定 Skill 顺序反查专精 Agent（同一 Agent 合并 Skill）。

    无专精 Agent 声明的 Skill 映射到 orchestrator。
    """
    order: list[str] = []
    grouped: dict[str, list[str]] = {}
    for skill_id in skill_ids:
        agent_id = _pick_agent_for_skill(skill_id, index)
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
    index: dict[str, str],
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
    skill_agent_index: dict[str, str],
    *,
    failed_agent_ids: frozenset[str] | None = None,
) -> list[AgentRoutingScore]:
    totals: dict[str, float] = {}
    matched: dict[str, list[str]] = {}
    failed = failed_agent_ids or frozenset()

    for relevance, skill in ranked_skills:
        if relevance <= 0:
            continue
        agent_id = lookup_agent_for_skill(skill.name, skill_agent_index)
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
    index: dict[str, str] | None = None,
) -> list[AgentRoutingScore]:
    """关键词评分路由：用倒排索引（优先传入）加速查 Agent 映射。"""
    query = build_routing_query(message, prior_outcomes)
    skills = [
        s
        for s in list_all_skill_definitions(db, user=user, catalog_only=False)
        if s.readiness not in (SkillReadiness.DISABLED, SkillReadiness.NO_PERMISSION)
    ]
    ranked = _rank_skills_for_routing(query, skills, limit=12)
    if not ranked:
        return []
    if index is None:
        index = build_skill_agent_index(db)
    failed: set[str] = set()
    for raw in prior_outcomes or []:
        failed.update(parse_failed_agents_from_text(str(raw or "")))
    return aggregate_agents_from_skills(
        ranked,
        index,
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


def _find_direct_skill_match(
    message: str,
    index: dict[str, str],
) -> str | None:
    """快速路径：消息中直接包含已知 Skill 名 → O(1) 返回对应 Agent ID。

    纯关键词匹配，比完整路由快 1000x。
    """
    msg = (message or "").strip().lower()
    for skill_name in index:
        if skill_name in msg:
            return index[skill_name]
    return None


def resolve_agent_from_message_fast(
    db: Session | None,
    message: str,
    index: dict[str, str] | None = None,
) -> str | None:
    """快速路由：直接扫描消息中的 Skill 名，匹配则返回 Agent。

    完全绕过 LLM 路由和关键词评分路由链路。返回 None 表示无法快速决策。
    可以传入预构建的 index 避免额外 DB 查询。
    """
    msg = (message or "").strip()
    if not msg or len(msg) < 4:
        return None
    if index is None:
        if db is None:
            return None
        index = build_skill_agent_index(db)
    return _find_direct_skill_match(msg, index)


async def llm_plan_routes_from_skills(
    db: Session,
    user: User,
    message: str,
    *,
    chat_history: list | None = None,
    prior_outcomes: list[str] | None = None,
    index: dict[str, str] | None = None,
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

    if index is None:
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
