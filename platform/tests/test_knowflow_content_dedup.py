"""内容 MD5 与 KnowFlow 索引复用。"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from sqlalchemy import select

from app.core.content_checksum import compute_md5_hex, normalize_checksum
from app.database import SessionLocal
from app.models.document import Document, DocumentVersion
from app.models.ragflow_document_version_link import RagflowDocumentVersionLink
from app.services.document_checksum_service import ensure_version_checksum
from app.services.ragflow_sync_service import sync_document_to_knowflow
from app.services.ragflow_version_link_service import find_reusable_knowflow_version_link


def test_compute_and_normalize_md5():
    data = b"hello knowflow dedup"
    digest = compute_md5_hex(data)
    assert len(digest) == 32
    assert normalize_checksum(f"MD5:{digest.upper()}") == digest


def test_find_reusable_knowflow_version_link(client, admin_token):
    headers = {"Authorization": f"Bearer {admin_token}"}
    content = b"%PDF-1.4 dedup test"
    digest = compute_md5_hex(content)

    r1 = client.post(
        "/api/v1/documents",
        headers=headers,
        json={"title": "dedup-a", "scope": "personal"},
    )
    r2 = client.post(
        "/api/v1/documents",
        headers=headers,
        json={"title": "dedup-b", "scope": "personal"},
    )
    doc_a = r1.json()["data"]["id"]
    doc_b = r2.json()["data"]["id"]

    with SessionLocal() as db:
        owner_id = db.scalar(
            select(Document.owner_id).where(Document.id == uuid.UUID(doc_a))
        )
        ver_a = DocumentVersion(
            document_id=uuid.UUID(doc_a),
            version_no=1,
            file_key=f"docs/{doc_a}/v1/report.pdf",
            file_name="report.pdf",
            file_size=len(content),
            mime_type="application/pdf",
            checksum=digest,
            created_by=owner_id,
        )
        ver_b = DocumentVersion(
            document_id=uuid.UUID(doc_b),
            version_no=1,
            file_key=f"docs/{doc_b}/v1/report.pdf",
            file_name="report.pdf",
            file_size=len(content),
            mime_type="application/pdf",
            checksum=digest,
            created_by=owner_id,
        )
        db.add(ver_a)
        db.add(ver_b)
        db.flush()
        db.add(
            RagflowDocumentVersionLink(
                platform_document_id=ver_a.document_id,
                platform_version_id=ver_a.id,
                version_no=1,
                platform_user_id=owner_id,
                ragflow_document_id="rag-existing-1",
                dataset_id="ds-personal-1",
                file_name="report.pdf",
                index_completed_at=datetime.now(timezone.utc),
            )
        )
        db.commit()
        ver_b_id = ver_b.id

    with SessionLocal() as db:
        hit = find_reusable_knowflow_version_link(
            db,
            dataset_id="ds-personal-1",
            file_name="report.pdf",
            checksum=digest,
            exclude_version_id=ver_b_id,
        )
        assert hit is not None
        assert hit.ragflow_document_id == "rag-existing-1"


def test_sync_reuses_existing_knowflow_index_without_upload(client, admin_token):
    headers = {"Authorization": f"Bearer {admin_token}"}
    digest = compute_md5_hex(b"reuse-me")

    r1 = client.post(
        "/api/v1/documents",
        headers=headers,
        json={"title": "source", "scope": "personal"},
    )
    r2 = client.post(
        "/api/v1/documents",
        headers=headers,
        json={"title": "duplicate", "scope": "personal"},
    )
    doc_a = uuid.UUID(r1.json()["data"]["id"])
    doc_b = uuid.UUID(r2.json()["data"]["id"])

    with SessionLocal() as db:
        owner_id = db.scalar(select(Document.owner_id).where(Document.id == doc_a))
        ver_a = DocumentVersion(
            document_id=doc_a,
            version_no=1,
            file_key=f"docs/{doc_a}/v1/same.pdf",
            file_name="same.pdf",
            file_size=10,
            mime_type="application/pdf",
            checksum=digest,
            created_by=owner_id,
        )
        ver_b = DocumentVersion(
            document_id=doc_b,
            version_no=1,
            file_key=f"docs/{doc_b}/v1/same.pdf",
            file_name="same.pdf",
            file_size=10,
            mime_type="application/pdf",
            checksum=digest,
            created_by=owner_id,
        )
        db.add(ver_a)
        db.add(ver_b)
        for doc, ver in ((doc_a, ver_a), (doc_b, ver_b)):
            d = db.get(Document, doc)
            d.current_version_id = ver.id
        db.flush()
        db.add(
            RagflowDocumentVersionLink(
                platform_document_id=doc_a,
                platform_version_id=ver_a.id,
                version_no=1,
                platform_user_id=owner_id,
                ragflow_document_id="rag-dedup-target",
                dataset_id="ds-dedup",
                file_name="same.pdf",
                index_completed_at=datetime.now(timezone.utc),
            )
        )
        db.commit()

    upload_mock = MagicMock(return_value=("should-not-upload", None))
    grants_mock = MagicMock(return_value=1)

    with patch(
        "app.services.ragflow_sync_service.get_knowflow_client_for_user"
    ) as get_kf, patch(
        "app.services.ragflow_sync_service.resolve_dataset_for_document",
        return_value="ds-dedup",
    ), patch(
        "app.services.ragflow_sync_service.sync_document_kb_grants",
        grants_mock,
    ), patch(
        "app.services.ragflow_sync_service._upload_with_fallback",
        upload_mock,
    ), patch(
        "app.services.ragflow_sync_service.prepare_dataset_for_upload",
    ):
        kf = MagicMock()
        kf.enabled.return_value = True
        get_kf.return_value = kf

        with SessionLocal() as db:
            doc = db.get(Document, doc_b)
            user = MagicMock(id=owner_id)
            rid = sync_document_to_knowflow(db, user, doc, force=True)
            db.commit()

    assert rid == "rag-dedup-target"
    upload_mock.assert_not_called()
    assert grants_mock.call_count >= 1

    with SessionLocal() as db:
        from app.services.ragflow_version_link_service import get_version_link_by_version_id

        ver_b = db.scalar(
            select(DocumentVersion).where(DocumentVersion.document_id == doc_b)
        )
        link = get_version_link_by_version_id(db, ver_b.id)
        assert link is not None
        assert link.ragflow_document_id == "rag-dedup-target"
        assert link.index_completed_at is not None


def test_ensure_version_checksum_reads_object_store():
    version = DocumentVersion(
        id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        version_no=1,
        file_key="k1",
        file_name="a.txt",
        file_size=4,
        mime_type="text/plain",
        checksum=None,
        created_by=uuid.uuid4(),
    )
    db = MagicMock()
    with patch(
        "app.services.document_checksum_service.get_object_store"
    ) as get_store:
        get_store.return_value.get_object_bytes.return_value = b"test"
        digest = ensure_version_checksum(db, version)
    assert digest == compute_md5_hex(b"test")
    assert version.checksum == digest
    db.flush.assert_called_once()
