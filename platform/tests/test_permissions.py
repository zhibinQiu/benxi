"""RBAC superuser tests."""

from __future__ import annotations

from sqlalchemy import select

from app.core.permissions import user_has_permission, user_is_superuser
from app.database import SessionLocal
from app.models.org import User


def test_admin_is_superuser():
    db = SessionLocal()
    try:
        user = db.scalar(select(User).where(User.username == "admin"))
        assert user is not None
        assert user_is_superuser(db, user)
        assert user_has_permission(db, user, "feature.translate")
        assert user_has_permission(db, user, "doc.grant")
    finally:
        db.close()
