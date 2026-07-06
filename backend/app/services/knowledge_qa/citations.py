"""Knowledge QA — 引用构建与过滤."""

from __future__ import annotations

import re
from typing import Any

from app.integrations.ragflow_client import RagflowClient
from app.services.knowledge_qa.constants import (
    CITATION_REF_RE,
    CITATION_REF_REPLACE_RE,
)
from app.services.knowledge_qa.text import strip_meta_footer


def _normalize_highlight_snippet(text: str) -> str:
    """将检索高亮统一为 <em>…</em>，供前端溯源展示。"""
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


def _citation_preview_available(h: dict) -> bool:
    """是否可展示页级引用截图（真实 image_id、KnowFlow bbox，或 PageIndex 页码）。"""
    if h.get("preview_available") is True:
        return True
    if h.get("preview_available") is False:
        return False
    if str(h.get("source") or "").strip() == "pageindex":
        did = str(h.get("document_id") or "").strip()
        if did:
            return True
    if RagflowClient.extract_chunk_image_id(h):
        return True
    anchor = h.get("anchor_json") or {}
    bbox = anchor.get("bbox")
    if isinstance(bbox, list) and len(bbox) >= 4:
        cid = str(h.get("chunk_id") or "").strip()
        ds_id = str(h.get("dataset_id") or "").strip()
        rid = str(h.get("ragflow_document_id") or "").strip()
        return bool(cid and ds_id and rid)
    return False


def _citation_image_id(h: dict) -> str | None:
    return (
        RagflowClient.extract_chunk_image_id(h)
        or RagflowClient.synthesize_chunk_image_id(h)
        or None
    )


def _dedupe_indexes_by_document(
    nums: list[int],
    by_index: dict[int, dict],
) -> dict[int, int]:
    """同一句内：同一文档只保留 score 最高的引用编号。"""
    best_by_doc: dict[str, int] = {}
    best_score: dict[str, float] = {}
    for num in nums:
        cite = by_index.get(num)
        if not cite:
            continue
        did = str(cite.get("document_id") or f"__idx_{num}")
        score = float(cite.get("score") or 0)
        if did not in best_by_doc or score > best_score[did]:
            best_by_doc[did] = num
            best_score[did] = score
    remap: dict[int, int] = {}
    for num in nums:
        cite = by_index.get(num)
        if not cite:
            remap[num] = num
            continue
        did = str(cite.get("document_id") or f"__idx_{num}")
        remap[num] = best_by_doc.get(did, num)
    return remap


def _sentence_chunks(text: str) -> list[str]:
    parts = re.split(r"(?<=[。！？\n；])", text)
    return parts if parts else [text]


def _collapse_sentence_citations(sentence: str, by_index: dict[int, dict]) -> str:
    nums = [int(n) for n in CITATION_REF_RE.findall(sentence)]
    if not nums:
        return sentence
    remap = _dedupe_indexes_by_document(nums, by_index)
    seen: set[int] = set()

    def _replace_one(match: re.Match[str]) -> str:
        num = int(match.group(1))
        primary = remap.get(num, num)
        if primary in seen:
            return ""
        seen.add(primary)
        return f"[{primary}]"

    collapsed = CITATION_REF_RE.sub(_replace_one, sentence)
    return re.sub(r"  +", " ", collapsed)


def collapse_answer_citation_refs(
    answer: str,
    citations: list[dict],
) -> tuple[str, list[dict]]:
    """同句内同一文档只保留最高 score 的引用；跨文档综合结论保留各文档一处。"""
    if not answer or not citations:
        return answer, citations

    by_index = {
        int(c["index"]): c for c in citations if c.get("index") is not None
    }
    if not by_index:
        return answer, citations

    normalized = "".join(
        _collapse_sentence_citations(chunk, by_index)
        if CITATION_REF_RE.search(chunk)
        else chunk
        for chunk in _sentence_chunks(answer)
    )
    used = {int(n) for n in CITATION_REF_RE.findall(normalized)}
    kept = [c for c in citations if int(c.get("index") or 0) in used]
    kept.sort(key=lambda c: int(c.get("index") or 0))
    return normalized, kept


def filter_citations_for_display(
    citations: list[dict],
    answer: str,
) -> list[dict]:
    """仅展示回答正文中实际标注 [n] 的引用条目。"""
    if not citations:
        return []

    indexes = {
        int(n)
        for n in CITATION_REF_RE.findall(answer or "")
        if str(n).isdigit() and int(n) > 0
    }
    if not indexes:
        return []

    pool = [c for c in citations if int(c.get("index") or 0) in indexes]
    pool.sort(key=lambda c: int(c.get("index") or 0))
    return pool


def finalize_citations_for_display(
    answer: str,
    citations: list[dict],
) -> tuple[str, list[dict]]:
    """仅保留正文 [n] 实际引用的条目；未标注则不展示引用区。"""
    return finalize_citations_preserving_index(answer, citations)


def finalize_qa_answer_and_citations(
    answer: str,
    citations: list[dict],
) -> tuple[str, list[dict]]:
    """过滤未使用的引用，并将正文与引用编号重排为连续的 1,2,3…"""
    answer = strip_meta_footer(answer)
    return finalize_citations_for_display(answer, citations)


def strip_answer_source_narrative(text: str) -> str:
    """移除回答中不应出现的来源说明段落/章节。"""
    lines = (text or "").splitlines()
    out: list[str] = []
    for line in lines:
        stripped = line.strip()
        if re.match(r"^#+\s*", stripped):
            heading = re.sub(r"^#+\s*", "", stripped)
            if re.search(
                r"(参考来源|参考文献|资料来源|引用来源|参考文档|联网来源|来源说明|资料说明)",
                heading,
            ):
                break
        if re.search(
            r"(以上内容|本报告|下文)?(主要)?(参考|引用|依据)(了|自)?",
            stripped,
        ) and re.search(r"(文档|资料|检索|知识库|网页|联网|来源)", stripped):
            continue
        if re.search(r"^(\*\*)?(参考来源|数据来源|引用说明)", stripped):
            continue
        out.append(line)
    return "\n".join(out).strip()


def _renumber_citations_sequential(
    answer: str,
    citations: list[dict],
) -> tuple[str, list[dict]]:
    """将正文与引用列表的编号统一重排为连续的 1,2,3…"""
    if not citations:
        return answer, []
    old_indexes = sorted(
        {int(c.get("index") or 0) for c in citations if int(c.get("index") or 0) > 0}
    )
    if not old_indexes:
        return answer, []
    remap = {old: new for new, old in enumerate(old_indexes, start=1)}
    if remap == {i: i for i in old_indexes}:
        return answer, citations

    def _replace_ref(match: re.Match[str]) -> str:
        old = int(match.group(2))
        new = remap.get(old)
        if new is None:
            return match.group(0)
        return f"{match.group(1)}{new}{match.group(3)}"

    normalized = CITATION_REF_REPLACE_RE.sub(_replace_ref, answer)
    renumbered: list[dict] = []
    for c in citations:
        old_idx = int(c.get("index") or 0)
        if old_idx not in remap:
            continue
        item = dict(c)
        item["index"] = remap[old_idx]
        renumbered.append(item)
    renumbered.sort(key=lambda c: int(c.get("index") or 0))
    return normalized, renumbered


def finalize_citations_preserving_index(
    answer: str,
    citations: list[dict],
) -> tuple[str, list[dict]]:
    """过滤未使用引用，并将正文与引用编号重排为连续的 1,2,3…"""
    answer = strip_answer_source_narrative(answer)
    if not answer or not citations:
        return answer, []
    indexes = {
        int(n)
        for n in CITATION_REF_RE.findall(answer)
        if str(n).isdigit() and int(n) > 0
    }
    if not indexes:
        return answer, []
    kept = [c for c in citations if int(c.get("index") or 0) in indexes]
    kept.sort(key=lambda c: int(c.get("index") or 0))
    return _renumber_citations_sequential(answer, kept)


def _extract_qa_context_body(hit: dict) -> str:
    for key in ("highlight", "snippet", "content"):
        raw = (hit.get(key) or "").strip()
        if not raw:
            continue
        if key == "highlight":
            return _normalize_highlight_snippet(raw)
        return raw
    return ""


def build_aligned_qa_context_and_citations(
    hits: list[dict],
    doc_titles: dict[str, str],
    *,
    question: str | None = None,
    doc_meta: dict[str, dict[str, Any]] | None = None,
) -> tuple[str, list[dict]]:
    """构建与 citations 索引严格对齐的 LLM 上下文与引用列表。"""
    included: list[dict] = []
    blocks: list[str] = []
    for h in hits:
        body = _extract_qa_context_body(h)
        if not body:
            continue
        idx = len(included) + 1
        blocks.append(f"[{idx}]\n{body}")
        included.append(h)
    context = "\n\n".join(blocks)
    citations = build_citations(
        included, doc_titles, question=question, doc_meta=doc_meta
    )
    return context, citations


def build_citations(
    hits: list[dict],
    doc_titles: dict[str, str],
    *,
    question: str | None = None,
    doc_meta: dict[str, dict[str, Any]] | None = None,
) -> list[dict]:
    from app.integrations.citation_snippet import (
        format_citation_snippet,
        query_terms_for_highlight,
    )

    citations: list[dict] = []
    meta_by_doc = doc_meta or {}
    for i, h in enumerate(hits, start=1):
        did = str(h.get("document_id") or "")
        doc_info = meta_by_doc.get(did) or {}
        pre_snippet = (h.get("snippet") or "").strip()
        snippet = format_citation_snippet(
            highlight=h.get("highlight"),
            content=h.get("content") or pre_snippet,
            question=question,
        )
        if not snippet.strip():
            snippet = pre_snippet or _normalize_highlight_snippet(
                (h.get("highlight") or "").strip()
            )
        citations.append(
            {
                "index": i,
                "document_id": did or None,
                "title": doc_titles.get(did, did or "文档"),
                "snippet": snippet[:2000],
                "score": h.get("score"),
                "anchor_json": h.get("anchor_json"),
                "chunk_id": h.get("chunk_id"),
                "dataset_id": h.get("dataset_id"),
                "image_id": _citation_image_id(h),
                "preview_available": _citation_preview_available(h),
                "highlight_terms": query_terms_for_highlight(question),
                "ragflow_document_id": h.get("ragflow_document_id"),
                "source": h.get("source") or "knowflow",
                "file_name": doc_info.get("file_name"),
                "file_format": doc_info.get("file_format"),
            }
        )
    return citations


