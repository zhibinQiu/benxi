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
    job_id = uuid.uuid4()
    folder_id = uuid.uuid4()

    with patch.object(
        svc, "get_article_detail", return_value={"title": "t", "source_name": "s", "original_url": "u"}
    ), patch(
        "app.services.wechat_mp_service.create_document",
        return_value=MagicMock(id=doc_id, title="t"),
    ) as create_doc, patch(
        "app.services.wechat_mp_service.create_initial_uploaded_version"
    ) as create_version, patch(
        "app.services.subscription_import_service.enqueue_subscription_import_finalize",
        return_value=MagicMock(id=job_id),
    ) as enqueue_finalize, patch(
        "app.services.library_folder_service.resolve_web_favorites_folder_id_for_user",
        return_value=folder_id,
    ), patch(
        "app.core.platform_cache.invalidate_document_caches"
    ):
        db = MagicMock()
        db.scalar.return_value = None
        db.get.return_value = MagicMock(
            content_html="<p>" + "订阅正文。" * 30 + "</p>",
            summary="摘要说明",
            link="",
        )
        result = svc.import_article_to_document(
            db,
            user,
            article_id,
            scope="company",
            dept_id=uuid.uuid4(),
        )

    create_doc.assert_called_once()
    assert create_doc.call_args.kwargs["scope"] == SCOPE_PERSONAL
    assert create_doc.call_args.kwargs["dept_id"] is None
    assert create_doc.call_args.kwargs["folder_id"] == folder_id
    create_version.assert_called_once()
    assert create_version.call_args.kwargs["file_name"].endswith(".pdf")
    assert create_version.call_args.kwargs["mime_type"] == "application/pdf"
    enqueue_finalize.assert_called_once()
    assert result["queued"] is True
    assert result["job_id"] == job_id


def test_feed_import_uses_personal_scope():
    from app.services import subscription_service as svc

    user = MagicMock(id=uuid.uuid4())
    entry_id = uuid.uuid4()
    doc_id = uuid.uuid4()
    job_id = uuid.uuid4()
    folder_id = uuid.uuid4()

    with patch.object(
        svc,
        "_get_feed_entry_detail",
        return_value={"title": "t", "source_name": "s", "source_kind": "link", "link": ""},
    ), patch(
        "app.services.document_service.create_document",
        return_value=MagicMock(id=doc_id, title="t"),
    ) as create_doc, patch(
        "app.services.document_service.create_initial_uploaded_version"
    ) as create_version, patch(
        "app.services.subscription_import_service.enqueue_subscription_import_finalize",
        return_value=MagicMock(id=job_id),
    ) as enqueue_finalize, patch(
        "app.services.library_folder_service.resolve_web_favorites_folder_id_for_user",
        return_value=folder_id,
    ), patch(
        "app.core.platform_cache.invalidate_document_caches"
    ):
        db = MagicMock()
        db.scalar.return_value = None
        db.get.return_value = MagicMock(
            content_html="<p>" + "订阅正文。" * 30 + "</p>",
            summary="摘要说明",
            link="",
        )
        result = svc._import_feed_entry_to_document(
            db,
            user,
            entry_id,
            sync_knowflow=True,
        )

    create_doc.assert_called_once()
    assert create_doc.call_args.kwargs["scope"] == SCOPE_PERSONAL
    assert create_doc.call_args.kwargs["dept_id"] is None
    assert create_doc.call_args.kwargs["folder_id"] == folder_id
    create_version.assert_called_once()
    assert create_version.call_args.kwargs["file_name"].endswith(".pdf")
    assert create_version.call_args.kwargs["mime_type"] == "application/pdf"
    enqueue_finalize.assert_called_once()
    assert result["queued"] is True
    assert result["job_id"] == job_id
