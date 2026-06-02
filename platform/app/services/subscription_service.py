"""统一资讯订阅：手动粘贴链接收录，合并展示公众号与网页条目。"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.integrations.html_markdown import html_to_markdown

from app.core.document_scope import content_subscription_import_scope
from app.core.exceptions import bad_request
from app.integrations.web_article_fetcher import (
    WebArticleFetchError,
    fetch_web_article,
    is_wechat_article_url,
)
from app.models.feed_subscription import (
    SOURCE_KIND_LINK,
    FeedEntry,
    FeedEntryImport,
    FeedSource,
    FeedSourceSubscription,
)
from app.models.org import User
from app.models.wechat_mp import (
    WechatMpArticle,
    WechatMpArticleImport,
    WechatMpSourceSubscription,
)
from app.services import feed_subscription_service as feed_svc
from app.services import subscription_summary_service as summary_svc
from app.services import wechat_mp_service as wechat_svc

REF_WECHAT = "w"
REF_FEED = "f"

logger = logging.getLogger(__name__)


def make_ref(prefix: str, item_id: uuid.UUID) -> str:
    """prefix 为 ``w`` / ``f``（见 REF_WECHAT、REF_FEED）。"""
    return f"{prefix}:{item_id}"


def parse_ref(ref: str) -> tuple[str, uuid.UUID]:
    text = (ref or "").strip()
    if ":" not in text:
        raise bad_request("无效条目引用")
    prefix, raw_id = text.split(":", 1)
    try:
        item_id = uuid.UUID(raw_id)
    except ValueError as e:
        raise bad_request("无效条目 ID") from e
    if prefix == REF_WECHAT:
        return "wechat", item_id
    if prefix == REF_FEED:
        return "feed", item_id
    raise bad_request("无效条目类型")


def _normalize_item(
    *,
    ref: str,
    item_id: uuid.UUID,
    title: str,
    summary: str,
    link: str,
    publish_at: datetime | None,
    fetched_at: datetime | None,
    imported: bool,
    document_id: uuid.UUID | None,
    cover_url: str = "",
) -> dict:
    url = (link or "").strip()
    return {
        "ref": ref,
        "id": item_id,
        "title": title,
        "summary": summary,
        "link": url,
        "cover_url": cover_url,
        "is_wechat": is_wechat_article_url(url),
        "publish_at": publish_at,
        "created_at": fetched_at,
        "imported": imported,
        "document_id": document_id,
    }


def _keyword_clause(keyword: str | None, *columns) -> list:
    text = (keyword or "").strip()
    if not text:
        return []
    pattern = f"%{text}%"
    return [or_(*(col.ilike(pattern) for col in columns))]


def _created_range_clause(
    created_from: datetime | None,
    created_to: datetime | None,
    column,
) -> list:
    clauses: list = []
    if created_from is not None:
        clauses.append(column >= created_from)
    if created_to is not None:
        clauses.append(column <= created_to)
    return clauses


def ingest_url(db: Session, user: User, url: str) -> dict:
    """粘贴文章链接收录（微信走公众号解析，其它走通用网页解析）。"""
    text = (url or "").strip()
    if not text:
        raise bad_request("请填写文章链接")

    if is_wechat_article_url(text):
        detail = wechat_svc.ingest_url(db, user, text)
        ref = make_ref(REF_WECHAT, detail["id"])
        _try_enrich_ai_summary(db, ref)
        return get_item_detail(db, user, ref)

    try:
        parsed = fetch_web_article(text)
    except WebArticleFetchError as e:
        raise bad_request(str(e)) from e

    from urllib.parse import urlparse

    netloc = urlparse(parsed.link).netloc or "web"
    feed_key = f"manual://{netloc}"
    source = db.scalar(select(FeedSource).where(FeedSource.feed_url == feed_key))
    if not source:
        source = FeedSource(
            feed_url=feed_key,
            site_url=parsed.link,
            name=netloc[:256],
            kind=SOURCE_KIND_LINK,
            category="手动收录",
        )
        db.add(source)
        db.flush()
    sub = db.scalar(
        select(FeedSourceSubscription).where(
            FeedSourceSubscription.user_id == user.id,
            FeedSourceSubscription.source_id == source.id,
        )
    )
    if not sub:
        db.add(FeedSourceSubscription(user_id=user.id, source_id=source.id))
        db.flush()

    existing = db.scalar(
        select(FeedEntry).where(
            FeedEntry.source_id == source.id,
            FeedEntry.entry_key == parsed.entry_key,
        )
    )
    if existing:
        existing.title = parsed.title
        existing.summary = parsed.summary or existing.summary
        existing.link = parsed.link or existing.link
        if parsed.content_html:
            existing.content_html = parsed.content_html
        if parsed.publish_at:
            existing.publish_at = parsed.publish_at
        entry = existing
    else:
        entry = FeedEntry(
            source_id=source.id,
            title=parsed.title,
            summary=parsed.summary,
            link=parsed.link,
            content_html=parsed.content_html,
            entry_key=parsed.entry_key,
            publish_at=parsed.publish_at,
        )
        db.add(entry)
        db.flush()

    ref = make_ref(REF_FEED, entry.id)
    _try_enrich_ai_summary(db, ref)
    return get_item_detail(db, user, ref)


def _try_enrich_ai_summary(db: Session, ref: str) -> None:
    try:
        summary_svc.enrich_subscription_item_ai_summary(db, ref)
    except Exception:
        logger.exception("subscription AI summary skipped ref=%s", ref)


def list_items(
    db: Session,
    user: User,
    *,
    page: int = 1,
    page_size: int = 20,
    keyword: str | None = None,
    created_from: datetime | None = None,
    created_to: datetime | None = None,
) -> tuple[list[dict], int]:
    """合并当前用户已收录条目（公众号 + 网页），支持标题/正文搜索与收录时间筛选。"""
    merged: list[dict] = []

    wechat_ids = list(
        db.scalars(
            select(WechatMpSourceSubscription.source_id).where(
                WechatMpSourceSubscription.user_id == user.id
            )
        ).all()
    )
    if wechat_ids:
        q = select(WechatMpArticle).where(WechatMpArticle.source_id.in_(wechat_ids))
        for clause in _keyword_clause(
            keyword,
            WechatMpArticle.title,
            WechatMpArticle.summary,
            WechatMpArticle.content_html,
        ):
            q = q.where(clause)
        for clause in _created_range_clause(
            created_from, created_to, WechatMpArticle.fetched_at
        ):
            q = q.where(clause)
        for article in db.scalars(q).all():
            imp = db.scalar(
                select(WechatMpArticleImport).where(
                    WechatMpArticleImport.user_id == user.id,
                    WechatMpArticleImport.article_id == article.id,
                )
            )
            merged.append(
                _normalize_item(
                    ref=make_ref(REF_WECHAT, article.id),
                    item_id=article.id,
                    title=article.title,
                    summary=article.summary or "",
                    link=article.original_url,
                    publish_at=article.publish_at,
                    fetched_at=article.fetched_at,
                    imported=imp is not None,
                    document_id=imp.document_id if imp else None,
                    cover_url=article.cover_url or "",
                )
            )

    feed_rows = feed_svc.list_user_sources(db, user, kind=None)
    feed_source_ids = [r["id"] for r in feed_rows]
    if feed_source_ids:
        q = select(FeedEntry).where(FeedEntry.source_id.in_(feed_source_ids))
        for clause in _keyword_clause(
            keyword,
            FeedEntry.title,
            FeedEntry.summary,
            FeedEntry.content_html,
        ):
            q = q.where(clause)
        for clause in _created_range_clause(
            created_from, created_to, FeedEntry.fetched_at
        ):
            q = q.where(clause)
        for entry in db.scalars(q).all():
            imp = db.scalar(
                select(FeedEntryImport).where(
                    FeedEntryImport.user_id == user.id,
                    FeedEntryImport.entry_id == entry.id,
                )
            )
            merged.append(
                _normalize_item(
                    ref=make_ref(REF_FEED, entry.id),
                    item_id=entry.id,
                    title=entry.title,
                    summary=entry.summary or "",
                    link=entry.link,
                    publish_at=entry.publish_at,
                    fetched_at=entry.fetched_at,
                    imported=imp is not None,
                    document_id=imp.document_id if imp else None,
                )
            )

    def _ts(item: dict) -> float:
        t = item.get("created_at") or item.get("publish_at")
        if t is None:
            return 0.0
        try:
            return t.timestamp()
        except Exception:
            return 0.0

    merged.sort(key=_ts, reverse=True)
    total = len(merged)
    start = (page - 1) * page_size
    return merged[start : start + page_size], total


def get_item_detail(db: Session, user: User, ref: str) -> dict:
    origin, item_id = parse_ref(ref)
    if origin == "wechat":
        data = wechat_svc.get_article_detail(db, user, item_id)
        content_html = data.get("content_html") or ""
        return {
            **_normalize_item(
                ref=ref,
                item_id=data["id"],
                title=data["title"],
                summary=data.get("summary") or "",
                link=data["original_url"],
                publish_at=data.get("publish_at"),
                fetched_at=data.get("fetched_at"),
                imported=data.get("imported", False),
                document_id=data.get("document_id"),
                cover_url=data.get("cover_url") or "",
            ),
            "content_html": content_html,
            "content_markdown": html_to_markdown(content_html),
            "author": data.get("author") or "",
        }

    data = feed_svc.get_entry_detail(db, user, item_id)
    content_html = data.get("content_html") or ""
    return {
        **_normalize_item(
            ref=ref,
            item_id=data["id"],
            title=data["title"],
            summary=data.get("summary") or "",
            link=data["link"],
            publish_at=data.get("publish_at"),
            fetched_at=data.get("fetched_at"),
            imported=data.get("imported", False),
            document_id=data.get("document_id"),
        ),
        "content_html": content_html,
        "content_markdown": html_to_markdown(content_html),
        "author": "",
    }


def import_item_to_document(
    db: Session,
    user: User,
    ref: str,
    *,
    sync_knowflow: bool = True,
) -> dict:
    origin, item_id = parse_ref(ref)
    scope = content_subscription_import_scope()
    if origin == "wechat":
        return wechat_svc.import_article_to_document(
            db,
            user,
            item_id,
            scope=scope,
            dept_id=None,
            sync_knowflow=sync_knowflow,
        )
    return feed_svc.import_entry_to_document(
        db,
        user,
        item_id,
        scope=scope,
        dept_id=None,
        sync_knowflow=sync_knowflow,
    )


def delete_item(db: Session, user: User, ref: str) -> dict:
    """从资讯订阅中删除一条内容（已入文档库的文档保留）。"""
    origin, item_id = parse_ref(ref)
    if origin == "wechat":
        wechat_svc.delete_article(db, user, item_id)
    else:
        feed_svc.delete_entry(db, user, item_id)
    return {"deleted": True}

