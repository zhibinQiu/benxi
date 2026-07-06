"""文档范围校验：知识检索与对比场景。"""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

from app.core.exceptions import AppError
from app.services.compare_service import validate_document_scope


def test_validate_document_scope_repairs_missing_current_version_id():
    user = MagicMock()
    db = MagicMock()
    doc_id = uuid.uuid4()
    doc = MagicMock()
    doc.id = doc_id
    doc.deleted_at = None
    doc.title = "source"
    doc.current_version_id = None
    version = MagicMock()

    with patch(
        "app.services.compare_service.get_document",
        return_value=doc,
    ), patch(
        "app.services.compare_service.can_access_document",
        return_value=True,
    ), patch(
        "app.services.document_service.resolve_current_version",
        return_value=version,
    ) as resolve_mock:
        docs = validate_document_scope(db, user, [doc_id])

    assert docs == [doc]
    resolve_mock.assert_called_once_with(db, doc, repair=True)


def test_validate_document_scope_allows_index_only_without_local_file():
    user = MagicMock()
    db = MagicMock()
    doc_id = uuid.uuid4()
    doc = MagicMock()
    doc.id = doc_id
    doc.deleted_at = None
    doc.title = "source"
    doc.current_version_id = None

    with patch(
        "app.services.compare_service.get_document",
        return_value=doc,
    ), patch(
        "app.services.compare_service.can_access_document",
        return_value=True,
    ), patch(
        "app.services.document_service.resolve_current_version",
        return_value=None,
    ), patch(
        "app.services.document_index_service.enrich_document_index_meta",
        return_value={
            str(doc_id): {
                "knowledge_synced": True,
                "parse_status": "已索引",
            }
        },
    ):
        docs = validate_document_scope(
            db,
            user,
            [doc_id],
            allow_index_only=True,
        )

    assert docs == [doc]


def test_validate_document_scope_index_only_rejects_unindexed():
    user = MagicMock()
    db = MagicMock()
    doc_id = uuid.uuid4()
    doc = MagicMock()
    doc.id = doc_id
    doc.deleted_at = None
    doc.title = "source"
    doc.current_version_id = None

    with patch(
        "app.services.compare_service.get_document",
        return_value=doc,
    ), patch(
        "app.services.compare_service.can_access_document",
        return_value=True,
    ), patch(
        "app.services.document_service.resolve_current_version",
        return_value=None,
    ), patch(
        "app.services.document_index_service.enrich_document_index_meta",
        return_value={str(doc_id): {"knowledge_synced": False}},
    ):
        try:
            validate_document_scope(
                db,
                user,
                [doc_id],
                allow_index_only=True,
            )
        except AppError as exc:
            from app.core.user_messages import KNOWLEDGE_QA_DOC_UNAVAILABLE

            assert exc.detail["message"] == KNOWLEDGE_QA_DOC_UNAVAILABLE.format(
                title="source"
            )
        else:
            raise AssertionError("expected bad_request")


def test_validate_document_scope_omit_unready_skips_bad_docs():
    user = MagicMock()
    db = MagicMock()
    good_id = uuid.uuid4()
    bad_id = uuid.uuid4()
    good = MagicMock()
    good.id = good_id
    good.deleted_at = None
    good.title = "已索引文档"
    bad = MagicMock()
    bad.id = bad_id
    bad.deleted_at = None
    bad.title = "文件夹内文档"

    def _get_document(_db, did):
        return good if did == good_id else bad

    with patch(
        "app.services.compare_service.get_document",
        side_effect=_get_document,
    ), patch(
        "app.services.compare_service.can_access_document",
        return_value=True,
    ), patch(
        "app.services.document_service.resolve_current_version",
        return_value=None,
    ), patch(
        "app.services.document_index_service.enrich_document_index_meta",
        return_value={
            str(good_id): {"knowledge_synced": True, "parse_status": "已索引"},
            str(bad_id): {"knowledge_synced": False},
        },
    ):
        docs = validate_document_scope(
            db,
            user,
            [bad_id, good_id],
            min_count=1,
            max_count=20,
            allow_index_only=True,
            omit_unready=True,
        )

    assert docs == [good]
