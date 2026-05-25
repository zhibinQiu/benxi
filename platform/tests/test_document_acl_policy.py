"""文档显式授权与禁止访问的权限边界。"""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

from app.core.document_scope import (
    SCOPE_COMPANY,
    SCOPE_DEPARTMENT,
    SCOPE_PERSONAL,
    can_grant_document_permissions,
    can_manage_document_denials,
)


def _doc(*, scope: str, owner_id: uuid.UUID | None = None, dept_id: uuid.UUID | None = None):
    d = MagicMock(deleted_at=None, owner_id=owner_id or uuid.uuid4(), scope=scope, dept_id=dept_id)
    return d


def test_only_owner_or_sysadmin_can_grant():
    db = MagicMock()
    owner = uuid.uuid4()
    other = uuid.uuid4()
    doc = _doc(scope=SCOPE_PERSONAL, owner_id=owner)

    with patch("app.core.document_scope.user_is_superuser", return_value=False):
        assert can_grant_document_permissions(db, MagicMock(id=owner), doc)
        assert not can_grant_document_permissions(db, MagicMock(id=other), doc)

    with patch("app.core.document_scope.user_is_superuser", return_value=True):
        assert can_grant_document_permissions(db, MagicMock(id=other), doc)


def test_dept_admin_can_deny_but_not_grant_dept_doc():
    db = MagicMock()
    owner = uuid.uuid4()
    admin = MagicMock(id=uuid.uuid4())
    dept = uuid.uuid4()
    doc = _doc(scope=SCOPE_DEPARTMENT, owner_id=owner, dept_id=dept)

    with patch("app.core.document_scope.user_is_superuser", return_value=False), patch(
        "app.core.document_scope.user_dept_ids", return_value=[dept]
    ), patch("app.core.document_scope.can_edit_in_scope", return_value=True):
        assert not can_grant_document_permissions(db, admin, doc)
        assert can_manage_document_denials(db, admin, doc)


def test_company_admin_can_deny_company_doc():
    db = MagicMock()
    doc = _doc(scope=SCOPE_COMPANY, owner_id=uuid.uuid4())
    admin = MagicMock(id=uuid.uuid4())

    with patch("app.core.document_scope.user_is_superuser", return_value=False), patch(
        "app.core.document_scope.can_edit_in_scope", return_value=True
    ) as edit:
        edit.side_effect = lambda _db, _u, scope: scope == SCOPE_COMPANY
        assert can_manage_document_denials(db, admin, doc)
        assert not can_grant_document_permissions(db, admin, doc)
