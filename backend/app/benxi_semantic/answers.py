"""从语义层决策上下文生成可直接交付的用户答复（无 IO）。

判定依据：has_material / confidence / ABox 片段，不按问题类型写死路由。
"""

from __future__ import annotations

import re

from .models import AgentDecisionContext

# 置信度阈值：达到则认为图谱材料足以直接作答
DIRECT_ANSWER_MIN_CONFIDENCE = 0.6

_AFFILIATION_ORG_RE = re.compile(r"所属组织:\s*(.+)")
_ENTITY_TITLE_RE = re.compile(r"\[\d+\]\s*[^\n·]*·\s*(.+)")
_EMPTY_MARKERS = ("未匹配到", "未从问题中识别", "当前图谱为空")


def _parse_affiliation_orgs(snippets: str) -> list[str]:
    orgs: list[str] = []
    for m in _AFFILIATION_ORG_RE.finditer(snippets or ""):
        for part in re.split(r"[、,，;/|]", m.group(1)):
            name = part.strip()
            if name:
                orgs.append(name)
    return list(dict.fromkeys(orgs))


def _primary_entity_name(ctx: AgentDecisionContext) -> str | None:
    for ent in ctx.matched_entities:
        name = (ent.name or "").strip()
        if name:
            return name
    m = _ENTITY_TITLE_RE.search(ctx.abox_snippets or "")
    if m:
        return m.group(1).strip()
    return None


def _snippets_usable(snippets: str) -> bool:
    text = (snippets or "").strip()
    if len(text) < 12:
        return False
    return not any(m in text for m in _EMPTY_MARKERS)


def _memory_direct_answer(ctx: AgentDecisionContext) -> str | None:
    """点赞写入的 memory 实体：直接用 description 作答。"""
    for ent in ctx.matched_entities or []:
        if (ent.type_code or "").strip() != "memory":
            continue
        desc = (ent.description or "").strip()
        if len(desc) >= 8:
            return desc[:1200]
    # 兜底：从 ABox「描述:」行取
    for raw in (ctx.abox_snippets or "").splitlines():
        line = raw.strip()
        if line.startswith("描述:"):
            body = line[3:].strip()
            if len(body) >= 8:
                return body[:1200]
    return None


def can_answer_from_decision(ctx: AgentDecisionContext | None) -> bool:
    """图谱材料是否足以跳过 Skill/Agent 匹配直接作答。"""
    if ctx is None or not ctx.has_material:
        return False
    if _memory_direct_answer(ctx):
        return True
    if float(ctx.confidence or 0.0) < DIRECT_ANSWER_MIN_CONFIDENCE:
        return False
    if not _snippets_usable(ctx.abox_snippets or ""):
        return False
    preferred = list(ctx.preferred_tools or [])
    if preferred and preferred[0] != "kg_query":
        # 仍允许：有明确 ABox 事实时直答
        if not _AFFILIATION_ORG_RE.search(ctx.abox_snippets or ""):
            return False
    return True


def try_direct_answer_from_decision(
    ctx: AgentDecisionContext | None,
    question: str = "",
) -> str | None:
    """图谱已命中且足以回答时返回用户可见正文；否则 None（继续 Skill/Agent 匹配）。"""
    _ = (question or "").strip()
    if not can_answer_from_decision(ctx):
        return None
    assert ctx is not None

    memory_reply = _memory_direct_answer(ctx)
    if memory_reply:
        return memory_reply

    snippets = ctx.abox_snippets or ""
    orgs = _parse_affiliation_orgs(snippets)
    if orgs:
        person = _primary_entity_name(ctx)
        org_text = "、".join(orgs)
        if person:
            return f"{person}属于{org_text}。"
        return f"所属组织为{org_text}。"
    # 通用：压缩 ABox 片段为可读答复（去掉标题行前缀）
    lines: list[str] = []
    for raw in snippets.splitlines():
        line = raw.strip()
        if not line or line.startswith("【"):
            continue
        if line.startswith("[") and "·" in line:
            # [1] 类型 · 名称 → 名称
            m = _ENTITY_TITLE_RE.match(line)
            lines.append(m.group(1).strip() if m else line)
            continue
        lines.append(line.lstrip("→← ").strip() if line[:1] in "→←" else line)
    body = "\n".join(lines).strip()
    if len(body) < 8:
        return None
    return body[:1200]
