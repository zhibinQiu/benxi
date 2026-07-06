"""AI 智能体临时附件。"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.database import SessionLocal
from app.models.org import User
from app.services.ai_chat_attachment_service import build_attachment_context
from app.services.ai_chat_service import _resolve_attachment_context


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(autouse=True)
def _attachment_storage_tmp(tmp_path, monkeypatch):
    root = tmp_path / "ai-chat-attachments"
    monkeypatch.setenv("AI_CHAT_ATTACHMENT_STORAGE_DIR", str(root))
    from app.config import get_settings

    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_ai_chat_attachment_upload_requires_auth(client: TestClient):
    r = client.post(
        "/api/v1/ai-chat/attachments/upload",
        files=[("files", ("note.txt", b"hello attachment", "text/plain"))],
    )
    assert r.status_code == 401


def test_ai_chat_attachment_upload_extracts_text(client: TestClient, admin_token: str):
    r = client.post(
        "/api/v1/ai-chat/attachments/upload",
        headers=_auth(admin_token),
        files=[("files", ("note.txt", "临时附件正文\n第二段".encode(), "text/plain"))],
    )
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["attachment_session_id"]
    assert len(data["files"]) == 1
    assert data["files"][0]["file_name"] == "note.txt"
    assert data["files"][0]["char_count"] > 0

    session_id = data["attachment_session_id"]
    r2 = client.get(
        f"/api/v1/ai-chat/attachments/{session_id}",
        headers=_auth(admin_token),
    )
    assert r2.status_code == 200
    assert len(r2.json()["data"]["files"]) == 1


def test_ai_chat_attachment_multi_upload_and_remove(client: TestClient, admin_token: str):
    r = client.post(
        "/api/v1/ai-chat/attachments/upload",
        headers=_auth(admin_token),
        files=[
            ("files", ("a.txt", "文档A内容".encode(), "text/plain")),
            ("files", ("b.txt", "文档B内容".encode(), "text/plain")),
        ],
    )
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["total_files"] == 2
    session_id = data["attachment_session_id"]
    file_id = data["files"][0]["file_id"]

    r2 = client.delete(
        f"/api/v1/ai-chat/attachments/{session_id}/files/{file_id}",
        headers=_auth(admin_token),
    )
    assert r2.status_code == 200
    assert len(r2.json()["data"]["files"]) == 1

    r3 = client.delete(
        f"/api/v1/ai-chat/attachments/{session_id}",
        headers=_auth(admin_token),
    )
    assert r3.status_code == 200


def test_build_attachment_context_includes_files():
    ctx = build_attachment_context(
        [
            {"file_name": "a.txt", "full_text": "左侧文档"},
            {"file_name": "b.txt", "full_text": "右侧文档"},
        ]
    )
    assert "附件 1" in ctx
    assert "附件 2" in ctx
    assert "左侧文档" in ctx
    assert "差异" in ctx


def test_resolve_attachment_context_from_upload(client: TestClient, admin_token: str):
    r = client.post(
        "/api/v1/ai-chat/attachments/upload",
        headers=_auth(admin_token),
        files=[("files", ("policy.txt", "碳配额发放细则".encode(), "text/plain"))],
    )
    session_id = r.json()["data"]["attachment_session_id"]

    with SessionLocal() as db:
        user = db.query(User).filter(User.username == "admin").first()
        assert user is not None
        ctx, count = _resolve_attachment_context(db, user, session_id)
        assert count == 1
        assert "碳配额发放细则" in ctx
