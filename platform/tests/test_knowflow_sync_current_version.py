"""KnowFlow 同步应能处理 current_version_id 缺失的文档。"""

from unittest.mock import MagicMock, patch

from app.database import SessionLocal
from app.models.document import Document
from app.services.ragflow_sync_service import sync_document_to_knowflow
from tests.test_document_versions import _upload_dummy_pdf


def test_sync_document_uses_resolve_current_version(client, admin_token):
    headers = {"Authorization": f"Bearer {admin_token}"}
    r = client.post(
        "/api/v1/documents",
        headers=headers,
        json={"title": "kf-sync", "scope": "personal"},
    )
    doc_id = r.json()["data"]["id"]
    _upload_dummy_pdf(client, doc_id, headers)

    with SessionLocal() as db:
        doc = db.get(Document, doc_id)
        doc.current_version_id = None
        db.commit()

    with patch(
        "app.services.ragflow_sync_service.get_knowflow_client_for_user"
    ) as get_kf, patch(
        "app.services.ragflow_sync_service.resolve_dataset_for_document",
        return_value="ds-1",
    ), patch(
        "app.services.ragflow_sync_service.sync_document_kb_grants"
    ):
        kf = MagicMock()
        kf.enabled.return_value = True
        kf.sync_platform_document.return_value = "rag-doc-1"
        get_kf.return_value = kf

        with SessionLocal() as db:
            doc = db.get(Document, doc_id)
            rid = sync_document_to_knowflow(db, MagicMock(id=doc.owner_id), doc, force=True)
            db.commit()

    assert rid == "rag-doc-1"
    kf.sync_platform_document.assert_called_once()
    assert kf.sync_platform_document.call_args.kwargs["file_name"].endswith(".pdf")
