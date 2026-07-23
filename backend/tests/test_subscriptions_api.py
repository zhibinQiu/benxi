"""统一资讯订阅 API。"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import patch

from app.integrations.web_article_fetcher import ParsedFeedEntry
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
            feed_url="https://example.com/link-dup-test",
            site_url="https://example.com",
            name="示例链接源",
            kind="link",
            category="双碳",
        )
        db.add(source_b)
        db.flush()
        db.add(FeedSourceSubscription(user_id=user.id, source_id=source_b.id))
        entry_b = FeedEntry(
            source_id=source_b.id,
            title="重复链接收录",
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
        "app.services.subscription_service._try_sync_knowflow",
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


def test_admin_can_open_other_user_wechat_item(client, admin_token):
    """管理员 all_users 列表可见的他人微信文章，详情应可打开（非「文章不存在」）。"""
    import uuid
    from datetime import datetime, timezone

    from sqlalchemy import select

    from app.database import SessionLocal
    from app.models.org import User
    from app.models.wechat_mp import (
        WechatMpArticle,
        WechatMpSource,
        WechatMpSourceSubscription,
    )
    from app.services.subscription_service import REF_WECHAT, make_ref

    db = SessionLocal()
    try:
        admin = db.scalar(select(User).where(User.username == "admin"))
        assert admin is not None
        other = User(
            id=uuid.uuid4(),
            username=f"sub-member-{uuid.uuid4().hex[:6]}",
            display_name="资讯成员",
            phone=f"139{uuid.uuid4().int % 10**8:08d}",
            password_hash="x",
            status="active",
        )
        db.add(other)
        db.flush()
        source = WechatMpSource(
            id=uuid.uuid4(),
            biz=f"MzTestOther{uuid.uuid4().hex[:8]}",
            name="他人公众号",
        )
        db.add(source)
        db.flush()
        db.add(
            WechatMpSourceSubscription(user_id=other.id, source_id=source.id)
        )
        article = WechatMpArticle(
            id=uuid.uuid4(),
            source_id=source.id,
            title="他人收录的微信文章",
            summary="摘要",
            content_html="<p>正文</p>",
            original_url=f"https://mp.weixin.qq.com/s?__biz={source.biz}",
            content_hash=uuid.uuid4().hex,
            publish_at=datetime.now(timezone.utc),
        )
        db.add(article)
        db.commit()
        ref = make_ref(REF_WECHAT, article.id)
        # 管理员本人未订阅该源
        assert source.id not in {
            row
            for row in db.scalars(
                select(WechatMpSourceSubscription.source_id).where(
                    WechatMpSourceSubscription.user_id == admin.id
                )
            ).all()
        }
    finally:
        db.close()

    headers = {"Authorization": f"Bearer {admin_token}"}
    listed = client.get(
        "/api/v1/subscriptions/items",
        params={"all_users": "true", "page_size": 50},
        headers=headers,
    )
    assert listed.status_code == 200, listed.text
    assert any(i["ref"] == ref for i in listed.json()["data"]["items"])

    detail = client.get(
        f"/api/v1/subscriptions/items/{ref}",
        headers=headers,
    )
    assert detail.status_code == 200, detail.text
    assert detail.json()["data"]["title"] == "他人收录的微信文章"


def test_list_items_keyword_bm25_ranks_title_match_first(client, admin_token):
    """有关键词时按 BM25 相关度排序：标题强匹配应排在弱匹配之前。"""
    headers = {"Authorization": f"Bearer {admin_token}"}
    # 使用罕见专有词，避免与库内历史资讯碰撞
    docs = [
        ParsedFeedEntry(
            title="今日天气晴朗",
            summary="无关摘要",
            link="https://example.com/news/bm25-a",
            content_html="<p>天气</p>",
            entry_key="bm25-a",
            publish_at=datetime.now(timezone.utc),
        ),
        ParsedFeedEntry(
            title="市场周报",
            summary="关于 Quorixylene 催化材料的简讯",
            link="https://example.com/news/bm25-b",
            content_html="<p>周报</p>",
            entry_key="bm25-b",
            publish_at=datetime.now(timezone.utc),
        ),
        ParsedFeedEntry(
            title="Quorixylene 催化材料技术白皮书",
            summary="政策要点",
            link="https://example.com/news/bm25-c",
            content_html="<p>政策</p>",
            entry_key="bm25-c",
            publish_at=datetime.now(timezone.utc),
        ),
    ]
    for parsed in docs:
        with patch(
            "app.services.subscription_service.fetch_web_article",
            return_value=parsed,
        ):
            r = client.post(
                "/api/v1/subscriptions/ingest-url",
                headers=headers,
                json={"url": parsed.link},
            )
            assert r.status_code == 200, r.text

    listed = client.get(
        "/api/v1/subscriptions/items",
        params={"keyword": "Quorixylene 催化材料", "page_size": 50},
        headers=headers,
    )
    assert listed.status_code == 200, listed.text
    data = listed.json()["data"]
    titles = [i["title"] for i in data["items"]]
    assert "Quorixylene 催化材料技术白皮书" in titles
    assert titles[0] == "Quorixylene 催化材料技术白皮书"
    assert "今日天气晴朗" not in titles

    # 无关键词仍按时间倒序可用
    all_listed = client.get(
        "/api/v1/subscriptions/items",
        params={"page_size": 50},
        headers=headers,
    )
    assert all_listed.status_code == 200, all_listed.text
    assert all_listed.json()["data"]["total"] >= 3
