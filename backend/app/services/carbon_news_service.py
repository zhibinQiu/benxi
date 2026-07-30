"""碳新闻服务：发改委实时爬取 + 基于当次条目的一问一答。"""

from __future__ import annotations

import logging

from app.integrations.deepseek_client import chat_completion_message_async, is_configured
from app.schemas.carbon_news import (
    CarbonNewsAskOut,
    CarbonNewsCrawlOut,
    CarbonNewsItem,
    CarbonNewsSourceOut,
)
from app.services.ndrc_policy_scraper import DEFAULT_KEYWORD, NdrcPolicySearcher

logger = logging.getLogger(__name__)

_MAX_ASK_ITEMS = 15
_MAX_BODY_CHARS_PER_ITEM = 4000
_MAX_CONTEXT_CHARS = 28000
_DEFAULT_CRAWL_LIMIT = 100
_LIST_PAGE_SIZE = 20  # 上游搜索每页条数


async def crawl_carbon_news(
    *,
    keyword: str = "",
    limit: int = _DEFAULT_CRAWL_LIMIT,
) -> CarbonNewsCrawlOut:
    kw = (keyword or "").strip() or DEFAULT_KEYWORD
    cap = max(1, min(int(limit or _DEFAULT_CRAWL_LIMIT), _DEFAULT_CRAWL_LIMIT))
    max_pages = (cap + _LIST_PAGE_SIZE - 1) // _LIST_PAGE_SIZE
    searcher = NdrcPolicySearcher(keyword=kw, delay=0.2)
    try:
        rows = await searcher.scrape(
            max_pages=max_pages,
            page_size=_LIST_PAGE_SIZE,
            with_detail=True,
        )
    finally:
        await searcher.aclose()

    items = [
        CarbonNewsItem(
            title=str(r.get("title") or "").strip(),
            url=str(r.get("url") or "").strip(),
            doc_type=str(r.get("doc_type") or "").strip(),
            published_at=str(r.get("published_at") or "").strip(),
            source=str(r.get("source") or "").strip(),
            body=str(r.get("body") or "").strip(),
        )
        for r in rows
        if (r.get("title") or r.get("body") or r.get("url"))
    ][:cap]
    return CarbonNewsCrawlOut(
        keyword=kw,
        total_hits=int(searcher.total_hits or len(items)),
        count=len(items),
        items=items,
    )


def _build_evidence(items: list[CarbonNewsItem]) -> tuple[str, list[CarbonNewsSourceOut]]:
    sources: list[CarbonNewsSourceOut] = []
    parts: list[str] = []
    used = 0
    for i, item in enumerate(items[:_MAX_ASK_ITEMS], start=1):
        body = (item.body or "").strip()
        if len(body) > _MAX_BODY_CHARS_PER_ITEM:
            body = body[:_MAX_BODY_CHARS_PER_ITEM] + "…"
        block = (
            f"[{i}] 标题：{item.title or '（无标题）'}\n"
            f"类型：{item.doc_type or '—'}\n"
            f"发布时间：{item.published_at or '—'}\n"
            f"来源：{item.source or '—'}\n"
            f"URL：{item.url or '—'}\n"
            f"正文：\n{body or '（无正文）'}"
        )
        if used + len(block) > _MAX_CONTEXT_CHARS and parts:
            break
        parts.append(block)
        used += len(block)
        sources.append(
            CarbonNewsSourceOut(
                index=i,
                title=item.title or "（无标题）",
                url=item.url or "",
                doc_type=item.doc_type or "",
                published_at=item.published_at or "",
                source=item.source or "",
            )
        )
    return "\n\n---\n\n".join(parts), sources


async def ask_carbon_news(
    *,
    question: str,
    items: list[CarbonNewsItem],
) -> CarbonNewsAskOut:
    q = (question or "").strip()
    if not q:
        return CarbonNewsAskOut(answer_md="问题不能为空。", sources=[])
    if not items:
        return CarbonNewsAskOut(
            answer_md="当前没有可引用的爬取内容，请先输入关键词完成爬取后再提问。",
            sources=[],
        )

    evidence, sources = _build_evidence(items)
    if not is_configured():
        return CarbonNewsAskOut(
            answer_md=(
                "模型未配置，无法生成总结。以下为可引用数据来源：\n\n"
                + "\n".join(
                    f"- [{s.index}] {s.title}" + (f" — {s.url}" if s.url else "")
                    for s in sources
                )
            ),
            sources=sources,
        )

    system = (
        "You are a carbon policy & news analyst for the Benxi platform. "
        "Answer ONLY using the provided crawled evidence. "
        "Write the final answer in the same language as the user question. "
        "Use clear Markdown. Cite sources inline like [1], [2] when claims come from evidence. "
        "At the end, add a short '数据来源' section listing used citations with title and URL. "
        "If evidence is insufficient, say so explicitly; do not invent facts."
    )
    user = (
        f"用户问题：\n{q}\n\n"
        f"以下为当次爬取的政策/新闻证据（仅可据此作答）：\n\n{evidence}"
    )
    choice = await chat_completion_message_async(
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        temperature=0.2,
        timeout=120.0,
    )
    answer = ""
    if choice:
        msg = choice.get("message") or {}
        answer = str(msg.get("content") or "").strip()
    if not answer:
        answer = "模型调用失败，未能生成总结。请稍后重试。"

    # 若模型未列出来源，仍返回结构化 sources 供前端展示
    if "数据来源" not in answer and sources:
        lines = "\n".join(
            f"{s.index}. {s.title}" + (f" — {s.url}" if s.url else "")
            for s in sources
        )
        answer = f"{answer}\n\n## 数据来源\n\n{lines}"

    return CarbonNewsAskOut(answer_md=answer, sources=sources)
