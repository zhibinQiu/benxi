"""公众号 / Feed 资讯导入文档库分级。"""

from __future__ import annotations

from unittest.mock import MagicMock, patch
import uuid

from app.core.document_scope import SCOPE_PERSONAL, content_subscription_import_scope


def test_content_subscription_import_scope_is_personal():
    assert content_subscription_import_scope() == SCOPE_PERSONAL


def test_wechat_import_uses_personal_scope():
    from app.services import wechat_mp_service as svc

    user = MagicMock(id=uuid.uuid4())
    article_id = uuid.uuid4()
    doc_id = uuid.uuid4()

    with patch.object(
        svc, "get_article_detail", return_value={"title": "t", "source_name": "s", "original_url": "u"}
    ), patch(
        "app.services.wechat_mp_service.create_document",
        return_value=MagicMock(id=doc_id, title="t"),
    ) as create_doc, patch(
        "app.services.wechat_mp_service.create_initial_uploaded_version"
    ) as create_version, patch.object(
        svc, "_try_sync_knowflow", return_value=False
    ):
        db = MagicMock()
        db.scalar.return_value = None
        db.get.return_value = MagicMock(
            content_html="<p>" + "订阅正文。" * 30 + "</p>",
            summary="摘要说明",
            link="",
        )
        svc.import_article_to_document(
            db,
            user,
            article_id,
            scope="company",
            dept_id=uuid.uuid4(),
        )

    create_doc.assert_called_once()
    assert create_doc.call_args.kwargs["scope"] == SCOPE_PERSONAL
    assert create_doc.call_args.kwargs["dept_id"] is None
    create_version.assert_called_once()
    assert create_version.call_args.kwargs["file_name"].endswith(".pdf")
    assert create_version.call_args.kwargs["mime_type"] == "application/pdf"
    assert create_version.call_args.kwargs["content"].startswith(b"%PDF")
    assert len(create_version.call_args.kwargs["content"]) > 500


def test_feed_import_uses_personal_scope():
    from app.services import feed_subscription_service as svc

    user = MagicMock(id=uuid.uuid4())
    entry_id = uuid.uuid4()
    doc_id = uuid.uuid4()

    with patch.object(
        svc,
        "get_entry_detail",
        return_value={"title": "t", "source_name": "s", "source_kind": "rss", "link": ""},
    ), patch(
        "app.services.feed_subscription_service.create_document",
        return_value=MagicMock(id=doc_id, title="t"),
    ) as create_doc, patch(
        "app.services.feed_subscription_service.create_initial_uploaded_version"
    ) as create_version, patch.object(
        svc, "_try_sync_knowflow", return_value=False
    ):
        db = MagicMock()
        db.scalar.return_value = None
        db.get.return_value = MagicMock(
            content_html="<p>" + "订阅正文。" * 30 + "</p>",
            summary="摘要说明",
            link="",
        )
        svc.import_entry_to_document(
            db,
            user,
            entry_id,
            scope="department",
            dept_id=uuid.uuid4(),
        )

    create_doc.assert_called_once()
    assert create_doc.call_args.kwargs["scope"] == SCOPE_PERSONAL
    assert create_doc.call_args.kwargs["dept_id"] is None
    create_version.assert_called_once()
    assert create_version.call_args.kwargs["file_name"].endswith(".pdf")
    assert create_version.call_args.kwargs["mime_type"] == "application/pdf"
    assert create_version.call_args.kwargs["content"].startswith(b"%PDF")
    assert len(create_version.call_args.kwargs["content"]) > 500
