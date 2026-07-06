"""资讯管理：收录后 AI 摘要并写入条目 summary / 正文顶部。"""

from __future__ import annotations

import asyncio
import logging
import re
from html import escape

from sqlalchemy.orm import Session

from app.integrations.deepseek_client import is_configured, summarize_article_content
from app.integrations.html_document_export import plain_text_char_count
from app.integrations.html_markdown import html_to_markdown
from app.models.feed_subscription import FeedEntry
from app.models.wechat_mp import WechatMpArticle

logger = logging.getLogger(__name__)

AI_SUMMARY_CLASS = "subscription-ai-summary"
_AI_SUMMARY_BLOCK_RE = re.compile(
    rf'<div[^>]*class="[^"]*{AI_SUMMARY_CLASS}[^"]*"[^>]*data-ai-summary="1"[^>]*>[\s\S]*?</div>\s*'
    rf'(?:<hr[^>]*class="subscription-ai-summary-divider"[^>]*/?>\s*)?',
    re.IGNORECASE,
)

MIN_CHARS_FOR_AI = 80


def plain_text_for_summary(
    *,
    title: str = "",
    html_body: str = "",
    fallback_summary: str = "",
) -> str:
    """从标题、HTML 与已有摘要拼出可供模型阅读的纯文本。"""
    parts: list[str] = []
    title_text = (title or "").strip()
    if title_text:
        parts.append(title_text)
    md = html_to_markdown(_strip_ai_summary_block(html_body))
    if md.strip():
        parts.append(md.strip())
    meta = (fallback_summary or "").strip()
    if meta:
        plain_meta = re.sub(r"\s+", " ", meta)
        combined = "\n".join(parts)
        if plain_meta not in re.sub(r"\s+", " ", combined):
            parts.append(meta)
    return "\n\n".join(parts).strip()


def content_html_has_ai_summary(html: str) -> bool:
    text = html or ""
    return AI_SUMMARY_CLASS in text or 'data-ai-summary="1"' in text


def _strip_ai_summary_block(html: str) -> str:
    if not html:
        return ""
    return _AI_SUMMARY_BLOCK_RE.sub("", html, count=1).strip()


def build_summary_html_block(summary: str) -> str:
    text = (summary or "").strip()
    if not text:
        return ""
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    if not paragraphs:
        paragraphs = [text]
    inner = "".join(f"<p>{escape(p)}</p>" for p in paragraphs)
    return (
        f'<div class="{AI_SUMMARY_CLASS}" data-ai-summary="1">'
        f'<p><strong>摘要</strong></p>{inner}</div>'
        '<hr class="subscription-ai-summary-divider" />'
    )


def prepend_ai_summary_to_content_html(content_html: str, summary: str) -> str:
    block = build_summary_html_block(summary)
    if not block:
        return (content_html or "").strip()
    body = _strip_ai_summary_block(content_html) if content_html_has_ai_summary(content_html) else (content_html or "").strip()
    if not body:
        return block
    return f"{block}\n{body}"


def enrich_subscription_item_ai_summary(db: Session, ref: str) -> str | None:
    """
    为已收录条目生成 AI 摘要，写入 summary 字段并插入正文 HTML 顶部。
    未配置模型或正文过短时返回 None，不抛错（由调用方记录日志）。
    """
    if not is_configured():
        return None

    from app.services.subscription_service import parse_ref

    origin, item_id = parse_ref(ref)
    if origin == "wechat":
        article = db.get(WechatMpArticle, item_id)
        if not article:
            return None
        title = article.title
        html_body = article.content_html or ""
        meta_summary = article.summary or ""
    else:
        entry = db.get(FeedEntry, item_id)
        if not entry:
            return None
        title = entry.title
        html_body = entry.content_html or ""
        meta_summary = entry.summary or ""

    plain = plain_text_for_summary(
        title=title,
        html_body=html_body,
        fallback_summary=meta_summary,
    )
    if plain_text_char_count(plain) < MIN_CHARS_FOR_AI and not (meta_summary or "").strip():
        return None

    try:
        result = asyncio.run(
            summarize_article_content(title=title or "未命名", text=plain or meta_summary)
        )
    except Exception:
        logger.exception("subscription AI summary failed ref=%s", ref)
        return None

    ai_summary = (result.get("summary") or "").strip()
    if not ai_summary:
        return None

    new_html = prepend_ai_summary_to_content_html(html_body, ai_summary)
    if origin == "wechat":
        article.summary = ai_summary
        article.content_html = new_html
    else:
        entry.summary = ai_summary
        entry.content_html = new_html
    db.flush()
    return ai_summary
