"""文档库部门列表：系统管理员可见全部部门；分部成员可见上级部门。"""

import uuid
from unittest.mock import MagicMock, patch

from app.core.document_scope import (
    department_id_at_depth,
    department_id_for_scope,
    library_departments_for_user,
)


def _chain_db(depts: dict[uuid.UUID, MagicMock]) -> MagicMock:
    db = MagicMock()

    def get(_model, dept_id):
        return depts.get(dept_id)

    db.get.side_effect = get
    return db


def test_superuser_gets_all_departments():
    db = MagicMock()
    d1 = MagicMock(id=uuid.uuid4())
    d1.name = "研发部"
    d2 = MagicMock(id=uuid.uuid4())
    d2.name = "市场部"
    db.scalars.return_value.all.return_value = [d1, d2]
    user = MagicMock()
    with patch("app.core.document_scope.user_is_superuser", return_value=True), patch(
        "app.core.document_scope.department_depth", return_value=1
    ):
        rows = library_departments_for_user(db, user)
    assert len(rows) == 2
    assert rows[0]["name"] == "研发部"


def test_member_only_own_department():
    db = MagicMock()
    dept_id = uuid.uuid4()
    dept = MagicMock(id=dept_id, name="研发部", parent_id=None)
    user = MagicMock(id=uuid.uuid4())
    with patch("app.core.document_scope.user_is_superuser", return_value=False), patch(
        "app.core.document_scope.user_dept_ids", return_value=[dept_id]
    ), patch("app.core.document_scope.department_id_at_depth", return_value=dept_id):
        db.get.return_value = dept
        rows = library_departments_for_user(db, user)
    assert len(rows) == 1
    assert rows[0]["id"] == dept_id


def test_team_member_sees_parent_department():
    company_id = uuid.uuid4()
    dept_id = uuid.uuid4()
    team_id = uuid.uuid4()

    class Dept:
        def __init__(self, id, name, parent_id):
            self.id = id
            self.name = name
            self.parent_id = parent_id

    company = Dept(company_id, "公司", None)
    dept = Dept(dept_id, "研发部", company_id)
    team = Dept(team_id, "后端组", dept_id)
    db = _chain_db({company_id: company, dept_id: dept, team_id: team})
    user = MagicMock(id=uuid.uuid4())
    with patch("app.core.document_scope.user_is_superuser", return_value=False), patch(
        "app.core.document_scope.user_dept_ids", return_value=[team_id]
    ), patch(
        "app.core.document_scope.department_depth",
        side_effect=lambda _db, did: {company_id: 0, dept_id: 1, team_id: 2}[did],
    ):
        rows = library_departments_for_user(db, user)
    assert len(rows) == 1
    assert rows[0]["id"] == dept_id
    assert rows[0]["name"] == "研发部"


def test_department_id_at_depth_walks_up_to_parent():
    company_id = uuid.uuid4()
    dept_id = uuid.uuid4()
    team_id = uuid.uuid4()
    company = MagicMock(id=company_id, name="公司", parent_id=None)
    dept = MagicMock(id=dept_id, name="研发部", parent_id=company_id)
    team = MagicMock(id=team_id, name="后端组", parent_id=dept_id)
    db = _chain_db({company_id: company, dept_id: dept, team_id: team})
    with patch(
        "app.core.document_scope.department_depth",
        side_effect=lambda _db, did: {company_id: 0, dept_id: 1, team_id: 2}[did],
    ):
        assert department_id_at_depth(db, team_id, 1) == dept_id
        assert department_id_at_depth(db, team_id, 0) == company_id
        assert department_id_for_scope(db, team_id, "department") == dept_id
