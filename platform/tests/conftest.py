"""API test fixtures."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture(scope="session")
def client() -> TestClient:
    return TestClient(create_app())


@pytest.fixture(scope="session")
def admin_token(client: TestClient) -> str:
    r = client.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": "admin123"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    return body["data"]["access_token"]
