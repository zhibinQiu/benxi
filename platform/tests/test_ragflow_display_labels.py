"""知识库展示名（部门名/用户名）。"""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock

from app.services.ragflow_naming import (
    dataset_display_label_dept,
    dataset_display_label_personal,
    dataset_name_for_dept,
    dataset_name_for_personal,
)


def test_dataset_names_include_human_slug_when_db_provided():
    db = MagicMock()
    dept_id = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
    user_id = uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
    from app.models.org import Department, User

    dept = MagicMock()
    dept.name = "研发中心"
    user = MagicMock()
    user.username = "zhangsan"

    def get_mock(model, pk):
        if model is Department and pk == dept_id:
            return dept
        if model is User and pk == user_id:
            return user
        return None

    db.get.side_effect = get_mock

    dept_name = dataset_name_for_dept(dept_id, db)
    personal_name = dataset_name_for_personal(user_id, db)
    assert "研发中心" in dept_name
    assert "zhangsan" in personal_name
    assert dataset_display_label_dept(db, dept_id) == "部门·研发中心"
    assert dataset_display_label_personal(db, user_id) == "个人·zhangsan"
