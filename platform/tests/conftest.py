"""API test fixtures."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture(scope="session")
def client() -> TestClient:
    return TestClient(create_app())


@pytest.fixture(autouse=True)
def _skip_knowflow_sync_on_upload(monkeypatch, request):
    """测试上传完成时不触发 KnowFlow（避免依赖对象存储中真实文件内容）。"""
    if request.module.__name__.endswith("test_knowledge_ingest_sync"):
        yield
        return
    monkeypatch.setattr(
        "app.domains.knowledge.gateway.KnowledgeGateway.sync_document_after_ingest",
        staticmethod(lambda *args, **kwargs: None),
    )
    yield


@pytest.fixture(scope="session")
def admin_token(client: TestClient) -> str:
    r = client.post(
        "/api/v1/auth/login",
        json={"account": "15963564658", "password": "admin123"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    return body["data"]["access_token"]
