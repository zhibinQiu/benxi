"""前端固定前缀指令：指定智能体 / 技能后硬路由。

前端注入格式（见 ``useAgentSelection``）::

    请让 {智能体展示名}：{问题}
    请使用 {技能名} 技能：{问题}

冒号前 = 能力选型（Catalog）；冒号后 = 语义分析正文（KG/本体只用这部分）。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from sqlalchemy.orm import Session

from app.models.org import User

DirectiveKind = Literal["agent", "skill"]

# 与前端 useAgent / useSkill 对齐；允许全角/半角冒号
_AGENT_DIRECTIVE_RE = re.compile(
    r"^\s*请让\s+(.+?)\s*[:：]\s*(.*)\s*$",
    re.S,
)
_SKILL_DIRECTIVE_RE = re.compile(
    r"^\s*请使用\s+(.+?)\s*技能\s*[:：]\s*(.*)\s*$",
    re.S,
)


@dataclass(frozen=True, slots=True)
class UserCapabilityDirective:
    kind: DirectiveKind
    raw_label: str
    body: str
    agent_id: str = ""
    skill_name: str = ""

    @property
    def resolved(self) -> bool:
        if self.kind == "agent":
            return bool(self.agent_id)
        return bool(self.skill_name)


def parse_user_capability_directive(message: str) -> UserCapabilityDirective | None:
    """只解析固定前缀，不查库。"""
    text = (message or "").strip()
    if not text:
        return None
    m = _AGENT_DIRECTIVE_RE.match(text)
    if m:
        label = (m.group(1) or "").strip()
        body = (m.group(2) or "").strip()
        if label:
            return UserCapabilityDirective(kind="agent", raw_label=label, body=body)
    m = _SKILL_DIRECTIVE_RE.match(text)
    if m:
        label = (m.group(1) or "").strip()
        body = (m.group(2) or "").strip()
        if label:
            return UserCapabilityDirective(kind="skill", raw_label=label, body=body)
    return None


def analysis_text_for_semantic(message: str) -> str:
    """KG/本体分析用文本：有固定前缀时只取冒号后；否则原文。"""
    d = parse_user_capability_directive(message)
    if d is None:
        return (message or "").strip()
    return (d.body or "").strip()


def _agent_display_name(title: str) -> str:
    base = (title or "").strip()
    if not base:
        return ""
    if re.search(r"\bAgent$", base, re.I):
        return base
    return f"{base} Agent"


def _fold(s: str) -> str:
    return re.sub(r"\s+", "", (s or "").strip()).casefold()


def _strip_agent_suffix(label: str) -> str:
    return re.sub(r"\s*Agent\s*$", "", (label or "").strip(), flags=re.I).strip()


def _resolve_agent_id(db: Session, label: str) -> str:
    from app.core.agent_profiles import AGENT_PROFILES
    from app.services.agent_profile_service import list_agent_profiles

    raw = (label or "").strip()
    if not raw:
        return ""
    folded = _fold(raw)
    bare = _fold(_strip_agent_suffix(raw))

    # 内置 profile（不依赖 DB）
    for p in AGENT_PROFILES:
        candidates = {
            _fold(p.id),
            _fold(p.title),
            _fold(_agent_display_name(p.title)),
            _fold(_strip_agent_suffix(p.title)),
        }
        if folded in candidates or (bare and bare in candidates):
            return p.id

    try:
        for row in list_agent_profiles(db):
            aid = str(getattr(row, "id", "") or "").strip()
            title = str(getattr(row, "title", "") or "").strip()
            candidates = {
                _fold(aid),
                _fold(title),
                _fold(_agent_display_name(title)),
                _fold(_strip_agent_suffix(title)),
            }
            if folded in candidates or (bare and bare in candidates):
                return aid
    except Exception:
        pass
    return ""


def _resolve_skill_name(db: Session, user: User | None, label: str) -> tuple[str, str]:
    """返回 (skill_name, prefer_agent_id)。"""
    from app.skills.catalog import list_all_skill_definitions
    from app.services.agent_skill_routing import build_skill_agent_index

    raw = (label or "").strip()
    if not raw:
        return "", ""
    folded = _fold(raw)
    try:
        defs = list_all_skill_definitions(db, user=user)
    except Exception:
        return "", ""
    hit_name = ""
    for d in defs:
        name = str(getattr(d, "name", "") or "").strip()
        title = str(getattr(d, "title", "") or getattr(d, "display_name", "") or "").strip()
        candidates = {_fold(name), _fold(title)}
        if folded in candidates:
            hit_name = name
            break
    if not hit_name:
        # 宽松：label 包含 skill name / title 被 label 包含
        for d in sorted(defs, key=lambda x: len(str(getattr(x, "name", "") or "")), reverse=True):
            name = str(getattr(d, "name", "") or "").strip()
            title = str(getattr(d, "title", "") or "").strip()
            if name and _fold(name) in folded:
                hit_name = name
                break
            if title and _fold(title) == folded:
                hit_name = name
                break
    if not hit_name:
        # 上传技能常不在 catalog 标题字段：直接按 slug 命中
        if re.fullmatch(r"[A-Za-z0-9][\w.-]{0,80}", raw):
            hit_name = raw
        else:
            return "", ""
    try:
        index = build_skill_agent_index(db)
        agent_id = str(index.get(hit_name) or "").strip()
    except Exception:
        agent_id = ""
    return hit_name, agent_id


def resolve_user_capability_directive(
    db: Session,
    message: str,
    *,
    user: User | None = None,
) -> UserCapabilityDirective | None:
    """解析并解析到具体 agent_id / skill_name。"""
    parsed = parse_user_capability_directive(message)
    if parsed is None:
        return None
    if parsed.kind == "agent":
        agent_id = _resolve_agent_id(db, parsed.raw_label)
        return UserCapabilityDirective(
            kind="agent",
            raw_label=parsed.raw_label,
            body=parsed.body,
            agent_id=agent_id,
        )
    skill_name, agent_id = _resolve_skill_name(db, user, parsed.raw_label)
    return UserCapabilityDirective(
        kind="skill",
        raw_label=parsed.raw_label,
        body=parsed.body,
        agent_id=agent_id,
        skill_name=skill_name,
    )
