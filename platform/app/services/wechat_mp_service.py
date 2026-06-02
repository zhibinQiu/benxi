"""公众号跟踪列表与推文入库。"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.document_scope import content_subscription_import_scope
from app.core.exceptions import bad_request, not_found
from app.integrations.wechat_mp_fetcher import (
    ParsedArticle,
    WechatMpFetchError,
    fetch_article,
    fetch_recent_articles,
)
from app.models.org import User
from app.models.wechat_mp import (
    WechatMpArticle,
    WechatMpArticleImport,
    WechatMpSource,
    WechatMpSourceSubscription,
)
from app.services.document_service import create_document, create_initial_uploaded_version

logger = logging.getLogger(__name__)

_ORIGINAL_URL_MAX = 1024


def _clamp_original_url(url: str) -> str:
    text = (url or "").strip()
    if len(text) <= _ORIGINAL_URL_MAX:
        return text
    return text[:_ORIGINAL_URL_MAX]


def _article_to_out(
    article: WechatMpArticle,
    source: WechatMpSource,
    *,
    imported: bool = False,
    document_id: uuid.UUID | None = None,
) -> dict:
    return {
        "id": article.id,
        "source_id": source.id,
        "source_name": source.name,
        "title": article.title,
        "summary": article.summary,
        "cover_url": article.cover_url,
        "author": article.author,
        "publish_at": article.publish_at,
        "original_url": article.original_url,
        "fetched_at": article.fetched_at,
        "imported": imported,
        "document_id": document_id,
    }


def parse_url(url: str) -> ParsedArticle:
    try:
        return fetch_article(url)
    except WechatMpFetchError as e:
        raise bad_request(str(e)) from e


def _normalize_manual_biz(biz: str | None) -> str:
    from app.integrations.wechat_mp_fetcher import _decode_biz, _looks_like_biz

    raw = _decode_biz((biz or "").strip())
    if raw and _looks_like_biz(raw):
        return raw
    if raw:
        raise bad_request("Biz 格式无效，请填写链接中 __biz= 后的完整字符串")
    return ""


def _get_or_create_source(
    db: Session,
    parsed: ParsedArticle | None,
    name: str,
    *,
    manual_biz: str | None = None,
) -> WechatMpSource:
    biz = _normalize_manual_biz(manual_biz)
    if parsed and parsed.biz:
        biz = parsed.biz
    if not biz:
        raise bad_request(
            "无法解析公众号标识。请粘贴微信「复制链接」的完整文章 URL，"
            "或在添加时手动填写 Biz"
        )

    source = db.scalar(select(WechatMpSource).where(WechatMpSource.biz == biz))
    account = ""
    if parsed:
        account = parsed.account_name or parsed.author
    display_name = (name or account or biz)[:256]
    if source:
        if display_name and source.name != display_name:
            source.name = display_name
        if parsed and parsed.account_name and not source.intro:
            source.intro = parsed.account_name
        return source

    source = WechatMpSource(
        biz=biz,
        name=display_name,
        intro=(parsed.account_name if parsed else "") or "",
    )
    db.add(source)
    db.flush()
    return source


def _upsert_article(db: Session, source: WechatMpSource, parsed: ParsedArticle) -> WechatMpArticle:
    existing = db.scalar(
        select(WechatMpArticle).where(
            WechatMpArticle.source_id == source.id,
            WechatMpArticle.content_hash == parsed.content_hash,
        )
    )
    if existing:
        existing.title = parsed.title
        existing.summary = parsed.summary or existing.summary
        existing.cover_url = parsed.cover_url or existing.cover_url
        existing.content_html = parsed.content_html or existing.content_html
        existing.original_url = _clamp_original_url(parsed.original_url)
        if parsed.publish_at:
            existing.publish_at = parsed.publish_at
        existing.fetched_at = datetime.now(timezone.utc)
        return existing

    article = WechatMpArticle(
        source_id=source.id,
        title=parsed.title,
        summary=parsed.summary,
        cover_url=parsed.cover_url,
        author=parsed.author or source.name,
        publish_at=parsed.publish_at,
        content_html=parsed.content_html,
        original_url=_clamp_original_url(parsed.original_url),
        content_hash=parsed.content_hash,
    )
    db.add(article)
    db.flush()
    return article


def list_user_sources(db: Session, user: User) -> list[dict]:
    rows = db.execute(
        select(
            WechatMpSource,
            WechatMpSourceSubscription.created_at,
            func.count(WechatMpArticle.id),
        )
        .join(
            WechatMpSourceSubscription,
            WechatMpSourceSubscription.source_id == WechatMpSource.id,
        )
        .outerjoin(WechatMpArticle, WechatMpArticle.source_id == WechatMpSource.id)
        .where(WechatMpSourceSubscription.user_id == user.id)
        .group_by(WechatMpSource.id, WechatMpSourceSubscription.created_at)
        .order_by(WechatMpSourceSubscription.created_at.desc())
    ).all()

    out: list[dict] = []
    for source, subscribed_at, article_count in rows:
        out.append(
            {
                "id": source.id,
                "biz": source.biz,
                "name": source.name,
                "avatar_url": source.avatar_url,
                "intro": source.intro,
                "sync_status": source.sync_status,
                "sync_message": source.sync_message,
                "last_sync_at": source.last_sync_at,
                "article_count": int(article_count or 0),
                "subscribed_at": subscribed_at,
            }
        )
    return out


def subscribe_source(
    db: Session,
    user: User,
    *,
    name: str,
    sample_url: str | None,
    biz: str | None = None,
) -> dict:
    parsed: ParsedArticle | None = None
    if sample_url:
        parsed = parse_url(sample_url.strip())
    elif not _normalize_manual_biz(biz):
        raise bad_request("请提供文章链接，或手动填写公众号 Biz")

    source = _get_or_create_source(db, parsed, name, manual_biz=biz)
    if parsed:
        _upsert_article(db, source, parsed)

    sub = db.scalar(
        select(WechatMpSourceSubscription).where(
            WechatMpSourceSubscription.user_id == user.id,
            WechatMpSourceSubscription.source_id == source.id,
        )
    )
    if not sub:
        sub = WechatMpSourceSubscription(user_id=user.id, source_id=source.id)
        db.add(sub)
        db.flush()

    count = db.scalar(
        select(func.count())
        .select_from(WechatMpArticle)
        .where(WechatMpArticle.source_id == source.id)
    )
    return {
        "id": source.id,
        "biz": source.biz,
        "name": source.name,
        "avatar_url": source.avatar_url,
        "intro": source.intro,
        "sync_status": source.sync_status,
        "sync_message": source.sync_message,
        "last_sync_at": source.last_sync_at,
        "article_count": int(count or 0),
        "subscribed_at": sub.created_at if sub else datetime.now(timezone.utc),
    }


def unsubscribe_source(db: Session, user: User, source_id: uuid.UUID) -> None:
    sub = db.scalar(
        select(WechatMpSourceSubscription).where(
            WechatMpSourceSubscription.user_id == user.id,
            WechatMpSourceSubscription.source_id == source_id,
        )
    )
    if not sub:
        raise not_found("未跟踪该公众号")
    db.delete(sub)
    db.flush()


def _user_source_ids(db: Session, user: User) -> list[uuid.UUID]:
    return list(
        db.scalars(
            select(WechatMpSourceSubscription.source_id).where(
                WechatMpSourceSubscription.user_id == user.id
            )
        ).all()
    )


def list_articles(
    db: Session,
    user: User,
    *,
    source_id: uuid.UUID | None = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[dict], int]:
    source_ids = _user_source_ids(db, user)
    if not source_ids:
        return [], 0
    if source_id:
        if source_id not in source_ids:
            raise not_found("未跟踪该公众号")
        source_ids = [source_id]

    total = (
        db.scalar(
            select(func.count())
            .select_from(WechatMpArticle)
            .where(WechatMpArticle.source_id.in_(source_ids))
        )
        or 0
    )
    base = (
        select(WechatMpArticle, WechatMpSource)
        .join(WechatMpSource, WechatMpSource.id == WechatMpArticle.source_id)
        .where(WechatMpArticle.source_id.in_(source_ids))
    )
    rows = db.execute(
        base.order_by(
            WechatMpArticle.publish_at.desc().nullslast(),
            WechatMpArticle.fetched_at.desc(),
        )
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()

    article_ids = [a.id for a, _ in rows]
    imports: dict[uuid.UUID, uuid.UUID] = {}
    if article_ids:
        imports = {
            row.article_id: row.document_id
            for row in db.scalars(
                select(WechatMpArticleImport).where(
                    WechatMpArticleImport.user_id == user.id,
                    WechatMpArticleImport.article_id.in_(article_ids),
                )
            ).all()
        }

    items: list[dict] = []
    for article, source in rows:
        doc_id = imports.get(article.id)
        items.append(
            _article_to_out(
                article,
                source,
                imported=doc_id is not None,
                document_id=doc_id,
            )
        )
    return items, int(total)


def get_article_detail(
    db: Session, user: User, article_id: uuid.UUID
) -> dict:
    row = db.execute(
        select(WechatMpArticle, WechatMpSource)
        .join(WechatMpSource, WechatMpSource.id == WechatMpArticle.source_id)
        .where(WechatMpArticle.id == article_id)
    ).first()
    if not row:
        raise not_found("文章不存在")
    article, source = row
    source_ids = _user_source_ids(db, user)
    if source.id not in source_ids:
        raise not_found("文章不存在")

    imp = db.scalar(
        select(WechatMpArticleImport).where(
            WechatMpArticleImport.user_id == user.id,
            WechatMpArticleImport.article_id == article.id,
        )
    )
    data = _article_to_out(
        article,
        source,
        imported=imp is not None,
        document_id=imp.document_id if imp else None,
    )
    data["content_html"] = article.content_html
    return data


def delete_article(db: Session, user: User, article_id: uuid.UUID) -> None:
    """删除用户可访问的公众号文章（不删除已导入的文档库文档）。"""
    row = db.execute(
        select(WechatMpArticle, WechatMpSource)
        .join(WechatMpSource, WechatMpSource.id == WechatMpArticle.source_id)
        .where(WechatMpArticle.id == article_id)
    ).first()
    if not row:
        raise not_found("文章不存在")
    article, source = row
    if source.id not in _user_source_ids(db, user):
        raise not_found("文章不存在")
    for imp in list(
        db.scalars(
            select(WechatMpArticleImport).where(
                WechatMpArticleImport.article_id == article.id
            )
        ).all()
    ):
        db.delete(imp)
    db.delete(article)
    db.flush()


def ingest_url(db: Session, user: User, url: str) -> dict:
    parsed = parse_url(url)
    source = _get_or_create_source(db, parsed, parsed.account_name or parsed.author)
    sub = db.scalar(
        select(WechatMpSourceSubscription).where(
            WechatMpSourceSubscription.user_id == user.id,
            WechatMpSourceSubscription.source_id == source.id,
        )
    )
    if not sub:
        db.add(
            WechatMpSourceSubscription(user_id=user.id, source_id=source.id)
        )
    article = _upsert_article(db, source, parsed)
    db.flush()
    return get_article_detail(db, user, article.id)


def _repair_source_biz(db: Session, source: WechatMpSource) -> bool:
    """用已收录文章的链接回填/修正 biz。"""
    from app.integrations.wechat_mp_fetcher import _looks_like_biz, extract_biz_from_url

    if _looks_like_biz(source.biz):
        return True
    latest = db.scalar(
        select(WechatMpArticle)
        .where(WechatMpArticle.source_id == source.id)
        .order_by(WechatMpArticle.fetched_at.desc())
        .limit(1)
    )
    if not latest or not latest.original_url:
        return False
    biz = extract_biz_from_url(latest.original_url)
    if not biz:
        try:
            biz = parse_url(latest.original_url).biz
        except Exception:
            return False
    if biz and biz != source.biz:
        conflict = db.scalar(
            select(WechatMpSource).where(
                WechatMpSource.biz == biz, WechatMpSource.id != source.id
            )
        )
        if conflict:
            return False
        source.biz = biz
        db.flush()
    return _looks_like_biz(source.biz)


def sync_source(db: Session, user: User, source_id: uuid.UUID) -> dict:
    if source_id not in _user_source_ids(db, user):
        raise not_found("未跟踪该公众号")

    source = db.get(WechatMpSource, source_id)
    if not source:
        raise not_found("公众号不存在")

    if not _repair_source_biz(db, source):
        return {
            "synced_articles": 0,
            "message": (
                "公众号 Biz 无效。请先「粘贴链接收录」至少一篇文章，"
                "或删除后重新添加并填写完整链接 / Biz"
            ),
        }

    source.sync_status = "running"
    source.sync_message = ""
    db.flush()

    synced = 0
    errors: list[str] = []
    entries, hint = fetch_recent_articles(source.biz, count=10)
    if not entries:
        source.sync_status = "idle"
        source.sync_message = hint
        source.last_sync_at = datetime.now(timezone.utc)
        db.flush()
        return {"synced_articles": 0, "message": source.sync_message}

    for entry in entries:
        link = entry.get("url") or ""
        if not link:
            continue
        try:
            parsed = fetch_article(link)
            _upsert_article(db, source, parsed)
            synced += 1
        except WechatMpFetchError as e:
            errors.append(str(e))
            logger.info("sync article skip %s: %s", link, e)
        except Exception as e:
            errors.append("入库失败")
            logger.exception("sync article failed %s: %s", link, e)

    source.sync_status = "ok" if synced else "partial"
    source.sync_message = hint + (
        f"；成功 {synced} 篇"
        + (f"，{len(errors)} 篇失败" if errors else "")
    )
    source.last_sync_at = datetime.now(timezone.utc)
    db.flush()
    return {"synced_articles": synced, "message": source.sync_message}


def import_article_to_document(
    db: Session,
    user: User,
    article_id: uuid.UUID,
    *,
    scope: str = "personal",
    dept_id: uuid.UUID | None = None,
    sync_knowflow: bool = True,
) -> dict:
    # 资讯导入文档库固定「我的」，忽略请求中的其它分级
    _ = scope
    scope = content_subscription_import_scope()
    dept_id = None

    detail = get_article_detail(db, user, article_id)
    existing = db.scalar(
        select(WechatMpArticleImport).where(
            WechatMpArticleImport.user_id == user.id,
            WechatMpArticleImport.article_id == article_id,
        )
    )
    if existing:
        knowflow_synced = False
        if sync_knowflow:
            knowflow_synced = _try_sync_knowflow(db, user, existing.document_id)
        return {
            "document_id": existing.document_id,
            "knowflow_synced": knowflow_synced,
        }

    article = db.get(WechatMpArticle, article_id)
    if not article:
        raise not_found("文章不存在")

    desc = (
        f"来源公众号：{detail['source_name']}\n"
        f"原文：{detail['original_url']}"
    )
    doc = create_document(
        db,
        user,
        title=detail["title"][:500],
        description=desc,
        scope=scope,
        dept_id=dept_id,
    )

    from app.integrations.html_document_export import (
        html_body_to_pdf_bytes,
        resolve_article_html_body,
    )

    link = detail.get("original_url") or article.original_url or ""
    html_body, summary_text = resolve_article_html_body(
        article.content_html or "",
        summary=article.summary or "",
        link=link,
    )
    if html_body and html_body != (article.content_html or ""):
        article.content_html = html_body
    if summary_text and summary_text != (article.summary or ""):
        article.summary = summary_text

    file_name, content, mime_type = html_body_to_pdf_bytes(
        doc.title,
        html_body or f"<p>{article.summary}</p>",
        summary=summary_text or article.summary or "",
        link=link,
        source_label=detail.get("source_name") or "微信公众号",
        fallback_stem="wechat-article",
        allow_refetch=False,
    )

    create_initial_uploaded_version(
        db,
        doc,
        user,
        file_name=file_name,
        mime_type=mime_type,
        content=content,
    )
    db.refresh(doc)

    db.add(
        WechatMpArticleImport(
            article_id=article_id,
            user_id=user.id,
            document_id=doc.id,
        )
    )
    db.flush()

    knowflow_synced = False
    if sync_knowflow:
        knowflow_synced = _try_sync_knowflow(db, user, doc.id)

    return {"document_id": doc.id, "knowflow_synced": knowflow_synced}


def _try_sync_knowflow(db: Session, user: User, document_id: uuid.UUID) -> bool:
    from app.models.document import Document
    from app.services.ragflow_sync_service import sync_document_to_knowflow

    from app.services.document_service import resolve_current_version

    doc = db.get(Document, document_id)
    if not doc:
        return False
    db.refresh(doc)
    resolve_current_version(db, doc)
    try:
        return bool(sync_document_to_knowflow(db, user, doc, force=True))
    except Exception as e:
        logger.warning("KnowFlow sync after wechat import: %s", e)
        return False
