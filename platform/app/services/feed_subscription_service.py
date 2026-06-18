"""RSS/网站资讯订阅服务。"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.document_scope import content_subscription_import_scope
from app.core.exceptions import bad_request, not_found
from app.integrations.feed_fetcher import (
    CARBON_FEED_PRESETS,
    FeedFetchError,
    fetch_feed,
    resolve_feed_url,
)
from app.models.feed_subscription import (
    SOURCE_KIND_RSS,
    SOURCE_KIND_WEBSITE,
    FeedEntry,
    FeedEntryImport,
    FeedSource,
    FeedSourceSubscription,
)
from app.models.org import User
from app.services.document_service import create_document, create_initial_uploaded_version

logger = logging.getLogger(__name__)


def list_presets() -> list[dict[str, str]]:
    return list(CARBON_FEED_PRESETS)


def _entry_out(entry: FeedEntry, source: FeedSource, **extra) -> dict:
    return {
        "id": entry.id,
        "source_id": source.id,
        "source_name": source.name,
        "source_kind": source.kind,
        "category": source.category,
        "title": entry.title,
        "summary": entry.summary,
        "link": entry.link,
        "publish_at": entry.publish_at,
        "fetched_at": entry.fetched_at,
        **extra,
    }


def _get_or_create_source(
    db: Session,
    *,
    name: str,
    feed_url: str,
    kind: str,
    category: str = "",
    site_url: str = "",
) -> FeedSource:
    source = db.scalar(select(FeedSource).where(FeedSource.feed_url == feed_url))
    display = (name or "").strip()[:256]
    if source:
        if display:
            source.name = display
        if category:
            source.category = category
        if site_url:
            source.site_url = site_url
        return source
    source = FeedSource(
        feed_url=feed_url,
        site_url=site_url or feed_url,
        name=display or feed_url,
        kind=kind if kind in (SOURCE_KIND_RSS, SOURCE_KIND_WEBSITE) else SOURCE_KIND_RSS,
        category=(category or "")[:64],
    )
    db.add(source)
    db.flush()
    return source


def _upsert_entries(
    db: Session, source: FeedSource, entries: list
) -> int:
    from app.integrations.feed_fetcher import ParsedFeedEntry

    added = 0
    for item in entries:
        if not isinstance(item, ParsedFeedEntry):
            continue
        existing = db.scalar(
            select(FeedEntry).where(
                FeedEntry.source_id == source.id,
                FeedEntry.entry_key == item.entry_key,
            )
        )
        if existing:
            existing.title = item.title
            existing.summary = item.summary or existing.summary
            existing.link = item.link or existing.link
            if item.content_html:
                existing.content_html = item.content_html
            if item.publish_at:
                existing.publish_at = item.publish_at
            continue
        db.add(
            FeedEntry(
                source_id=source.id,
                title=item.title,
                summary=item.summary,
                link=item.link,
                content_html=item.content_html,
                entry_key=item.entry_key,
                publish_at=item.publish_at,
            )
        )
        added += 1
    db.flush()
    return added


def list_user_sources(db: Session, user: User, *, kind: str | None = None) -> list[dict]:
    q = (
        select(FeedSource, FeedSourceSubscription.created_at, func.count(FeedEntry.id))
        .join(
            FeedSourceSubscription,
            FeedSourceSubscription.source_id == FeedSource.id,
        )
        .outerjoin(FeedEntry, FeedEntry.source_id == FeedSource.id)
        .where(FeedSourceSubscription.user_id == user.id)
    )
    if kind in (SOURCE_KIND_RSS, SOURCE_KIND_WEBSITE):
        q = q.where(FeedSource.kind == kind)
    rows = db.execute(
        q.group_by(FeedSource.id, FeedSourceSubscription.created_at).order_by(
            FeedSourceSubscription.created_at.desc()
        )
    ).all()
    return [
        {
            "id": s.id,
            "name": s.name,
            "feed_url": s.feed_url,
            "site_url": s.site_url,
            "kind": s.kind,
            "category": s.category,
            "sync_status": s.sync_status,
            "sync_message": s.sync_message,
            "last_sync_at": s.last_sync_at,
            "entry_count": int(cnt or 0),
            "subscribed_at": sub_at,
        }
        for s, sub_at, cnt in rows
    ]


def _source_dict(db: Session, source: FeedSource, user: User) -> dict:
    sub = db.scalar(
        select(FeedSourceSubscription).where(
            FeedSourceSubscription.user_id == user.id,
            FeedSourceSubscription.source_id == source.id,
        )
    )
    cnt = db.scalar(
        select(func.count()).select_from(FeedEntry).where(FeedEntry.source_id == source.id)
    )
    return {
        "id": source.id,
        "name": source.name,
        "feed_url": source.feed_url,
        "site_url": source.site_url,
        "kind": source.kind,
        "category": source.category,
        "sync_status": source.sync_status,
        "sync_message": source.sync_message,
        "last_sync_at": source.last_sync_at,
        "entry_count": int(cnt or 0),
        "subscribed_at": sub.created_at if sub else None,
    }


def subscribe_source(
    db: Session,
    user: User,
    *,
    name: str,
    feed_url: str,
    kind: str = SOURCE_KIND_RSS,
    category: str = "",
) -> dict:
    try:
        resolved, site = resolve_feed_url(feed_url, kind=kind)
        meta, entries = fetch_feed(resolved, limit=15)
    except FeedFetchError as e:
        raise bad_request(str(e)) from e

    display_name = (name or meta.title or site or resolved)[:256]
    source = _get_or_create_source(
        db,
        name=display_name,
        feed_url=resolved,
        kind=kind,
        category=category,
        site_url=site or "",
    )
    sub = db.scalar(
        select(FeedSourceSubscription).where(
            FeedSourceSubscription.user_id == user.id,
            FeedSourceSubscription.source_id == source.id,
        )
    )
    if not sub:
        db.add(FeedSourceSubscription(user_id=user.id, source_id=source.id))
        db.flush()
    _upsert_entries(db, source, entries)
    source.sync_status = "ok"
    source.sync_message = f"已拉取 {len(entries)} 条"
    source.last_sync_at = datetime.now(timezone.utc)
    db.flush()
    return _source_dict(db, source, user)


def subscribe_preset(db: Session, user: User, preset_index: int) -> dict:
    if preset_index < 0 or preset_index >= len(CARBON_FEED_PRESETS):
        raise bad_request("无效的推荐订阅")
    p = CARBON_FEED_PRESETS[preset_index]
    return subscribe_source(
        db,
        user,
        name=p["name"],
        feed_url=p["feed_url"],
        kind=p.get("kind", SOURCE_KIND_WEBSITE),
        category=p.get("category", "双碳"),
    )


def unsubscribe_source(db: Session, user: User, source_id: uuid.UUID) -> None:
    sub = db.scalar(
        select(FeedSourceSubscription).where(
            FeedSourceSubscription.user_id == user.id,
            FeedSourceSubscription.source_id == source_id,
        )
    )
    if not sub:
        raise not_found("未订阅该源")
    db.delete(sub)
    db.flush()


def _user_source_ids(db: Session, user: User) -> list[uuid.UUID]:
    return list(
        db.scalars(
            select(FeedSourceSubscription.source_id).where(
                FeedSourceSubscription.user_id == user.id
            )
        ).all()
    )


def list_entries(
    db: Session,
    user: User,
    *,
    source_id: uuid.UUID | None = None,
    kind: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[dict], int]:
    source_ids = _user_source_ids(db, user)
    if not source_ids:
        return [], 0
    if source_id:
        if source_id not in source_ids:
            raise not_found("未订阅该源")
        source_ids = [source_id]

    base = select(FeedEntry, FeedSource).join(
        FeedSource, FeedSource.id == FeedEntry.source_id
    ).where(FeedEntry.source_id.in_(source_ids))
    if kind in (SOURCE_KIND_RSS, SOURCE_KIND_WEBSITE):
        base = base.where(FeedSource.kind == kind)

    count_q = select(func.count()).select_from(FeedEntry).where(
        FeedEntry.source_id.in_(source_ids)
    )
    if kind in (SOURCE_KIND_RSS, SOURCE_KIND_WEBSITE):
        count_q = count_q.join(FeedSource, FeedSource.id == FeedEntry.source_id).where(
            FeedSource.kind == kind
        )
    total = db.scalar(count_q) or 0
    rows = db.execute(
        base.order_by(
            FeedEntry.publish_at.desc().nullslast(),
            FeedEntry.fetched_at.desc(),
        )
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()

    entry_ids = [e.id for e, _ in rows]
    imports: dict[uuid.UUID, uuid.UUID] = {}
    if entry_ids:
        imports = {
            row.entry_id: row.document_id
            for row in db.scalars(
                select(FeedEntryImport).where(
                    FeedEntryImport.user_id == user.id,
                    FeedEntryImport.entry_id.in_(entry_ids),
                )
            ).all()
        }

    items = []
    for entry, source in rows:
        doc_id = imports.get(entry.id)
        items.append(
            _entry_out(
                entry,
                source,
                imported=doc_id is not None,
                document_id=doc_id,
            )
        )
    return items, int(total)


def get_entry_detail(db: Session, user: User, entry_id: uuid.UUID) -> dict:
    row = db.execute(
        select(FeedEntry, FeedSource)
        .join(FeedSource, FeedSource.id == FeedEntry.source_id)
        .where(FeedEntry.id == entry_id)
    ).first()
    if not row:
        raise not_found("条目不存在")
    entry, source = row
    if source.id not in _user_source_ids(db, user):
        raise not_found("条目不存在")
    imp = db.scalar(
        select(FeedEntryImport).where(
            FeedEntryImport.user_id == user.id,
            FeedEntryImport.entry_id == entry.id,
        )
    )
    data = _entry_out(
        entry,
        source,
        imported=imp is not None,
        document_id=imp.document_id if imp else None,
    )
    data["content_html"] = entry.content_html
    return data


def delete_entry(db: Session, user: User, entry_id: uuid.UUID) -> None:
    """删除用户可访问的订阅条目（不删除已导入的文档库文档）。"""
    row = db.execute(
        select(FeedEntry, FeedSource)
        .join(FeedSource, FeedSource.id == FeedEntry.source_id)
        .where(FeedEntry.id == entry_id)
    ).first()
    if not row:
        raise not_found("条目不存在")
    entry, source = row
    if source.id not in _user_source_ids(db, user):
        raise not_found("条目不存在")
    for imp in list(
        db.scalars(select(FeedEntryImport).where(FeedEntryImport.entry_id == entry.id)).all()
    ):
        db.delete(imp)
    db.delete(entry)
    db.flush()


def sync_source(db: Session, user: User, source_id: uuid.UUID) -> dict:
    if source_id not in _user_source_ids(db, user):
        raise not_found("未订阅该源")
    source = db.get(FeedSource, source_id)
    if not source:
        raise not_found("订阅源不存在")

    source.sync_status = "running"
    db.flush()
    try:
        meta, entries = fetch_feed(source.feed_url, limit=30)
        if meta.title and source.name == source.feed_url:
            source.name = meta.title[:256]
        added = _upsert_entries(db, source, entries)
        source.sync_status = "ok"
        source.sync_message = f"共同步 {added} 条新条目（共解析 {len(entries)} 条）"
    except FeedFetchError as e:
        source.sync_status = "error"
        source.sync_message = str(e)
        added = 0
    source.last_sync_at = datetime.now(timezone.utc)
    db.flush()
    return {"synced_entries": added, "message": source.sync_message}


def import_entry_to_document(
    db: Session,
    user: User,
    entry_id: uuid.UUID,
    *,
    scope: str = "personal",
    dept_id: uuid.UUID | None = None,
    sync_knowflow: bool = True,
) -> dict:
    _ = scope
    scope = content_subscription_import_scope()
    dept_id = None

    detail = get_entry_detail(db, user, entry_id)
    existing = db.scalar(
        select(FeedEntryImport).where(
            FeedEntryImport.user_id == user.id,
            FeedEntryImport.entry_id == entry_id,
        )
    )
    if existing:
        from app.services.library_folder_service import (
            assign_document_to_web_favorites_folder,
        )

        assign_document_to_web_favorites_folder(
            db, user, existing.document_id
        )
        synced = False
        if sync_knowflow:
            synced = _try_sync_knowflow(db, user, existing.document_id)
        return {
            "document_id": existing.document_id,
            "knowflow_synced": synced,
            "queued": False,
        }

    entry = db.get(FeedEntry, entry_id)
    if not entry:
        raise not_found("条目不存在")

    desc = (
        f"来源：{detail['source_name']}（{detail['source_kind']}）\n"
        f"链接：{detail['link']}"
    )
    from app.services.library_folder_service import (
        resolve_web_favorites_folder_id_for_user,
    )

    doc = create_document(
        db,
        user,
        title=detail["title"][:500],
        description=desc,
        scope=scope,
        dept_id=dept_id,
        folder_id=resolve_web_favorites_folder_id_for_user(db, user),
    )
    from app.integrations.html_document_export import (
        html_body_to_pdf_bytes,
        resolve_article_html_body,
    )

    link = detail.get("link") or entry.link or ""
    source_label = f"{detail['source_name']}（{detail['source_kind']}）"
    html_body, summary_text = resolve_article_html_body(
        entry.content_html or "",
        summary=entry.summary or "",
        link=link,
        allow_refetch=True,
    )
    if html_body and html_body != (entry.content_html or ""):
        entry.content_html = html_body
    if summary_text and summary_text != (entry.summary or ""):
        entry.summary = summary_text

    file_name, content, mime_type = html_body_to_pdf_bytes(
        doc.title,
        html_body or f"<p>{entry.summary}</p>",
        summary=summary_text or entry.summary or "",
        link=link,
        source_label=source_label,
        fallback_stem="subscription-article",
        allow_refetch=False,
    )  # 正文已在 resolve_article_html_body 中按需重抓

    create_initial_uploaded_version(
        db,
        doc,
        user,
        file_name=file_name,
        mime_type=mime_type,
        content=content,
        schedule_post_upload=False,
    )
    db.refresh(doc)

    db.add(
        FeedEntryImport(entry_id=entry_id, user_id=user.id, document_id=doc.id)
    )
    db.flush()

    from app.services.subscription_import_service import (
        enqueue_subscription_import_finalize,
    )

    job = enqueue_subscription_import_finalize(
        db,
        user,
        doc.id,
        sync_knowflow=sync_knowflow,
        source="feed_entry",
        source_id=entry_id,
        title=doc.title,
        link=link,
        source_label=source_label,
        html_body=html_body or f"<p>{entry.summary}</p>",
        summary=summary_text or entry.summary or "",
        fallback_stem="subscription-article",
    )
    from app.core.platform_cache import invalidate_document_caches

    invalidate_document_caches(str(user.id))
    return {
        "document_id": doc.id,
        "knowflow_synced": False,
        "queued": True,
        "job_id": job.id,
    }


def _try_sync_knowflow(db: Session, user: User, document_id: uuid.UUID) -> bool:
    from app.domains.knowledge.gateway import knowledge
    from app.models.document import Document
    from app.services.document_service import resolve_current_version

    if not knowledge.enabled():
        return False
    doc = db.get(Document, document_id)
    if not doc:
        return False
    db.refresh(doc)
    if not resolve_current_version(db, doc):
        return False
    knowledge.enqueue_sync_after_ingest(document_id, user.id)
    return True
