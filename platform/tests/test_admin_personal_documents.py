"""系统管理员查看他人个人文档库。"""

from __future__ import annotations

import uuid

from sqlalchemy import select

from app.database import SessionLocal
from app.models.document import Document, DocumentVersion
from app.models.org import User


def test_admin_lists_other_user_personal_documents(client, admin_token):
    db = SessionLocal()
    try:
        admin = db.scalar(select(User).where(User.phone == "15963564658"))
        assert admin is not None
        other = User(
            id=uuid.uuid4(),
            username=f"member-{uuid.uuid4().hex[:6]}",
            display_name="其他成员",
            phone=f"138{uuid.uuid4().int % 10**8:08d}",
            password_hash="x",
            status="active",
        )
        db.add(other)
        db.flush()
        doc = Document(
            id=uuid.uuid4(),
            title=f"other-personal-{uuid.uuid4().hex[:6]}",
            scope="personal",
            owner_id=other.id,
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
            created_by=other.id,
        )
        db.add(version)
        doc.current_version_id = version.id
        db.commit()
        other_id = str(other.id)
        doc_id = str(doc.id)
    finally:
        db.close()

    headers = {"Authorization": f"Bearer {admin_token}"}

    lib = client.get("/api/v1/documents/library", headers=headers)
    assert lib.status_code == 200, lib.text
    owners = lib.json()["data"].get("personal_owners") or []
    assert any(o["id"] == other_id for o in owners)

    listed = client.get(
        "/api/v1/documents",
        params={
            "scope": "personal",
            "owner_id": other_id,
            "uncategorized": True,
            "page": 1,
            "page_size": 50,
        },
        headers=headers,
    )
    assert listed.status_code == 200, listed.text
    ids = [i["id"] for i in listed.json()["data"]["items"]]
    assert doc_id in ids

    folders = client.get(
        "/api/v1/documents/kb-folders",
        params={"scope": "personal", "owner_id": other_id},
        headers=headers,
    )
    assert folders.status_code == 200, folders.text
    uncategorized = next(
        i for i in folders.json()["data"]["items"] if i["kind"] == "uncategorized"
    )
    assert uncategorized["document_count"] >= 1
