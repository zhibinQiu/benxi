"""API test fixtures."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture(scope="session", autouse=True)
def _ensure_version_compare_tables():
    from app.database import engine
    from app.schema_migrate import (
        ensure_document_version_change_description,
        ensure_kg_schema,
        ensure_user_auth_token_version_schema,
        ensure_version_compare_schema,
        ensure_version_compare_llm_summary_schema,
        ensure_document_version_blocks_schema,
    )

    ensure_document_version_change_description(engine)
    ensure_version_compare_schema(engine)
    ensure_version_compare_llm_summary_schema(engine)
    ensure_document_version_blocks_schema(engine)
    ensure_user_auth_token_version_schema(engine)
    ensure_kg_schema(engine)


@pytest.fixture(scope="session")
def client() -> TestClient:
    return TestClient(create_app())


@pytest.fixture(autouse=True)
def _document_git_repos_tmp(tmp_path, monkeypatch):
    root = tmp_path / "document-git-repos"
    monkeypatch.setenv("DOCUMENT_GIT_REPOS_ROOT", str(root))
    from app.config import get_settings

    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


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
    monkeypatch.setattr(
        "app.domains.knowledge.gateway.KnowledgeGateway.schedule_sync_after_ingest",
        staticmethod(lambda *args, **kwargs: None),
    )
    yield


@pytest.fixture(scope="session")
def admin_token(client: TestClient) -> str:
    r = client.post(
        "/api/v1/auth/login",
        json={"account": "admin", "password": "admin123"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    return body["data"]["access_token"]
