"""文档禁止访问权限。"""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

from app.core.document_scope import can_manage_document_denials, is_access_denied


def test_is_access_denied():
    db = MagicMock()
    user = MagicMock(id=uuid.uuid4())
    doc = MagicMock(id=uuid.uuid4())
    db.scalar.return_value = 1
    assert is_access_denied(db, user, doc)


def test_only_owner_can_deny_dept_doc():
    db = MagicMock()
    owner = uuid.uuid4()
    other = MagicMock(id=uuid.uuid4())
    doc = MagicMock(
        deleted_at=None,
        owner_id=owner,
        scope="department",
        dept_id=uuid.uuid4(),
    )

    with patch("app.core.document_scope.user_is_superuser", return_value=False):
        assert can_manage_document_denials(db, MagicMock(id=owner), doc)
        assert not can_manage_document_denials(db, other, doc)
