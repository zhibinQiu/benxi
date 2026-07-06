"""Skill 匹配评分 — 关键词召回 → 相似度归一化 → Agent 聚合 → 判定路由可行性。

评分三阶段：
  1. 召回：从所有 Skill 定义中根据关键词筛选候选
  2. 归一化：将原始相似度评分归一化为 [0,1] 
  3. 聚合评分：按 Agent 分组聚合 Skill 匹配得分，判定匹配等级（full/partial/weak/none）
  
依赖 agent_skill_routing 的粗筛与 LLM 路由能力。"""


from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.org import User
from app.services.agent_skill_routing import (
    AgentRoutingScore,
    build_routing_query,
    pick_skill_route_scores,
    resolve_skill_routed_agent_scores,
)
from agentkit_skills.search import rank_skills_by_query, skill_query_tokens
from app.skills.catalog import list_all_skill_definitions
from app.skills.types import SkillDefinition, SkillReadiness

SkillMatchKind = Literal["full", "none", "weak", "partial"]


@dataclass(frozen=True, slots=True)
class SkillMatchAssessment:
    """Skill 召回后的匹配判定（供调度兜底链路使用）。"""

    kind: SkillMatchKind
    max_similarity: float
    top_skills: tuple[str, ...]
    agent_scores: tuple[AgentRoutingScore, ...]
    missing_skill_tags: tuple[str, ...] = ()


def _normalize_keyword_score(score: int, query: str) -> float:
    tokens = skill_query_tokens(query)
    if score <= 0 or not tokens:
        return 0.0
    ceiling = max(1, 3 * len(tokens))
    return min(1.0, float(score) / float(ceiling))


def rank_skills_with_similarity(
    db: Session,
    user: User,
    message: str,
    *,
    prior_outcomes: list[str] | None = None,
    limit: int = 12,
) -> list[tuple[float, int, SkillDefinition]]:
    query = build_routing_query(message, prior_outcomes)
    skills = [
        s
        for s in list_all_skill_definitions(db, user=user, catalog_only=False)
        if s.readiness not in (SkillReadiness.DISABLED, SkillReadiness.NO_PERMISSION)
    ]
    ranked = rank_skills_by_query(query, skills, limit=limit)
    out: list[tuple[float, int, SkillDefinition]] = []
    for score, skill in ranked:
        if score <= 0:
            continue
        out.append((_normalize_keyword_score(score, query), score, skill))
    return out


def list_platform_skill_summaries(
    db: Session,
    user: User,
) -> list[tuple[str, str]]:
    """(skill_id, 简述) 列表，供能力说明与 LLM 拆解使用。"""
    rows: list[tuple[str, str]] = []
    for skill in list_all_skill_definitions(db, user=user, catalog_only=False):
        if skill.readiness in (SkillReadiness.DISABLED, SkillReadiness.NO_PERMISSION):
            continue
        label = (skill.title or skill.name).strip()
        desc = (skill.use_when or skill.description or "").strip()
        rows.append((skill.name, f"{label}：{desc}"[:200] if desc else label))
    return rows


def supported_capability_labels(
    db: Session,
    user: User,
    *,
    limit: int = 24,
) -> tuple[str, ...]:
    labels: list[str] = []
    for _name, summary in list_platform_skill_summaries(db, user)[:limit]:
        head = summary.split("：", 1)[0].strip()
        if head and head not in labels:
            labels.append(head)
    return tuple(labels)


def assess_skill_match(
    db: Session,
    user: User,
    message: str,
    *,
    prior_outcomes: list[str] | None = None,
) -> SkillMatchAssessment:
    """召回 + 归一化相似度 + Agent 聚合，判定是否可路由专精 Agent。"""
    query = build_routing_query(message, prior_outcomes)
    ranked = rank_skills_with_similarity(
        db, user, message, prior_outcomes=prior_outcomes
    )
    threshold = float(get_settings().agent_skill_match_threshold or 0.3)

    agent_scores = tuple(
        pick_skill_route_scores(
            resolve_skill_routed_agent_scores(
                db, user, message, prior_outcomes=prior_outcomes
            ),
            query=(message or "").strip(),
        )
    )
    top_skills = tuple(skill.name for _, _, skill in ranked[:6])
    top_agent_score = agent_scores[0].score if agent_scores else 0.0

    if not ranked and not agent_scores:
        return SkillMatchAssessment(
            kind="none",
            max_similarity=0.0,
            top_skills=(),
            agent_scores=agent_scores,
        )

    max_sim = ranked[0][0] if ranked else 0.0

    if agent_scores and top_agent_score >= 3.0:
        if (
            len(ranked) > 1
            and ranked[1][0] >= threshold
            and max_sim < threshold * 1.8
        ):
            tags = tuple(_infer_gap_tags_from_query(query))
            return SkillMatchAssessment(
                kind="partial",
                max_similarity=max_sim,
                top_skills=top_skills,
                agent_scores=agent_scores,
                missing_skill_tags=tags,
            )
        return SkillMatchAssessment(
            kind="full",
            max_similarity=max_sim,
            top_skills=top_skills,
            agent_scores=agent_scores,
        )

    if max_sim < threshold:
        return SkillMatchAssessment(
            kind="none",
            max_similarity=max_sim,
            top_skills=top_skills,
            agent_scores=agent_scores,
        )

    if not agent_scores:
        tags = tuple(_infer_gap_tags_from_query(query))
        return SkillMatchAssessment(
            kind="weak",
            max_similarity=max_sim,
            top_skills=top_skills,
            agent_scores=agent_scores,
            missing_skill_tags=tags,
        )

    if len(ranked) > 1:
        second_sim = ranked[1][0]
        if second_sim >= threshold and max_sim < threshold * 1.8:
            tags = tuple(_infer_gap_tags_from_query(query))
            return SkillMatchAssessment(
                kind="partial",
                max_similarity=max_sim,
                top_skills=top_skills,
                agent_scores=agent_scores,
                missing_skill_tags=tags,
            )

    return SkillMatchAssessment(
        kind="full",
        max_similarity=max_sim,
        top_skills=top_skills,
        agent_scores=agent_scores,
    )


def _infer_gap_tags_from_query(query: str) -> list[str]:
    """从用户表述提取能力标签（通用分词，无领域词表）。"""
    tags: list[str] = []
    for token in skill_query_tokens(query):
        if len(token) >= 2 and token not in tags:
            tags.append(token)
        if len(tags) >= 6:
            break
    return tags


def format_missing_skill_context_line(tags: tuple[str, ...]) -> str:
    if not tags:
        return ""
    return "缺失能力标签：" + "、".join(tags)
