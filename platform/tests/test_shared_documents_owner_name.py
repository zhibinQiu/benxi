"""分享文档列表应返回上传人姓名。"""

from __future__ import annotations

import uuid

from sqlalchemy import select

from app.api.documents.serializers import batch_owner_names, list_items_with_owners
from app.core.security import hash_password
from app.database import SessionLocal
from app.models.document import Document, DocumentPermission, DocumentVersion
from app.models.org import User
from app.services.documents import listing as document_listing


def test_batch_owner_names_uses_display_name_when_username_empty():
    db = SessionLocal()
    try:
        owner = User(
            id=uuid.uuid4(),
            username="",
            display_name="文档上传者",
            phone=f"136{uuid.uuid4().int % 10**8:08d}",
            email="owner@example.com",
            password_hash=hash_password("password123"),
            status="active",
        )
        db.add(owner)
        db.commit()
        names = batch_owner_names(db, {owner.id})
        assert names[owner.id] == "文档上传者"
    finally:
        db.close()


def test_shared_documents_list_includes_owner_name(client, admin_token):
    db = SessionLocal()
    try:
        owner = db.scalar(select(User).where(User.phone == "admin"))
        assert owner is not None
        owner_display = (owner.display_name or owner.username or owner.phone or owner.email or "").strip()
        assert owner_display

        recipient = User(
            id=uuid.uuid4(),
            username="",
            display_name="分享接收人",
            phone=f"137{uuid.uuid4().int % 10**8:08d}",
            email=f"recv-{uuid.uuid4().hex[:8]}@example.com",
            password_hash=hash_password("password123"),
            status="active",
        )
        db.add(recipient)
        doc = Document(
            id=uuid.uuid4(),
            title=f"shared-in-{uuid.uuid4().hex[:6]}",
            scope="personal",
            owner_id=owner.id,
            status="active",
        )
        db.add(doc)
        db.flush()
        version = DocumentVersion(
            id=uuid.uuid4(),
            document_id=doc.id,
            version_no=1,
            file_name="a.pdf",
            file_key=f"test/{doc.id}.pdf",
            mime_type="application/pdf",
            file_size=10,
            created_by=owner.id,
        )
        db.add(version)
        doc.current_version_id = version.id
        db.add(
            DocumentPermission(
                id=uuid.uuid4(),
                document_id=doc.id,
                subject_type="user",
                subject_id=recipient.id,
                level="read",
                granted_by=owner.id,
            )
        )
        db.commit()
        doc_id = doc.id
        recipient_id = recipient.id
    finally:
        db.close()

    db = SessionLocal()
    try:
        recipient = db.get(User, recipient_id)
        rows, _total = document_listing.list_shared_documents(
            db, recipient, page=1, page_size=50
        )
        docs = [d for d, _ in rows if d.id == doc_id]
        assert docs
        items = list_items_with_owners(db, docs, include_owner_name=True, user=recipient)
        assert items[0].owner_name == owner_display
    finally:
        db.close()
