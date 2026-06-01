"""公众号资讯 API（需登录与功能权限）。"""

from __future__ import annotations

from unittest.mock import patch

from app.integrations.wechat_mp_fetcher import ParsedArticle
from datetime import datetime, timezone


def _parsed() -> ParsedArticle:
    return ParsedArticle(
        title="测试文章",
        summary="摘要",
        cover_url="https://example.com/c.jpg",
        author="测试号",
        publish_at=datetime.now(timezone.utc),
        content_html="<p>内容</p>",
        original_url="https://mp.weixin.qq.com/s?__biz=MzTest==",
        biz="MzTest==",
        account_name="测试号",
        content_hash="abc123",
    )


def test_parse_url_requires_auth(client):
    r = client.post(
        "/api/v1/wechat-mp/parse-url",
        json={"url": "https://mp.weixin.qq.com/s?__biz=x"},
    )
    assert r.status_code == 401


def test_sync_source_long_url_not_500(client, admin_token):
    """同步入库时超长微信链接不应导致 500。"""
    from datetime import datetime, timezone

    from app.database import SessionLocal
    from app.models.org import User
    from app.services import wechat_mp_service as svc
    from sqlalchemy import select

    long_url = "https://mp.weixin.qq.com/s?__biz=MzTest123==&chksm=" + "x" * 1050
    parsed = ParsedArticle(
        title="长链接测试",
        summary="s",
        cover_url="",
        author="a",
        publish_at=datetime.now(timezone.utc),
        content_html="<p>x</p>",
        original_url=long_url,
        biz="MzTest123==",
        account_name="n",
        content_hash="longurlhash001",
    )

    db = SessionLocal()
    try:
        user = db.scalar(select(User).where(User.username == "admin"))
        assert user is not None
        with patch(
            "app.services.wechat_mp_service.fetch_recent_articles",
            return_value=([{"url": long_url, "title": "t"}], "mock"),
        ), patch(
            "app.services.wechat_mp_service.fetch_article",
            return_value=parsed,
        ):
            row = svc.subscribe_source(
                db, user, name="长链测试号", sample_url=None, biz="MzTest123=="
            )
            db.commit()
            result = svc.sync_source(db, user, row["id"])
            db.commit()
        assert result["synced_articles"] == 1
        from app.models.wechat_mp import WechatMpArticle
        from sqlalchemy import select

        article = db.scalar(
            select(WechatMpArticle).where(
                WechatMpArticle.content_hash == "longurlhash001"
            )
        )
        assert article is not None
        assert len(article.original_url) <= 1024
    finally:
        db.close()


def test_parse_url_authenticated(client, admin_token):
    headers = {"Authorization": f"Bearer {admin_token}"}
    with patch(
        "app.api.wechat_mp.svc.parse_url",
        return_value=_parsed(),
    ):
        r = client.post(
            "/api/v1/wechat-mp/parse-url",
            json={"url": "https://mp.weixin.qq.com/s?__biz=MzTest=="},
            headers=headers,
        )
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["title"] == "测试文章"
    assert data["biz"] == "MzTest=="
