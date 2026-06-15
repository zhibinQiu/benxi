"""引用片段展示：对齐 KnowFlow，优先 highlight（<em> 关键词），否则截取含问句关键词的短摘录。"""

from __future__ import annotations

import re


def _strip_html(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text or "")


def _normalize_highlight_snippet(text: str) -> str:
    raw = (text or "").strip()
    if not raw:
        return ""
    if re.search(r"</?em\b", raw, flags=re.I):
        return raw
    patterns = (
        (r"<mark\b[^>]*>(.*?)</mark>", r"<em>\1</em>"),
        (
            r"<font\b[^>]*\bclass=['\"]highlight['\"][^>]*>(.*?)</font>",
            r"<em>\1</em>",
        ),
        (r"\*\*(.+?)\*\*", r"<em>\1</em>"),
    )
    for pattern, repl in patterns:
        raw = re.sub(pattern, repl, raw, flags=re.I | re.S)
    return raw


def _query_terms(question: str | None, *, max_terms: int = 10) -> list[str]:
    q = (question or "").strip()
    if not q:
        return []
    terms: list[str] = []

    def _add(term: str) -> None:
        t = term.strip()
        if len(t) >= 2 and t not in terms:
            terms.append(t)

    for token in re.split(r"[\s,，。；;、？?！!]+", q):
        _add(token)
        if len(terms) >= max_terms:
            return terms[:max_terms]

    for seg in re.findall(r"[\u4e00-\u9fff]{2,}", q):
        if len(seg) <= 4:
            _add(seg)
        for i in range(len(seg) - 1):
            _add(seg[i : i + 2])
            if len(terms) >= max_terms:
                return terms[:max_terms]
        if len(terms) >= max_terms:
            break
    return terms[:max_terms]


def query_terms_for_highlight(question: str | None, *, max_terms: int = 10) -> list[str]:
    return _query_terms(question, max_terms=max_terms)


def _apply_term_highlights(plain: str, question: str | None, *, max_matches: int = 3) -> str:
    terms = _query_terms(question)
    if not terms or not plain:
        return plain
    excerpt = plain
    for term in sorted(terms, key=len, reverse=True):
        if len(term) < 2:
            continue
        excerpt = re.sub(
            re.escape(term),
            lambda m: f"<em>{m.group(0)}</em>",
            excerpt,
            flags=re.I,
            count=max_matches,
        )
    return excerpt


def _extract_excerpt(text: str, question: str | None, *, max_len: int = 360) -> str:
    plain = re.sub(r"\s+", " ", _strip_html(text)).strip()
    if not plain:
        return ""
    terms = _query_terms(question)
    window_len = min(max_len, len(plain))

    if len(plain) <= max_len and (not terms or len(plain) <= 120):
        return _apply_term_highlights(plain, question) if terms else plain

    if not terms:
        if len(plain) <= max_len:
            return plain
        return plain[: max_len - 1] + "…"

    best_pos = 0
    best_score = -1
    step = max(24, window_len // 5)
    scan_end = max(1, len(plain) - window_len // 2)
    for i in range(0, scan_end, step):
        window = plain[i : i + window_len]
        wl = window.lower()
        score = sum(1 for t in terms if t.lower() in wl)
        if score > best_score:
            best_score = score
            best_pos = i

    excerpt = plain[best_pos : best_pos + window_len].strip()
    excerpt = _apply_term_highlights(excerpt, question)

    prefix = "…" if best_pos > 0 else ""
    suffix = "…" if best_pos + window_len < len(plain) else ""
    return f"{prefix}{excerpt}{suffix}"


def format_citation_snippet(
    *,
    highlight: str | None = None,
    content: str | None = None,
    question: str | None = None,
    max_len: int = 480,
) -> str:
    """生成引用弹窗/列表展示的短片段（KnowFlow 风格 highlight 优先）。"""
    hl = (highlight or "").strip()
    body = (content or "").strip()
    plain_hl = _strip_html(hl)
    plain_body = _strip_html(body)

    if hl and plain_hl:
        has_em = bool(re.search(r"</?em\b", hl, flags=re.I))
        shorter = len(plain_hl) < len(plain_body) * 0.92 if plain_body else True
        same_as_body = bool(plain_body) and plain_hl == plain_body
        if has_em or (plain_hl != plain_body and shorter):
            return _normalize_highlight_snippet(hl)[:max_len]
        if same_as_body and len(plain_hl) > max_len:
            excerpt = _extract_excerpt(plain_body, question, max_len=max_len)
            return _normalize_highlight_snippet(excerpt)[:max_len]
        if same_as_body and question:
            return _normalize_highlight_snippet(
                _extract_excerpt(plain_body, question, max_len=max_len)
            )[:max_len]

    source = body or hl
    if not source:
        return ""
    excerpt = _extract_excerpt(source, question, max_len=max_len)
    out = _normalize_highlight_snippet(excerpt)[:max_len]
    if question and out and not re.search(r"</?(em|mark)\b", out, flags=re.I):
        plain = _strip_html(out)
        out = _apply_term_highlights(plain, question)[:max_len]
    return out
