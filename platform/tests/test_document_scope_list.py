"""公司/部门库列表仅展示分级管理员上传的文档。"""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

from app.core.document_scope import (
    SCOPE_COMPANY,
    SCOPE_DEPARTMENT,
    owner_qualifies_for_scope_list,
)


def _doc(scope, owner_id, dept_id=None):
    return MagicMock(scope=scope, owner_id=owner_id, dept_id=dept_id)


def test_company_list_only_company_admin_uploader():
    db = MagicMock()
    admin = MagicMock(id=uuid.uuid4())
    member = MagicMock(id=uuid.uuid4())
    doc_ok = _doc(SCOPE_COMPANY, admin.id)
    doc_bad = _doc(SCOPE_COMPANY, member.id)

    with patch(
        "app.core.document_scope.user_is_company_admin",
        side_effect=lambda _db, u: u.id == admin.id,
    ):
        assert owner_qualifies_for_scope_list(db, doc_ok)
        assert not owner_qualifies_for_scope_list(db, doc_bad)


def test_dept_list_only_dept_admin_in_same_dept():
    db = MagicMock()
    dept = uuid.uuid4()
    admin = MagicMock(id=uuid.uuid4())
    doc_ok = _doc(SCOPE_DEPARTMENT, admin.id, dept)
    doc_bad = _doc(SCOPE_DEPARTMENT, uuid.uuid4(), dept)

    with patch("app.core.document_scope.user_is_dept_admin", return_value=True), patch(
        "app.core.document_scope.user_dept_ids",
        side_effect=lambda _db, uid: [dept] if uid == admin.id else [],
    ):
        assert owner_qualifies_for_scope_list(db, doc_ok)
        assert not owner_qualifies_for_scope_list(db, doc_bad)
