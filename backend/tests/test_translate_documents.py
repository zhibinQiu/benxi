"""Translate document library integration tests."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from app.core.permissions import PermissionLevel
from app.models.document import Document, DocumentStatus


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_list_translatable_documents_requires_auth(client):
    r = client.get("/api/v1/translate/documents")
    assert r.status_code == 401


def test_list_translatable_documents_ok(client, admin_token):
    r = client.get("/api/v1/translate/documents", headers=_auth(admin_token))
    assert r.status_code == 200
    data = r.json()["data"]
    assert "items" in data
    assert "total" in data


def test_list_translatable_excludes_deleted():
    from app.services.document_service import list_translatable_documents

    db = MagicMock()
    user = MagicMock()
    active = Document(
        id=uuid.uuid4(),
        title="正常",
        owner_id=uuid.uuid4(),
        scope="personal",
        status=DocumentStatus.active.value,
        current_version_id=uuid.uuid4(),
    )
    deleted = Document(
        id=uuid.uuid4(),
        title="已删除",
        owner_id=uuid.uuid4(),
        scope="personal",
        status=DocumentStatus.active.value,
        deleted_at=datetime.now(timezone.utc),
    )
    db.scalars.return_value.all.return_value = [active, deleted]
    version = MagicMock()
    version.file_name = "a.pdf"
    version.mime_type = "application/pdf"
    db.get.return_value = version

    with patch(
        "app.services.document_service.can_access_document", return_value=True
    ), patch(
        "app.core.document_scope.owner_qualifies_for_scope_list",
        return_value=True,
    ):
        rows, _ = list_translatable_documents(db, user, page=1, page_size=50)
    assert all(d.id != deleted.id for d, _ in rows)


def test_list_translatable_requires_query_not_only_visible():
    from app.services.document_service import list_translatable_documents

    db = MagicMock()
    user = MagicMock()
    doc = Document(
        id=uuid.uuid4(),
        title="仅可见",
        owner_id=uuid.uuid4(),
        scope="personal",
        status=DocumentStatus.active.value,
        current_version_id=uuid.uuid4(),
    )
    db.scalars.return_value.all.return_value = [doc]
    db.get.return_value = MagicMock(file_name="a.pdf", mime_type="application/pdf")

    with patch(
        "app.services.document_service.can_access_document",
        return_value=False,
    ), patch(
        "app.core.document_scope.owner_qualifies_for_scope_list",
        return_value=True,
    ):
        rows, _ = list_translatable_documents(db, user, page=1, page_size=50)
    assert rows == []


def test_create_job_requires_source(client, admin_token):
    r = client.post(
        "/api/v1/translate/jobs",
        headers=_auth(admin_token),
        data={"lang_in": "en", "lang_out": "zh-CN", "service": "siliconflow"},
    )
    assert r.status_code == 400


def test_create_job_rejects_unknown_document(client, admin_token):
    r = client.post(
        "/api/v1/translate/jobs",
        headers=_auth(admin_token),
        data={
            "document_id": str(uuid.uuid4()),
            "lang_in": "en",
            "lang_out": "zh-CN",
            "service": "siliconflow",
        },
    )
    assert r.status_code in (400, 404)
