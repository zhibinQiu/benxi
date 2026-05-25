"""四档文档显式授权：可见 / 可查询 / 可编辑 / 完全。"""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

from app.core.document_scope import (
    SCOPE_DEPARTMENT,
    SCOPE_PERSONAL,
    can_delete_document,
    can_edit_document,
    can_manage_document,
    can_query_document,
    can_read_document,
)
from app.core.permissions import (
    PermissionLevel,
    level_order,
    level_satisfies,
    normalize_permission_level,
)


def test_level_order_and_aliases():
    assert normalize_permission_level("read") == "visible"
    assert normalize_permission_level("use") == "edit"
    assert normalize_permission_level("delete") == "full"
    assert level_order("visible") < level_order("query") < level_order("edit") < level_order("full")
    assert level_satisfies("full", "query")
    assert not level_satisfies("visible", "edit")


def _doc(*, scope: str, owner_id: uuid.UUID | None = None, dept_id: uuid.UUID | None = None):
    return MagicMock(
        deleted_at=None,
        owner_id=owner_id or uuid.uuid4(),
        scope=scope,
        dept_id=dept_id,
    )


def test_explicit_query_without_edit():
    db = MagicMock()
    user_id = uuid.uuid4()
    other = uuid.uuid4()
    doc = _doc(scope=SCOPE_PERSONAL, owner_id=other)
    user = MagicMock(id=user_id)

    with patch(
        "app.core.document_scope._has_explicit_permission",
        side_effect=lambda _db, _u, _d, level: level == PermissionLevel.query.value,
    ), patch("app.core.document_scope.user_is_superuser", return_value=False), patch(
        "app.core.document_scope.is_access_denied", return_value=False
    ), patch("app.core.document_scope.can_read_document", return_value=True):
        assert can_query_document(db, user, doc)
        assert not can_edit_document(db, user, doc)
        assert not can_delete_document(db, user, doc)


def test_can_manage_matches_owner_or_admin():
    db = MagicMock()
    owner = uuid.uuid4()
    doc = _doc(scope=SCOPE_PERSONAL, owner_id=owner)
    user = MagicMock(id=owner)

    with patch("app.core.document_scope.user_is_superuser", return_value=False), patch(
        "app.core.document_scope._has_explicit_permission", return_value=False
    ):
        from app.core.document_scope import can_manage_document

        assert can_manage_document(db, user, doc)


def test_owner_personal_has_full_capabilities():
    db = MagicMock()
    owner = uuid.uuid4()
    doc = _doc(scope=SCOPE_PERSONAL, owner_id=owner)
    user = MagicMock(id=owner)

    with patch("app.core.document_scope.user_is_superuser", return_value=False), patch(
        "app.core.document_scope._has_explicit_permission", return_value=False
    ), patch("app.core.document_scope.is_access_denied", return_value=False):
        assert can_read_document(db, user, doc)
        assert can_query_document(db, user, doc)
        assert can_edit_document(db, user, doc)
        assert can_delete_document(db, user, doc)


def test_explicit_edit_not_delete():
    db = MagicMock()
    user = MagicMock(id=uuid.uuid4())
    doc = _doc(scope=SCOPE_DEPARTMENT, owner_id=uuid.uuid4())

    with patch(
        "app.core.document_scope._has_explicit_permission",
        side_effect=lambda _db, _u, _d, level: level == PermissionLevel.edit.value,
    ), patch("app.core.document_scope.user_is_superuser", return_value=False), patch(
        "app.core.document_scope.can_read_document", return_value=True
    ), patch("app.core.document_scope.can_edit_in_scope", return_value=False), patch(
        "app.core.document_scope.can_delete_in_scope", return_value=False
    ):
        assert can_edit_document(db, user, doc)
        assert not can_delete_document(db, user, doc)
