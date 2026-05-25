"""分享列表与默认可读规则。"""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

from app.core.document_scope import (
    SCOPE_COMPANY,
    SCOPE_DEPARTMENT,
    SCOPE_PERSONAL,
    can_read_document,
    readable_by_scope_default,
)
from app.models.document import Document


def _doc(*, scope: str, owner_id: uuid.UUID | None = None, dept_id: uuid.UUID | None = None):
    return Document(
        id=uuid.uuid4(),
        title="t",
        status="ready",
        scope=scope,
        owner_id=owner_id or uuid.uuid4(),
        dept_id=dept_id,
        deleted_at=None,
    )


def test_dept_member_needs_doc_read_for_default():
    db = MagicMock()
    user = MagicMock(id=uuid.uuid4())
    dept = uuid.uuid4()
    doc = _doc(scope=SCOPE_DEPARTMENT, dept_id=dept)

    with patch("app.core.document_scope.user_is_superuser", return_value=False), patch(
        "app.core.document_scope._has_explicit_permission", return_value=False
    ), patch("app.core.document_scope.is_access_denied", return_value=False), patch(
        "app.core.document_scope.user_dept_ids", return_value=[dept]
    ), patch(
        "app.core.document_scope.user_has_permission", return_value=False
    ):
        assert not can_read_document(db, user, doc)


def test_company_needs_doc_read():
    db = MagicMock()
    user = MagicMock(id=uuid.uuid4())
    doc = _doc(scope=SCOPE_COMPANY)

    with patch("app.core.document_scope.user_is_superuser", return_value=False), patch(
        "app.core.document_scope._has_explicit_permission", return_value=False
    ), patch("app.core.document_scope.is_access_denied", return_value=False), patch(
        "app.core.document_scope.user_has_permission", return_value=False
    ):
        assert not can_read_document(db, user, doc)


def test_explicit_grant_before_deny_check_order():
    """显式授权优先于禁止名单（can_read 先查 explicit）。"""
    db = MagicMock()
    user = MagicMock(id=uuid.uuid4())
    doc = _doc(scope=SCOPE_PERSONAL, owner_id=uuid.uuid4())

    with patch("app.core.document_scope.user_is_superuser", return_value=False), patch(
        "app.core.document_scope._has_explicit_permission", return_value=True
    ), patch("app.core.document_scope.is_access_denied", return_value=True):
        assert can_read_document(db, user, doc)


def test_readable_by_scope_default_personal_not_shared():
    db = MagicMock()
    user = MagicMock(id=uuid.uuid4())
    owner = uuid.uuid4()
    doc = _doc(scope=SCOPE_PERSONAL, owner_id=owner)

    with patch("app.core.document_scope.is_access_denied", return_value=False):
        assert not readable_by_scope_default(db, MagicMock(id=user.id), doc)
        assert readable_by_scope_default(db, MagicMock(id=owner), doc)
