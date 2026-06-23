"""报告生成结果入库测试。"""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

from app.services.report_generation_service import import_report_to_library


def test_import_report_to_library_creates_document():
    db = MagicMock()
    user = MagicMock()
    user.id = uuid.uuid4()
    doc_id = uuid.uuid4()

    doc = MagicMock()
    doc.id = doc_id
    doc.title = "全国碳市场研究报告"

    with (
        patch(
            "app.integrations.markdown_docx_export.markdown_to_docx_bytes",
            return_value=b"docx",
        ),
        patch(
            "app.integrations.markdown_docx_export.build_docx_download_filename",
            return_value="全国碳市场研究报告.docx",
        ),
        patch("app.services.document_service.create_document", return_value=doc) as create_doc,
        patch("app.services.document_service.create_initial_uploaded_version") as create_ver,
        patch("app.domains.knowledge.gateway.knowledge") as knowledge,
        patch("app.services.document_service.resolve_current_version", return_value=MagicMock()),
        patch("app.core.platform_cache.invalidate_document_caches"),
    ):
        knowledge.enabled.return_value = True
        result = import_report_to_library(
            db,
            user,
            title="全国碳市场研究报告",
            markdown="## 摘要\n内容",
        )

    create_doc.assert_called_once()
    assert create_doc.call_args.kwargs["folder_id"] is None
    create_ver.assert_called_once()
    db.commit.assert_called_once()
    knowledge.enqueue_sync_after_ingest.assert_called_once_with(doc_id, user.id)
    assert result["document_id"] == doc_id
    assert result["knowflow_synced"] is True
    assert "未分类" in result["message"]
