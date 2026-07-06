"""Skill 关键词搜索与排名 — 纯算法，零 I/O 依赖。"""

from __future__ import annotations

import re

from agentkit_skills.types import SkillDefinition


def skill_query_tokens(query: str) -> list[str]:
    """将用户查询拆分为可匹配的 Token（中文二元/三元 + 英文 slug）。"""
    q = (query or "").strip().lower()
    if not q:
        return []
    tokens: list[str] = []
    parts = re.split(r"[\s,，、/]+", q)
    for part in parts:
        p = part.strip().lower()
        if len(p) >= 2:
            tokens.append(p)
        if re.fullmatch(r"https?://[^\s]+", p):
            tokens.extend(re.findall(r"[a-z][a-z0-9-]{2,}", p))
    for run in re.findall(r"[\u4e00-\u9fff]+", q):
        if len(run) >= 2:
            tokens.append(run)
            for i in range(len(run) - 1):
                tokens.append(run[i : i + 2])
    return list(dict.fromkeys(tokens))


def _skill_search_haystack(skill: SkillDefinition) -> str:
    return " ".join(
        filter(
            None,
            (
                skill.name,
                skill.description,
                skill.use_when or "",
                skill.dont_use_when or "",
                skill.title or "",
            ),
        )
    ).lower()


def rank_skills_by_query(
    query: str,
    skills: list[SkillDefinition],
    *,
    limit: int | None = None,
    resident_boost: float = 1.15,
) -> list[tuple[int, SkillDefinition]]:
    """按 Query 对 Skill 列表打分排序。

    Args:
        query: 用户搜索关键词。
        skills: 候选 Skill 列表。
        limit: 返回数量上限。
        resident_boost: 常住 Skill 的得分放大系数（默认 1.15）。
    """
    tokens = skill_query_tokens(query)
    if not tokens:
        ordered = list(skills)
        if limit is not None and limit > 0:
            ordered = ordered[:limit]
        return [(0, skill) for skill in ordered]

    scored: list[tuple[int, SkillDefinition]] = []
    for skill in skills:
        name_l = skill.name.lower()
        use_l = (skill.use_when or "").lower()
        hay = _skill_search_haystack(skill)
        score = 0
        for t in tokens:
            if t in use_l:
                score += 3
            elif t in name_l:
                score += 2
            elif t in hay:
                score += 1
        if score > 0 and skill.catalog_tier == "resident":
            score = int(round(score * resident_boost))
        if score > 0:
            scored.append((score, skill))
    scored.sort(key=lambda item: (-item[0], item[1].name))
    if limit is not None and limit > 0:
        scored = scored[:limit]
    return scored
