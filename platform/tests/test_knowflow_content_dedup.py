"""内容 MD5 与 KnowFlow 索引复用。"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from sqlalchemy import select

from app.core.content_checksum import compute_md5_hex, normalize_checksum
from app.core.document_scope import SCOPE_COMPANY
from app.database import SessionLocal
from app.models.document import Document, DocumentVersion
from app.models.ragflow_document_version_link import RagflowDocumentVersionLink
from app.services.document_checksum_service import ensure_version_checksum
from app.services.ragflow_sync_service import sync_document_to_knowflow
from app.services.ragflow_version_link_service import (
    find_existing_knowflow_version_link_by_content,
    find_reusable_knowflow_version_link,
)


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


def test_find_inflight_knowflow_version_link_by_content(client, admin_token):
    headers = {"Authorization": f"Bearer {admin_token}"}
    content = b"%PDF-1.4 inflight dedup"
    digest = compute_md5_hex(content)

    r1 = client.post(
        "/api/v1/documents",
        headers=headers,
        json={"title": "inflight-a", "scope": "personal"},
    )
    r2 = client.post(
        "/api/v1/documents",
        headers=headers,
        json={"title": "inflight-b", "scope": "personal"},
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
                ragflow_document_id="rag-inflight-1",
                dataset_id="ds-personal-1",
                file_name="report.pdf",
                index_completed_at=None,
            )
        )
        db.commit()
        ver_b_id = ver_b.id

    with SessionLocal() as db:
        assert find_reusable_knowflow_version_link(
            db,
            dataset_id="ds-personal-1",
            checksum=digest,
            file_size=len(content),
            exclude_version_id=ver_b_id,
        ) is None
        hit = find_existing_knowflow_version_link_by_content(
            db,
            dataset_id="ds-personal-1",
            checksum=digest,
            file_size=len(content),
            exclude_version_id=ver_b_id,
            require_indexed=False,
        )
        assert hit is not None
        assert hit.ragflow_document_id == "rag-inflight-1"


def test_find_reusable_knowflow_version_link_ignores_file_name(client, admin_token):
    headers = {"Authorization": f"Bearer {admin_token}"}
    content = b"%PDF-1.4 dedup other name"
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
            file_key=f"docs/{doc_a}/v1/original.pdf",
            file_name="original.pdf",
            file_size=len(content),
            mime_type="application/pdf",
            checksum=digest,
            created_by=owner_id,
        )
        ver_b = DocumentVersion(
            document_id=uuid.UUID(doc_b),
            version_no=1,
            file_key=f"docs/{doc_b}/v1/renamed-copy.pdf",
            file_name="renamed-copy.pdf",
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
                ragflow_document_id="rag-existing-2",
                dataset_id="ds-personal-1",
                file_name="original.pdf",
                index_completed_at=datetime.now(timezone.utc),
            )
        )
        db.commit()
        ver_b_id = ver_b.id

    with SessionLocal() as db:
        hit = find_reusable_knowflow_version_link(
            db,
            dataset_id="ds-personal-1",
            file_name="renamed-copy.pdf",
            checksum=digest,
            exclude_version_id=ver_b_id,
        )
        assert hit is not None
        assert hit.ragflow_document_id == "rag-existing-2"


def test_build_knowflow_upload_from_block_text():
    from app.services.document_version_block_service import (
        build_knowflow_upload_from_block_text,
    )

    version = DocumentVersion(
        id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        version_no=1,
        file_key="k",
        file_name="scan.pdf",
        file_size=100,
        mime_type="application/pdf",
        created_by=uuid.uuid4(),
    )
    name, body, mime = build_knowflow_upload_from_block_text(
        version, "hello world from cached blocks", title="体检通知"
    )
    assert name.endswith(".md")
    assert mime == "text/markdown"
    assert b"cached blocks" in body


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


def test_find_reusable_cross_company_dataset():
    """公司级文档：同 MD5 不同文件名，跨知识库复用已有索引。"""
    content = b"%PDF-1.4 cross company dedup"
    digest = compute_md5_hex(content)
    owner_id = uuid.uuid4()
    doc_a_id = uuid.uuid4()
    doc_b_id = uuid.uuid4()
    ver_a_id = uuid.uuid4()
    ver_b_id = uuid.uuid4()

    db = MagicMock()
    doc_a = Document(
        id=doc_a_id,
        title="company-a",
        scope=SCOPE_COMPANY,
        owner_id=owner_id,
        status="active",
    )
    doc_b = Document(
        id=doc_b_id,
        title="company-b",
        scope=SCOPE_COMPANY,
        owner_id=owner_id,
        status="active",
    )
    link_a = RagflowDocumentVersionLink(
        platform_document_id=doc_a_id,
        platform_version_id=ver_a_id,
        version_no=1,
        platform_user_id=owner_id,
        ragflow_document_id="rag-company-canonical",
        dataset_id="ds-company-main",
        file_name="Q3A.pdf",
        index_completed_at=datetime.now(timezone.utc),
    )

    def _scalar(stmt):
        _ = stmt
        return None

    def _scalars(stmt):
        from app.services.ragflow_version_link_service import (
            find_reusable_knowflow_version_link_for_document as finder,
        )

        _ = finder
        return MagicMock(all=lambda: [link_a])

    db.scalar = _scalar
    db.scalars = _scalars
    db.get.side_effect = lambda model, pk: {
        doc_a_id: doc_a,
        doc_b_id: doc_b,
    }.get(pk)

    with patch(
        "app.services.ragflow_version_link_service.find_existing_knowflow_version_link_by_content",
        return_value=None,
    ):
        from app.services.ragflow_version_link_service import (
            find_reusable_knowflow_version_link_for_document,
        )

        hit = find_reusable_knowflow_version_link_for_document(
            db,
            document=doc_b,
            target_dataset_id="ds-company-alt",
            checksum=digest,
            file_size=len(content),
            exclude_version_id=ver_b_id,
            require_indexed=True,
        )
    assert hit is not None
    assert hit.ragflow_document_id == "rag-company-canonical"
