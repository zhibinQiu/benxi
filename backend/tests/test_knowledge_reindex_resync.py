"""重新索引：已有 KnowFlow 副本时不因 dataset 探测失败强制 MinIO 重传。"""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

from app.services.knowledge_library_service import execute_document_reindex


def test_reindex_skips_full_sync_when_dataset_missing_but_knowflow_copy_exists():
    db = MagicMock()
    user = MagicMock()
    doc_id = uuid.uuid4()
    version_id = uuid.uuid4()

    doc = MagicMock(id=doc_id, deleted_at=None, title="体检通知")
    version = MagicMock(id=version_id, version_no=1)
    version_link = MagicMock(
        ragflow_document_id="rag-existing",
        dataset_id="ds-team",
        file_name="a.pdf",
        platform_user_id=uuid.uuid4(),
        parser_id="naive",
    )
    rag = MagicMock(health_ok=MagicMock(return_value=True))

    with patch(
        "app.services.knowledge_library_service.get_document",
        return_value=doc,
    ), patch(
        "app.services.ragflow_version_link_service.resolve_index_link",
        return_value=(version_link, version),
    ), patch(
        "app.services.ragflow_scope_service._dataset_exists_in_knowflow",
        return_value=False,
    ), patch(
        "app.services.ragflow_sync_service.sync_document_to_knowflow",
    ) as sync_mock, patch(
        "app.services.ragflow_version_link_service.clear_version_index_completed",
    ), patch(
        "app.services.knowledge_library_service._require_dataset_access",
    ), patch(
        "app.services.ragflow_sync_service._sync_context_for_document",
        return_value=(user, MagicMock()),
    ), patch(
        "app.services.ragflow_scope_service.prepare_dataset_for_upload",
    ), patch(
        "app.services.ragflow_sync_service._upload_rag_clients",
        return_value=[rag],
    ), patch(
        "app.services.knowledge_parser_service.build_parser_config",
        return_value=("smart", {"layout_recognize": "PaddleOCR"}),
    ), patch(
        "app.services.ragflow_version_link_service.upsert_version_link",
        return_value=version_link,
    ), patch(
        "app.core.platform_cache.invalidate_ragflow_doc_meta_cache",
    ):
        result = execute_document_reindex(
            db,
            user,
            doc_id,
            version_id=version_id,
            resync=False,
        )

    sync_mock.assert_not_called()
    rag.change_document_parser.assert_called_once()
    rag.parse_documents.assert_called_once()
    assert result["ragflow_document_id"] == "rag-existing"


def test_reindex_auto_resync_when_knowflow_copy_is_markdown():
    db = MagicMock()
    user = MagicMock()
    doc_id = uuid.uuid4()
    version_id = uuid.uuid4()

    doc = MagicMock(id=doc_id, deleted_at=None, title="体检通知")
    version = MagicMock(id=version_id, version_no=1)
    version_link = MagicMock(
        ragflow_document_id="rag-md",
        dataset_id="ds-team",
        file_name="通知.md",
        platform_user_id=uuid.uuid4(),
        parser_id="naive",
    )
    rag = MagicMock(health_ok=MagicMock(return_value=True))

    with patch(
        "app.services.knowledge_library_service.get_document",
        return_value=doc,
    ), patch(
        "app.services.ragflow_version_link_service.resolve_index_link",
        return_value=(version_link, version),
    ), patch(
        "app.services.ragflow_scope_service._dataset_exists_in_knowflow",
        return_value=True,
    ), patch(
        "app.services.ragflow_sync_service.sync_document_to_knowflow",
        return_value="rag-new-pdf",
    ) as sync_mock, patch(
        "app.services.ragflow_version_link_service.get_version_link_by_version_id",
        return_value=version_link,
    ), patch(
        "app.services.ragflow_version_link_service.clear_version_index_completed",
    ), patch(
        "app.services.knowledge_library_service._require_dataset_access",
    ), patch(
        "app.services.ragflow_sync_service._sync_context_for_document",
        return_value=(user, MagicMock()),
    ), patch(
        "app.services.ragflow_scope_service.prepare_dataset_for_upload",
    ), patch(
        "app.services.ragflow_sync_service._upload_rag_clients",
        return_value=[rag],
    ), patch(
        "app.services.knowledge_parser_service.build_parser_config",
        return_value=("smart", {"layout_recognize": "PaddleOCR"}),
    ), patch(
        "app.services.ragflow_version_link_service.upsert_version_link",
        return_value=version_link,
    ), patch(
        "app.core.platform_cache.invalidate_ragflow_doc_meta_cache",
    ):
        execute_document_reindex(
            db,
            user,
            doc_id,
            version_id=version_id,
            resync=False,
        )

    sync_mock.assert_called_once()
    assert sync_mock.call_args.kwargs.get("force") is True
