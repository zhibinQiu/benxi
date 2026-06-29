"""AIP SK 认证与管理测试。"""

from __future__ import annotations

import pytest
from sqlalchemy import select

from app.core.aip.auth import generate_aip_sk, hash_aip_sk, is_aip_sk_token
from app.database import SessionLocal
from app.models.aip_secret_key import AipSecretKey
from app.models.org import User
from app.services.aip_secret_key_service import (
    authenticate_secret_key,
    create_secret_key,
    delete_secret_key,
    list_secret_keys,
)


@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def test_is_aip_sk_token():
    full, _, _ = generate_aip_sk()
    assert is_aip_sk_token(full)
    assert not is_aip_sk_token("sk-other")
    assert not is_aip_sk_token("Bearer jwt")


def test_create_list_delete_sk(db):
    user = db.scalar(select(User).limit(1))
    assert user is not None
    created = create_secret_key(db, user, purpose="集成测试密钥")
    assert created.secret_key.startswith("sk-aip-")
    assert created.purpose == "集成测试密钥"
    listed = list_secret_keys(db)
    assert any(item.id == created.id for item in listed)
    row, authed_user = authenticate_secret_key(db, created.secret_key)
    assert row.id == created.id
    assert authed_user.id == user.id
    delete_secret_key(db, created.id)
    assert db.get(AipSecretKey, created.id) is None


def test_authenticate_rejects_invalid(db):
    from app.core.exceptions import AppError

    with pytest.raises(AppError):
        authenticate_secret_key(db, "sk-aip-invalid-token")
