"""文档库部门列表：系统管理员可见全部部门。"""

import uuid
from unittest.mock import MagicMock, patch

from app.core.document_scope import library_departments_for_user


def test_superuser_gets_all_departments():
    db = MagicMock()
    d1 = MagicMock(id=uuid.uuid4())
    d1.name = "研发部"
    d2 = MagicMock(id=uuid.uuid4())
    d2.name = "市场部"
    db.scalars.return_value.all.return_value = [d1, d2]
    user = MagicMock()
    with patch("app.core.document_scope.user_is_superuser", return_value=True):
        rows = library_departments_for_user(db, user)
    assert len(rows) == 2
    assert rows[0]["name"] == "研发部"


def test_member_only_own_department():
    db = MagicMock()
    dept_id = uuid.uuid4()
    dept = MagicMock(id=dept_id, name="研发部")
    user = MagicMock(id=uuid.uuid4())
    with patch("app.core.document_scope.user_is_superuser", return_value=False), patch(
        "app.core.document_scope.user_dept_ids", return_value=[dept_id]
    ):
        db.get.return_value = dept
        rows = library_departments_for_user(db, user)
    assert len(rows) == 1
    assert rows[0]["id"] == dept_id
