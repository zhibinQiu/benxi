"""资讯导入与首版上传：避免 current_version_id 被外层 commit 覆盖。"""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch


def test_create_initial_uploaded_version_flushes_without_commit():
    from app.services.documents.crud import create_initial_uploaded_version

    document = MagicMock(id=uuid.uuid4())
    user = MagicMock(id=uuid.uuid4())
    version = MagicMock(id=uuid.uuid4())
    db = MagicMock()
    store = MagicMock()
    store.build_file_key.return_value = "docs/x/v1/a.pdf"

    with patch("app.services.documents.crud.get_object_store", return_value=store), patch(
        "app.services.documents.crud.DocumentVersion",
        return_value=version,
    ):
        create_initial_uploaded_version(
            db,
            document,
            user,
            file_name="a.pdf",
            mime_type="application/pdf",
            content=b"%PDF-1.4",
            schedule_post_upload=False,
        )

    db.commit.assert_not_called()
    assert db.flush.call_count >= 2
    assert document.current_version_id == version.id


def test_subscription_import_uses_resolve_current_version():
    import inspect

    from app.services import subscription_import_service as svc

    source = inspect.getsource(svc.run_subscription_import_job)
    assert "resolve_current_version" in source
    assert "repair=True" in source


def test_enqueue_subscription_import_includes_document_title():
    from app.services.subscription_import_service import enqueue_subscription_import_finalize

    user = MagicMock(id=uuid.uuid4())
    doc_id = uuid.uuid4()
    source_id = uuid.uuid4()
    job = MagicMock(id=uuid.uuid4())
    db = MagicMock()

    with patch(
        "app.services.subscription_import_service.create_job",
        return_value=job,
    ) as create_job, patch(
        "app.core.db_after_commit.run_after_commit",
    ):
        enqueue_subscription_import_finalize(
            db,
            user,
            doc_id,
            source="feed_entry",
            source_id=source_id,
            title="  测试资讯标题  ",
        )

    payload = create_job.call_args.kwargs["payload"]
    assert payload["document_title"] == "测试资讯标题"
    assert payload["title"] == "测试资讯标题"


def test_subscription_import_always_regenerates_pdf_before_index():
    import inspect

    from app.services import subscription_import_service as svc

    source = inspect.getsource(svc.run_subscription_import_job)
    assert "resolve_article_html_body" in source
    assert "allow_refetch=True" in source
    assert "replace_version_file_content" in source


def test_subscription_import_uses_subscription_pipeline():
    import inspect

    from app.services import subscription_import_service as svc

    source = inspect.getsource(svc.run_subscription_import_job)
    assert "create_subscription_pipeline_index_job" in source
    assert "index_job_id" in source


def test_create_subscription_pipeline_index_job_payload():
    from unittest.mock import MagicMock, patch

    from app.services.knowledge_sync_job_service import (
        SUBSCRIPTION_PIPELINE_MODE,
        create_subscription_pipeline_index_job,
    )

    user_id = uuid.uuid4()
    doc_id = uuid.uuid4()
    ver_id = uuid.uuid4()
    job = MagicMock(id=uuid.uuid4())
    db = MagicMock()

    with patch(
        "app.services.knowledge_sync_job_service.knowledge.enabled",
        return_value=True,
    ), patch(
        "app.services.knowledge_parser_service.index_stack_block_reason",
        return_value=None,
    ), patch(
        "app.services.knowledge_sync_job_service.get_document",
        return_value=MagicMock(title="测试"),
    ), patch(
        "app.services.knowledge_sync_job_service.create_job",
        return_value=job,
    ) as create_job:
        out = create_subscription_pipeline_index_job(
            db,
            user_id=user_id,
            document_id=doc_id,
            version_id=ver_id,
            document_title="  标题  ",
            article_html_body="<p>正文</p>",
            article_summary="摘要",
            article_link="https://example.com/a",
            article_source_label="测试源",
            article_title="资讯标题",
        )

    assert out is job
    payload = create_job.call_args.kwargs["payload"]
    assert payload["mode"] == SUBSCRIPTION_PIPELINE_MODE
    assert payload["layout_recognize"] == "DeepDOC"
    assert payload["document_title"] == "标题"
    assert payload["version_id"] == str(ver_id)
    assert payload["article_html_body"] == "<p>正文</p>"
    assert payload["article_summary"] == "摘要"
    assert payload["article_link"] == "https://example.com/a"
    assert payload["article_source_label"] == "测试源"
    assert payload["article_title"] == "资讯标题"
