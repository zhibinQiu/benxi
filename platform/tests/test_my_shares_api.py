"""文档中心 · 我的分享列表。"""

from __future__ import annotations

import uuid

from sqlalchemy import select

from app.database import SessionLocal
from app.models.document import Document, DocumentPermission, DocumentVersion
from app.models.org import User


def test_my_shares_lists_shared_documents(client, admin_token):
    db = SessionLocal()
    try:
        owner = db.scalar(select(User).where(User.phone == "admin"))
        assert owner is not None
        other = User(
            id=uuid.uuid4(),
            username=f"share-target-{uuid.uuid4().hex[:6]}",
            display_name="分享对象",
            phone=f"139{uuid.uuid4().int % 10**8:08d}",
            password_hash="x",
            status="active",
        )
        db.add(other)
        doc = Document(
            id=uuid.uuid4(),
            title=f"share-out-{uuid.uuid4().hex[:6]}",
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
                subject_id=other.id,
                level="read",
                granted_by=owner.id,
            )
        )
        db.commit()
        doc_id = str(doc.id)
    finally:
        db.close()

    r = client.get(
        "/api/v1/documents/my-shares",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert r.status_code == 200, r.text
    items = r.json()["data"]["items"]
    assert any(i["id"] == doc_id for i in items)
    hit = next(i for i in items if i["id"] == doc_id)
    assert hit.get("share_count", 0) >= 1
    assert hit.get("share_to_summary")
