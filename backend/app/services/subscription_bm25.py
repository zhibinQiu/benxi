"""资讯条目 BM25 检索：jieba 分词 + BM25Okapi 相关度打分。"""

from __future__ import annotations

import re
from html import unescape

import jieba
from rank_bm25 import BM25Okapi

_HTML_TAG_RE = re.compile(r"<[^>]+>", re.I)
_WS_RE = re.compile(r"\s+")

# ILIKE 命中但 BM25=0 时的保底分，保证专有连续串不被丢弃且排在真相关之后
ILIKE_FLOOR_SCORE = 1e-6

_TITLE_WEIGHT = 3
_SUMMARY_WEIGHT = 2
_CONTENT_MAX_CHARS = 4000


def strip_html(text: str) -> str:
    raw = unescape(text or "")
    raw = _HTML_TAG_RE.sub(" ", raw)
    return _WS_RE.sub(" ", raw).strip()


def tokenize(text: str) -> list[str]:
    """小写、去 HTML、jieba 分词；过滤空白与无意义单字符。"""
    cleaned = strip_html(text).casefold()
    if not cleaned:
        return []
    tokens: list[str] = []
    for tok in jieba.lcut(cleaned):
        t = (tok or "").strip()
        if not t:
            continue
        if len(t) == 1 and not t.isalnum():
            continue
        # 单汉字常为噪声；保留英数单字符（如 "a"/"1"）与长度>=2 的词
        if len(t) == 1 and "\u4e00" <= t <= "\u9fff":
            continue
        tokens.append(t)
    return tokens


def _index_text(item: dict) -> str:
    title = str(item.get("title") or "").strip()
    summary = str(item.get("summary") or "").strip()
    content = strip_html(str(item.get("content_html") or ""))[:_CONTENT_MAX_CHARS]
    parts = (
        [title] * _TITLE_WEIGHT
        + [summary] * _SUMMARY_WEIGHT
        + ([content] if content else [])
    )
    return " ".join(p for p in parts if p)


def substring_match(keyword: str, item: dict) -> bool:
    """与 SQL ILIKE '%kw%' 同语义的大小写不敏感子串匹配。"""
    needle = (keyword or "").strip().casefold()
    if not needle:
        return False
    haystacks = (
        str(item.get("title") or ""),
        str(item.get("summary") or ""),
        str(item.get("content_html") or ""),
    )
    return any(needle in h.casefold() for h in haystacks)


def rank_subscription_items(
    keyword: str,
    items: list[dict],
    *,
    ilike_refs: set[str] | None = None,
) -> list[dict]:
    """
    对语料建 BM25，返回混合召回结果（BM25>0 ∪ ILIKE），按 `_bm25_score` 降序。
    调用方负责在返回前剔除 `_bm25_score` / `content_html` 等内部字段。
    """
    text = (keyword or "").strip()
    if not text or not items:
        return []

    query_tokens = tokenize(text)
    corpus_tokens = [tokenize(_index_text(it)) for it in items]
    scores = [0.0] * len(items)
    if query_tokens and any(corpus_tokens):
        # BM25Okapi 要求至少一篇非空文档；空语料时跳过打分
        non_empty = [c if c else ["__empty__"] for c in corpus_tokens]
        bm25 = BM25Okapi(non_empty)
        raw = bm25.get_scores(query_tokens)
        scores = [float(s) for s in raw]

    ilike = ilike_refs or set()
    ranked: list[dict] = []
    for item, score in zip(items, scores):
        ref = str(item.get("ref") or "")
        hit_ilike = ref in ilike
        if score > 0:
            out = dict(item)
            out["_bm25_score"] = score
            ranked.append(out)
        elif hit_ilike:
            out = dict(item)
            out["_bm25_score"] = ILIKE_FLOOR_SCORE
            ranked.append(out)

    ranked.sort(key=lambda x: float(x.get("_bm25_score") or 0), reverse=True)
    return ranked
