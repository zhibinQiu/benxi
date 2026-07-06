"""三档文档显式授权：可见 / 可查 / 可修改。"""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

from app.core.document_scope import (
    SCOPE_DEPARTMENT,
    SCOPE_PERSONAL,
    SCOPE_TEAM,
    can_delete_document,
    can_edit_document,
    can_modify_document,
    can_query_document,
    can_read_document,
    readable_by_scope_default,
)
from app.core.permissions import (
    PermissionLevel,
    level_order,
    level_satisfies,
    normalize_permission_level,
)


def test_level_order_and_aliases():
    assert normalize_permission_level("read") == "visible"
    assert normalize_permission_level("use") == "modify"
    assert normalize_permission_level("edit") == "modify"
    assert normalize_permission_level("full") == "modify"
    assert normalize_permission_level("delete") == "modify"
    assert (
        level_order("visible")
        < level_order("query")
        < level_order("modify")
    )
    assert level_satisfies("modify", "query")
    assert not level_satisfies("visible", "modify")


def _doc(*, scope: str, owner_id: uuid.UUID | None = None, dept_id: uuid.UUID | None = None):
    return MagicMock(
        deleted_at=None,
        owner_id=owner_id or uuid.uuid4(),
        scope=scope,
        dept_id=dept_id,
        status="active",
    )


def test_explicit_query_without_modify():
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
    ), patch("app.core.document_scope.readable_by_scope_default", return_value=False), patch(
        "app.core.document_scope.can_read_document", return_value=True
    ):
        assert can_query_document(db, user, doc)
        assert not can_modify_document(db, user, doc)
        assert not can_edit_document(db, user, doc)
        assert not can_delete_document(db, user, doc)


def test_owner_personal_has_modify_capabilities():
    db = MagicMock()
    owner = uuid.uuid4()
    doc = _doc(scope=SCOPE_PERSONAL, owner_id=owner)
    user = MagicMock(id=owner)

    with patch("app.core.document_scope.user_is_superuser", return_value=False), patch(
        "app.core.document_scope._has_explicit_permission", return_value=False
    ), patch("app.core.document_scope.is_access_denied", return_value=False):
        assert can_read_document(db, user, doc)
        assert can_query_document(db, user, doc)
        assert can_modify_document(db, user, doc)
        assert can_edit_document(db, user, doc)
        assert can_delete_document(db, user, doc)


def test_team_scope_default_grants_modify():
    db = MagicMock()
    owner = uuid.uuid4()
    member = uuid.uuid4()
    dept = uuid.uuid4()
    doc = _doc(scope=SCOPE_TEAM, owner_id=owner, dept_id=dept)
    user = MagicMock(id=member)

    with patch(
        "app.core.document_scope.readable_by_scope_default", return_value=True
    ), patch("app.core.document_scope.user_is_superuser", return_value=False), patch(
        "app.core.document_scope._has_explicit_permission", return_value=False
    ), patch("app.core.document_scope.is_access_denied", return_value=False), patch(
        "app.core.document_scope.can_read_document", return_value=True
    ), patch("app.core.document_scope.can_edit_in_scope", return_value=False):
        assert can_modify_document(db, user, doc)
        assert can_query_document(db, user, doc)


def test_explicit_modify_grants_all_modify_ops():
    db = MagicMock()
    user = MagicMock(id=uuid.uuid4())
    doc = _doc(scope=SCOPE_DEPARTMENT, owner_id=uuid.uuid4())

    with patch(
        "app.core.document_scope._has_explicit_permission",
        side_effect=lambda _db, _u, _d, level: level == PermissionLevel.modify.value,
    ), patch("app.core.document_scope.user_is_superuser", return_value=False), patch(
        "app.core.document_scope.readable_by_scope_default", return_value=False
    ), patch("app.core.document_scope.is_access_denied", return_value=False), patch(
        "app.core.document_scope.can_edit_in_scope", return_value=False
    ), patch("app.core.document_scope.can_read_document", return_value=True):
        assert can_modify_document(db, user, doc)
        assert can_delete_document(db, user, doc)
