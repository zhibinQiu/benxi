"""Skill / Agent 路由用进程内 Embedding 索引。

- Skill：对技能文档向量化，Top-K 语义召回后再走 skill→agent 倒排索引。
- Agent：对 agents.md 条目向量化，专精智能体直匹配走同一套 RAG。

依赖平台已配置的 Embedding（``get_embedding_credentials``），失败时返回 None，
调用方回退关键词匹配。索引按文档指纹缓存，TTL 默认 5 分钟；写操作可主动 invalidate。
"""

from __future__ import annotations

import hashlib
import logging
import threading
import time
from dataclasses import dataclass
from typing import Any

import httpx
import numpy as np
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.routing_catalog_md import RoutingEntry, load_agents_routing_md, load_skills_routing_md
from app.skills.types import SkillDefinition

_logger = logging.getLogger(__name__)

_EMBED_TIMEOUT = 15.0
_INDEX_TTL_SEC = 300.0
_BATCH_SIZE = 32
_DEFAULT_TOP_K = 8

_lock = threading.RLock()
_index: "_EmbeddingIndex | None" = None
_agent_index: "_EmbeddingIndex | None" = None


def invalidate_skill_embedding_index() -> None:
    """Skill 上传/更新/删除后清空进程内索引，下次查询重建。"""
    global _index
    with _lock:
        _index = None


def invalidate_agent_embedding_index() -> None:
    """agents.md 变更后清空 Agent 向量索引。"""
    global _agent_index
    with _lock:
        _agent_index = None


def skill_routing_document(skill: SkillDefinition) -> str:
    """拼装用于 Embedding 的技能文档（优先 skills.md 路由文案）。"""
    name = (skill.name or "").strip()
    desc = (skill.description or "").strip()
    body = (getattr(skill, "body", None) or "").strip()
    use_when = (getattr(skill, "use_when", None) or "").strip()
    parts: list[str] = []
    if name:
        parts.append(f"技能名: {name}")
    md_hit = False
    try:
        entry = load_skills_routing_md().get(name)
        if entry is not None:
            md_hit = True
            if entry.title:
                parts.append(f"标题: {entry.title}")
            if entry.use_when:
                parts.append(f"适用场景: {entry.use_when}")
            if entry.dont_use_when:
                parts.append(f"不适用: {entry.dont_use_when}")
            if entry.output:
                parts.append(f"输出: {entry.output}")
    except Exception:
        pass
    if not md_hit:
        if use_when:
            parts.append(f"适用场景: {use_when}")
        if desc:
            parts.append(f"描述: {desc}")
    if body:
        parts.append(f"正文摘要: {body[:1200]}")
    return "\n".join(parts).strip() or name


def agent_routing_document(entry: RoutingEntry) -> str:
    """拼装用于 Embedding 的专精 Agent 文档。"""
    parts: list[str] = []
    if entry.id:
        parts.append(f"智能体: {entry.id}")
    if entry.title:
        parts.append(f"名称: {entry.title}")
    if entry.use_when:
        parts.append(f"适用场景: {entry.use_when}")
    if entry.dont_use_when:
        parts.append(f"不适用: {entry.dont_use_when}")
    if entry.skills:
        parts.append(f"绑定技能: {entry.skills}")
    if entry.output:
        parts.append(f"输出: {entry.output}")
    return "\n".join(parts).strip() or (entry.id or "")


def _docs_fingerprint(model: str, docs: dict[str, str]) -> str:
    h = hashlib.sha256()
    h.update((model or "").encode("utf-8"))
    for name in sorted(docs.keys()):
        h.update(b"\0")
        h.update(name.encode("utf-8"))
        h.update(b"\0")
        h.update(docs[name].encode("utf-8"))
    return h.hexdigest()


def _l2_normalize(matrix: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms = np.maximum(norms, 1e-12)
    return matrix / norms


def embed_texts(
    texts: list[str],
    *,
    base_url: str,
    api_key: str,
    model: str,
) -> list[np.ndarray] | None:
    """调用 OpenAI 兼容 embeddings API；失败返回 None。"""
    if not texts:
        return []
    url = f"{base_url.rstrip('/')}/embeddings"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    out: list[np.ndarray] = []
    try:
        with httpx.Client(timeout=_EMBED_TIMEOUT) as client:
            for i in range(0, len(texts), _BATCH_SIZE):
                batch = texts[i : i + _BATCH_SIZE]
                payload: dict[str, Any] = {"model": model, "input": batch}
                resp = client.post(url, headers=headers, json=payload)
                if resp.status_code >= 400:
                    _logger.warning(
                        "skill/agent embedding HTTP %s: %s",
                        resp.status_code,
                        (resp.text or "")[:200],
                    )
                    return None
                data = resp.json()
                items = data.get("data") or []
                if len(items) != len(batch):
                    _logger.warning("embedding count mismatch: got=%s want=%s", len(items), len(batch))
                    return None
                ordered = sorted(items, key=lambda x: int(x.get("index", 0)))
                for item in ordered:
                    emb = item.get("embedding")
                    if not isinstance(emb, list) or not emb:
                        return None
                    out.append(np.asarray(emb, dtype=np.float32))
    except Exception as exc:
        _logger.warning("skill/agent embedding failed: %s", exc)
        return None
    return out


@dataclass
class _EmbeddingIndex:
    fingerprint: str
    model: str
    names: list[str]
    matrix: np.ndarray  # (n, dim) L2-normalized
    built_at: float


def _get_credentials(db: Session | None) -> tuple[str, str, str] | None:
    from app.services.model_settings_service import get_embedding_credentials

    base, key, model = get_embedding_credentials(db)
    if not (base or "").strip() or not (key or "").strip() or not (model or "").strip():
        return None
    return base.strip(), key.strip(), model.strip()


def _build_or_reuse_index(
    *,
    cache_attr: str,
    docs: dict[str, str],
    creds: tuple[str, str, str],
    label: str,
) -> _EmbeddingIndex | None:
    global _index, _agent_index
    base, key, model = creds
    fingerprint = _docs_fingerprint(model, docs)
    now = time.monotonic()
    with _lock:
        current = _index if cache_attr == "skill" else _agent_index
        if (
            current is not None
            and current.fingerprint == fingerprint
            and (now - current.built_at) < _INDEX_TTL_SEC
        ):
            return current

        names = sorted(docs.keys())
        texts = [docs[n] for n in names]
        vectors = embed_texts(texts, base_url=base, api_key=key, model=model)
        if vectors is None or len(vectors) != len(names):
            return None
        matrix = _l2_normalize(np.stack(vectors, axis=0))
        built = _EmbeddingIndex(
            fingerprint=fingerprint,
            model=model,
            names=names,
            matrix=matrix,
            built_at=now,
        )
        if cache_attr == "skill":
            _index = built
        else:
            _agent_index = built
        _logger.info("%s embedding index rebuilt: n=%s model=%s", label, len(names), model)
        return built


def _ensure_skill_index(
    db: Session | None,
    skills: list[SkillDefinition],
) -> _EmbeddingIndex | None:
    settings = get_settings()
    if not settings.agent_skill_rag_enabled:
        return None
    creds = _get_credentials(db)
    if creds is None:
        return None
    docs = {s.name: skill_routing_document(s) for s in skills if (s.name or "").strip()}
    if not docs:
        return None
    return _build_or_reuse_index(cache_attr="skill", docs=docs, creds=creds, label="skill")


def _ensure_agent_index(db: Session | None) -> tuple[_EmbeddingIndex | None, list[RoutingEntry]]:
    settings = get_settings()
    if not settings.agent_skill_rag_enabled:
        return None, []
    creds = _get_credentials(db)
    if creds is None:
        return None, []
    try:
        raw = load_agents_routing_md()
        entries = [
            e
            for eid, e in raw.items()
            if eid and eid != "orchestrator"
        ]
    except Exception:
        return None, []
    if not entries:
        return None, []
    docs = {e.id: agent_routing_document(e) for e in entries}
    idx = _build_or_reuse_index(cache_attr="agent", docs=docs, creds=creds, label="agent")
    return idx, entries


def _rank_names(
    index: _EmbeddingIndex,
    query: str,
    *,
    creds: tuple[str, str, str],
    limit: int,
    min_similarity: float,
) -> list[tuple[str, float]] | None:
    base, key, model = creds
    q_vecs = embed_texts([query], base_url=base, api_key=key, model=model)
    if not q_vecs:
        return None
    q = _l2_normalize(q_vecs[0].reshape(1, -1))[0]
    scores = index.matrix @ q
    order = np.argsort(-scores)
    out: list[tuple[str, float]] = []
    for i in order:
        sim = float(scores[int(i)])
        if sim < min_similarity:
            break
        out.append((index.names[int(i)], sim))
        if len(out) >= limit:
            break
    return out


def _resolve_top_k(limit: int | None) -> int:
    if limit is not None:
        return max(1, int(limit))
    return _DEFAULT_TOP_K


def _embedding_rank_prep(
    db: Session | None,
    query: str,
    *,
    limit: int | None = None,
    min_similarity: float | None = None,
) -> tuple[str, float, int, tuple[str, str, str]] | None:
    """Embedding 召回前置守卫：空查询 / 闲聊 / 关闭 / 无凭证时返回 None。"""
    q = (query or "").strip()
    if not q:
        return None

    settings = get_settings()
    if not settings.agent_skill_rag_enabled:
        return None

    from app.services.agent_intent import is_chitchat_message

    if is_chitchat_message(q) or len(q) < 2:
        return None

    threshold = (
        settings.agent_skill_rag_min_similarity
        if min_similarity is None
        else float(min_similarity)
    )
    top_k = _resolve_top_k(limit)
    creds = _get_credentials(db)
    if creds is None:
        return None
    return q, threshold, top_k, creds


def rank_skills_by_embedding(
    db: Session | None,
    query: str,
    skills: list[SkillDefinition],
    *,
    limit: int | None = None,
    min_similarity: float | None = None,
) -> list[tuple[float, SkillDefinition]] | None:
    """语义召回 Skill。

    Returns:
        ``[(score, skill), ...]``，score = similarity * 100；
        Embedding 不可用或失败时返回 ``None``（调用方应回退关键词）。
    """
    if not skills:
        return None
    prep = _embedding_rank_prep(
        db, query, limit=limit, min_similarity=min_similarity
    )
    if prep is None:
        return None
    q, threshold, top_k, creds = prep

    index = _ensure_skill_index(db, skills)
    if index is None:
        return None

    ranked = _rank_names(index, q, creds=creds, limit=top_k, min_similarity=threshold)
    if ranked is None:
        return None

    by_name = {s.name: s for s in skills if (s.name or "").strip()}
    out: list[tuple[float, SkillDefinition]] = []
    for name, sim in ranked:
        skill = by_name.get(name)
        if skill is None:
            continue
        out.append((sim * 100.0, skill))
    return out


def rank_agents_by_embedding(
    db: Session | None,
    query: str,
    *,
    limit: int | None = None,
    min_similarity: float | None = None,
) -> list[tuple[float, RoutingEntry]] | None:
    """语义召回专精 Agent（agents.md）。失败返回 None，调用方回退关键词。"""
    prep = _embedding_rank_prep(
        db, query, limit=limit, min_similarity=min_similarity
    )
    if prep is None:
        return None
    q, threshold, top_k, creds = prep

    index, entries = _ensure_agent_index(db)
    if index is None or not entries:
        return None

    ranked = _rank_names(index, q, creds=creds, limit=top_k, min_similarity=threshold)
    if ranked is None:
        return None

    by_id = {e.id: e for e in entries}
    out: list[tuple[float, RoutingEntry]] = []
    for name, sim in ranked:
        entry = by_id.get(name)
        if entry is None:
            continue
        out.append((sim * 100.0, entry))
    return out
