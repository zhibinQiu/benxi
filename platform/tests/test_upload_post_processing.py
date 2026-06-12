"""上传 API 不应同步阻塞分块/索引。"""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

from app.services.documents.post_upload import schedule_post_upload_processing


def test_schedule_post_upload_processing_starts_thread():
    doc_id = uuid.uuid4()
    ver_id = uuid.uuid4()
    user_id = uuid.uuid4()

    with patch(
        "app.services.documents.post_upload.threading.Thread"
    ) as thread_cls:
        thread_cls.return_value = MagicMock()
        schedule_post_upload_processing(doc_id, ver_id, user_id)

    thread_cls.assert_called_once()
    kwargs = thread_cls.call_args.kwargs
    assert kwargs["daemon"] is True
    assert kwargs["args"] == (doc_id, ver_id, user_id)


def test_complete_upload_does_not_sync_git(monkeypatch):
    from app.services.documents import crud

    called = {"git": 0}

    def _fake_git(_db, _version):
        called["git"] += 1

    monkeypatch.setattr(crud, "_try_sync_version_git", _fake_git)

    db = MagicMock()
    user = MagicMock(id=uuid.uuid4())
    document = MagicMock(id=uuid.uuid4(), current_version_id=None)
    version = MagicMock(
        id=uuid.uuid4(),
        document_id=document.id,
        file_name="a.pdf",
        mime_type="application/pdf",
        checksum="abc",
        file_key="k",
    )

    with patch("app.services.documents.crud.can_access_document", return_value=True):
        with patch("app.services.documents.crud.get_baseline_uploaded_version", return_value=None):
            with patch(
                "app.core.platform_cache.invalidate_document_caches"
            ):
                with patch(
                    "app.services.documents.crud.get_object_store"
                ) as get_store:
                    get_store.return_value.head_object_size.return_value = 100
                    crud.complete_upload(
                        db,
                        user,
                        document,
                        version,
                        file_size=100,
                        checksum="abc",
                    )

    assert called["git"] == 0


def test_complete_upload_rejects_missing_storage_object():
    from app.core.exceptions import AppError
    from app.services.documents import crud

    db = MagicMock()
    user = MagicMock(id=uuid.uuid4())
    document = MagicMock(id=uuid.uuid4(), current_version_id=None)
    version = MagicMock(
        id=uuid.uuid4(),
        document_id=document.id,
        file_name="a.pdf",
        mime_type="application/pdf",
        file_key="docs/x/v1/a.pdf",
    )

    with patch("app.services.documents.crud.can_access_document", return_value=True):
        with patch("app.services.documents.crud.get_baseline_uploaded_version", return_value=None):
            with patch(
                "app.services.documents.crud.get_object_store"
            ) as get_store:
                get_store.return_value.head_object_size.return_value = None
                try:
                    crud.complete_upload(
                        db,
                        user,
                        document,
                        version,
                        file_size=100,
                        checksum=None,
                    )
                except AppError as e:
                    assert "对象存储" in str(e)
                else:
                    raise AssertionError("expected AppError")
