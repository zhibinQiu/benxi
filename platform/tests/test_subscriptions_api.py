"""统一资讯订阅 API。"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import patch

from app.integrations.feed_fetcher import ParsedFeedEntry
from app.integrations.wechat_mp_fetcher import ParsedArticle


def _web_parsed() -> ParsedFeedEntry:
    return ParsedFeedEntry(
        title="网页文章",
        summary="摘要",
        link="https://example.com/news/1",
        content_html="<p>正文</p>",
        entry_key="webkey001",
        publish_at=datetime.now(timezone.utc),
    )


def _wechat_parsed() -> ParsedArticle:
    return ParsedArticle(
        title="微信文章",
        summary="摘要",
        cover_url="",
        author="测试号",
        publish_at=datetime.now(timezone.utc),
        content_html="<p>微信</p>",
        original_url="https://mp.weixin.qq.com/s?__biz=MzTest==",
        biz="MzTest==",
        account_name="测试号",
        content_hash="wxhash001",
    )


def test_ingest_url_requires_auth(client):
    r = client.post(
        "/api/v1/subscriptions/ingest-url",
        json={"url": "https://example.com/a"},
    )
    assert r.status_code == 401


def test_ingest_web_url(client, admin_token):
    with patch(
        "app.services.subscription_service.fetch_web_article",
        return_value=_web_parsed(),
    ):
        r = client.post(
            "/api/v1/subscriptions/ingest-url",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"url": "https://example.com/news/1"},
        )
    assert r.status_code == 200, r.text
    body = r.json()["data"]
    assert body["ref"].startswith("f:")
    assert body["title"] == "网页文章"
    assert body["is_wechat"] is False
    assert "content_markdown" in body


def test_list_items_after_ingest(client, admin_token):
    with patch(
        "app.services.subscription_service.fetch_web_article",
        return_value=_web_parsed(),
    ):
        client.post(
            "/api/v1/subscriptions/ingest-url",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"url": "https://example.com/news/2"},
        )
    r = client.get(
        "/api/v1/subscriptions/items",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["total"] >= 1
    assert any(i["title"] == "网页文章" for i in data["items"])


def test_ingest_wechat_url(client, admin_token):
    with patch(
        "app.services.wechat_mp_service.fetch_article",
        return_value=_wechat_parsed(),
    ):
        r = client.post(
            "/api/v1/subscriptions/ingest-url",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"url": "https://mp.weixin.qq.com/s?__biz=MzTest=="},
        )
    assert r.status_code == 200, r.text
    assert r.json()["data"]["ref"].startswith("w:")


def test_delete_item_after_ingest(client, admin_token):
    parsed = ParsedFeedEntry(
        title="待删除",
        summary="摘要",
        link="https://example.com/news/del-me",
        content_html="<p>正文</p>",
        entry_key="webkey-del",
        publish_at=datetime.now(timezone.utc),
    )
    with patch(
        "app.services.subscription_service.fetch_web_article",
        return_value=parsed,
    ):
        ing = client.post(
            "/api/v1/subscriptions/ingest-url",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"url": "https://example.com/news/del-me"},
        )
    ref = ing.json()["data"]["ref"]
    r = client.delete(
        f"/api/v1/subscriptions/items/{ref}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["data"]["deleted"] is True
    detail = client.get(
        f"/api/v1/subscriptions/items/{ref}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert detail.status_code == 404
    listed = client.get(
        "/api/v1/subscriptions/items",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert listed.status_code == 200, listed.text
    assert not any(
        i["link"] == "https://example.com/news/del-me"
        for i in listed.json()["data"]["items"]
    )


def test_delete_item_hides_duplicate_link_entries(client, admin_token):
    from sqlalchemy import select

    from app.database import SessionLocal
    from app.models.feed_subscription import FeedEntry, FeedSource, FeedSourceSubscription
    from app.models.org import User
    from app.services.subscription_service import REF_FEED, make_ref

    parsed = ParsedFeedEntry(
        title="重复链接",
        summary="摘要",
        link="https://example.com/news/dup-link",
        content_html="<p>正文</p>",
        entry_key="webkey-dup-a",
        publish_at=datetime.now(timezone.utc),
    )
    with patch(
        "app.services.subscription_service.fetch_web_article",
        return_value=parsed,
    ):
        ing = client.post(
            "/api/v1/subscriptions/ingest-url",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"url": "https://example.com/news/dup-link"},
        )
    ref = ing.json()["data"]["ref"]

    db = SessionLocal()
    try:
        user = db.scalar(select(User).where(User.username == "admin"))
        assert user is not None
        source_b = FeedSource(
            feed_url="https://example.com/rss-dup-test.xml",
            site_url="https://example.com",
            name="示例 RSS",
            kind="rss",
            category="双碳",
        )
        db.add(source_b)
        db.flush()
        db.add(FeedSourceSubscription(user_id=user.id, source_id=source_b.id))
        entry_b = FeedEntry(
            source_id=source_b.id,
            title="重复链接 RSS",
            summary="摘要",
            link="https://example.com/news/dup-link",
            content_html="<p>正文</p>",
            entry_key="webkey-dup-b",
        )
        db.add(entry_b)
        db.commit()
        ref_b = make_ref(REF_FEED, entry_b.id)
    finally:
        db.close()

    listed = client.get(
        "/api/v1/subscriptions/items",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert listed.json()["data"]["total"] >= 2

    r = client.delete(
        f"/api/v1/subscriptions/items/{ref}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert r.status_code == 200, r.text

    listed_after = client.get(
        "/api/v1/subscriptions/items",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    links = [i["link"] for i in listed_after.json()["data"]["items"]]
    assert "https://example.com/news/dup-link" not in links

    detail_b = client.get(
        f"/api/v1/subscriptions/items/{ref_b}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert detail_b.status_code == 404


def test_delete_item_after_import_keeps_document(client, admin_token):
    parsed = ParsedFeedEntry(
        title="导入后删除",
        summary="摘要",
        link="https://example.com/news/del-imported",
        content_html="<p>正文</p>",
        entry_key="webkey-del-imp",
        publish_at=datetime.now(timezone.utc),
    )
    with patch(
        "app.services.subscription_service.fetch_web_article",
        return_value=parsed,
    ):
        ing = client.post(
            "/api/v1/subscriptions/ingest-url",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"url": "https://example.com/news/del-imported"},
        )
    ref = ing.json()["data"]["ref"]
    with patch(
        "app.services.feed_subscription_service._try_sync_knowflow",
        return_value=False,
    ):
        imp = client.post(
            f"/api/v1/subscriptions/items/{ref}/import",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={},
        )
    doc_id = imp.json()["data"]["document_id"]
    r = client.delete(
        f"/api/v1/subscriptions/items/{ref}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert r.status_code == 200, r.text
    doc = client.get(
        f"/api/v1/documents/{doc_id}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert doc.status_code == 200, doc.text
