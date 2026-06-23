"""Agent / Agentic RAG 问题规划缓存 — 归纳相似问题并复用已探索的执行方案。"""

from __future__ import annotations

import hashlib
import logging
import re
import uuid
from collections import Counter
from difflib import SequenceMatcher
from typing import Any

from app.config import get_settings
from app.core.platform_cache import cache_get_json, cache_set_json

_logger = logging.getLogger(__name__)

CACHE_PREFIX = "agent-plan-cache:v1"
PLAN_TYPE_AGENT_EXECUTION = "agent_execution"
PLAN_TYPE_KNOWLEDGE_QA = "knowledge_qa"

_PUNCT_RE = re.compile(r"[\s，,。.!！?？；;：:、~～…·\"'“”‘’（）()\[\]【】<>《》]+")
_CORE_SYNONYMS: tuple[tuple[str, str], ...] = (
    ("企业", "公司"),
    ("单位", "公司"),
    ("咋", "如何"),
    ("怎么", "如何"),
    ("怎样", "如何"),
    ("啥", "什么"),
    ("哪些", "什么"),
)


def _apply_core_synonyms(text: str) -> str:
    out = text
    for src, dst in _CORE_SYNONYMS:
        out = out.replace(src, dst)
    return out


_QUESTION_VARIANT_RE = re.compile(
    r"(怎么|如何|怎样|啥|什么|哪些|哪个|吗|呢|啊|吧|呀|嘛|了|的|请|帮|帮我|帮忙)"
)


def _strip_question_variants(text: str) -> str:
    """弱化问法差异，保留主题词。"""
    return _QUESTION_VARIANT_RE.sub("", text)


def _char_overlap_ratio(a: str, b: str) -> float:
    ca = Counter(a.replace(" ", ""))
    cb = Counter(b.replace(" ", ""))
    if not ca or not cb:
        return 0.0
    inter = sum((ca & cb).values())
    union = sum((ca | cb).values())
    return inter / union if union else 0.0


def _ngram_jaccard(a: str, b: str, n: int) -> float:
    if len(a) < n or len(b) < n:
        return 1.0 if a == b and a else 0.0
    grams_a = {a[i : i + n] for i in range(len(a) - n + 1)}
    grams_b = {b[i : i + n] for i in range(len(b) - n + 1)}
    if not grams_a or not grams_b:
        return 0.0
    return len(grams_a & grams_b) / len(grams_a | grams_b)


def plan_cache_enabled() -> bool:
    settings = get_settings()
    return bool(getattr(settings, "agent_plan_cache_enabled", True))


def _cache_ttl_sec() -> int:
    return max(300, int(getattr(get_settings(), "agent_plan_cache_ttl_sec", 86400) or 86400))


def _similarity_threshold() -> float:
    return max(
        0.5,
        min(
            0.99,
            float(getattr(get_settings(), "agent_plan_cache_similarity_threshold", 0.85) or 0.85),
        ),
    )


def _max_entries() -> int:
    return max(10, int(getattr(get_settings(), "agent_plan_cache_max_entries", 120) or 120))


def normalize_question(text: str) -> str:
    """归一化用户问题，便于精确/相似匹配。"""
    raw = (text or "").strip()
    if not raw:
        return ""
    lowered = raw.casefold()
    collapsed = _PUNCT_RE.sub(" ", lowered)
    normalized = " ".join(collapsed.split())
    return _apply_core_synonyms(normalized)


def question_similarity(a: str, b: str) -> float:
    """0~1 文本相似度：序列匹配 + n-gram Jaccard + 字符重叠。"""
    na = normalize_question(a)
    nb = normalize_question(b)
    if not na or not nb:
        return 0.0
    if na == nb:
        return 1.0

    seq = SequenceMatcher(None, na, nb).ratio()
    char_overlap = _char_overlap_ratio(na, nb)
    bigram = _ngram_jaccard(na, nb, 2)
    trigram = _ngram_jaccard(na, nb, 3)

    core_a = _strip_question_variants(na)
    core_b = _strip_question_variants(nb)
    core_seq = SequenceMatcher(None, core_a, core_b).ratio() if core_a and core_b else 0.0
    core_overlap = _char_overlap_ratio(core_a, core_b) if core_a and core_b else 0.0

    shorter, longer = (na, nb) if len(na) <= len(nb) else (nb, na)
    contain_boost = 0.1 if shorter in longer and len(shorter) >= 6 else 0.0

    score = max(seq, bigram, trigram, char_overlap, core_seq, core_overlap) + contain_boost
    return min(1.0, score)


def _scope_hash(parts: list[str]) -> str:
    joined = "|".join(p for p in parts if p)
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()[:16]


def agent_execution_scope_key(
    user_id: uuid.UUID,
    *,
    available_atomic_tools: set[str] | frozenset[str],
    builtin_skills: set[str],
    uploaded_skills: set[str],
) -> str:
    atomic = ",".join(sorted(available_atomic_tools))
    builtin = ",".join(sorted(builtin_skills))
    uploaded = ",".join(sorted(uploaded_skills))
    digest = _scope_hash([atomic, builtin, uploaded])
    return f"{CACHE_PREFIX}:{PLAN_TYPE_AGENT_EXECUTION}:{user_id}:{digest}"


def knowledge_qa_scope_key(user_id: uuid.UUID, doc_ids: list[uuid.UUID]) -> str:
    doc_part = ",".join(sorted(str(d) for d in doc_ids))
    digest = _scope_hash([doc_part])
    return f"{CACHE_PREFIX}:{PLAN_TYPE_KNOWLEDGE_QA}:{user_id}:{digest}"


def _load_index(scope_key: str) -> list[dict[str, Any]]:
    data = cache_get_json(scope_key, ttl=_cache_ttl_sec())
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    return []


def _save_index(scope_key: str, entries: list[dict[str, Any]]) -> None:
    cache_set_json(scope_key, entries[: _max_entries()], ttl=_cache_ttl_sec())


def lookup_cached_payload(
    scope_key: str,
    question: str,
    *,
    plan_type: str,
) -> dict[str, Any] | None:
    """查找相似问题的已缓存方案；命中时返回 entry（含 payload）。"""
    if not plan_cache_enabled():
        return None
    normalized = normalize_question(question)
    if not normalized:
        return None

    entries = _load_index(scope_key)
    if not entries:
        return None

    threshold = _similarity_threshold()
    best: dict[str, Any] | None = None
    best_score = 0.0

    for entry in entries:
        if str(entry.get("plan_type") or "") != plan_type:
            continue
        entry_norm = str(entry.get("normalized") or entry.get("question") or "")
        entry_intent = str(entry.get("intent") or "")
        score_q = question_similarity(normalized, entry_norm)
        score_intent = question_similarity(normalized, entry_intent) if entry_intent else 0.0
        score = max(score_q, score_intent * 0.98)
        if score >= threshold and score > best_score:
            best = entry
            best_score = score

    if not best:
        return None

    hit_count = int(best.get("hit_count") or 0) + 1
    best["hit_count"] = hit_count
    _save_index(scope_key, entries)
    payload = best.get("payload")
    if not isinstance(payload, dict):
        return None
    _logger.info(
        "agent plan cache hit type=%s score=%.3f question=%r",
        plan_type,
        best_score,
        (question or "")[:80],
    )
    return {
        **best,
        "similarity": best_score,
        "payload": dict(payload),
    }


def store_cached_payload(
    scope_key: str,
    question: str,
    *,
    plan_type: str,
    intent: str,
    payload: dict[str, Any],
) -> None:
    """写入或更新问题规划缓存。"""
    if not plan_cache_enabled():
        return
    normalized = normalize_question(question)
    if not normalized or not payload:
        return

    entries = _load_index(scope_key)
    for entry in entries:
        if str(entry.get("plan_type") or "") != plan_type:
            continue
        if normalize_question(str(entry.get("normalized") or entry.get("question") or "")) == normalized:
            entry["question"] = (question or "").strip()[:500]
            entry["normalized"] = normalized
            entry["intent"] = (intent or "").strip()[:240]
            entry["payload"] = payload
            _save_index(scope_key, entries)
            return

    entries.insert(
        0,
        {
            "question": (question or "").strip()[:500],
            "normalized": normalized,
            "intent": (intent or "").strip()[:240],
            "plan_type": plan_type,
            "payload": payload,
            "hit_count": 0,
        },
    )
    _save_index(scope_key, entries[: _max_entries()])


def execution_plan_to_payload(plan: Any) -> dict[str, Any]:
    return {
        "reasoning": plan.reasoning,
        "intent": plan.intent,
        "direct_answer": plan.direct_answer,
        "atomic_tools": list(plan.atomic_tools),
        "skip_tools": list(plan.skip_tools),
        "uploaded_skill": plan.uploaded_skill,
        "builtin_orchestration": plan.builtin_orchestration,
        "steps": list(plan.steps),
    }


def execution_plan_from_payload(data: dict[str, Any], *, source: str = "cache"):
    from app.services.agent_planner import AgentExecutionPlan

    return AgentExecutionPlan(
        reasoning=str(data.get("reasoning") or "").strip(),
        intent=str(data.get("intent") or "").strip(),
        direct_answer=bool(data.get("direct_answer")),
        atomic_tools=tuple(str(x) for x in (data.get("atomic_tools") or []) if str(x).strip()),
        skip_tools=tuple(str(x) for x in (data.get("skip_tools") or []) if str(x).strip()),
        uploaded_skill=str(data.get("uploaded_skill")).strip()
        if data.get("uploaded_skill")
        else None,
        builtin_orchestration=str(data.get("builtin_orchestration")).strip()
        if data.get("builtin_orchestration")
        else None,
        steps=tuple(str(x) for x in (data.get("steps") or []) if str(x).strip()),
        source=source,
    )


def cache_hit_summary(entry: dict[str, Any]) -> str:
    intent = str(entry.get("intent") or "").strip()
    matched = str(entry.get("question") or "").strip()
    score = float(entry.get("similarity") or 0.0)
    parts = ["命中问题缓存"]
    if intent:
        parts.append(f"意图：{intent}")
    if matched and normalize_question(matched) != normalize_question(str(entry.get("lookup_question") or "")):
        parts.append(f"相似问题：{matched[:60]}")
    if score > 0:
        parts.append(f"相似度 {score:.0%}")
    return "；".join(parts)[:240]
