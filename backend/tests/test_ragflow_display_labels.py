"""知识库展示名（部门名/用户名/公司）。"""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

from app.models.ragflow_scope_dataset import (
    SCOPE_COMPANY as REG_COMPANY,
    SCOPE_DEPARTMENT as REG_DEPARTMENT,
    SCOPE_PERSONAL as REG_PERSONAL,
)
from app.services.ragflow_naming import (
    dataset_display_label_company,
    dataset_display_label_dept,
    dataset_display_label_personal,
    dataset_name_for_company,
    dataset_name_for_dept,
    dataset_name_for_personal,
    dept_id_from_dataset_name,
    legacy_dataset_name_for_company,
    legacy_dataset_name_for_dept,
    legacy_dataset_name_for_personal,
)
from app.services.ragflow_scope_service import knowflow_kb_labels_for_user


def test_dataset_display_labels_plain_names():
    db = MagicMock()
    dept_id = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
    user_id = uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
    from app.models.org import Department, User

    dept = MagicMock()
    dept.name = "研发中心"
    user = MagicMock()
    user.username = "zhangsan"
    user.display_name = "张三"

    def get_mock(model, pk):
        if model is Department and pk == dept_id:
            return dept
        if model is User and pk == user_id:
            return user
        return None

    db.get.side_effect = get_mock

    assert dataset_display_label_dept(db, dept_id) == "研发中心"
    assert dataset_display_label_personal(db, user_id) == "张三"
    assert dataset_display_label_company() == "公司"
    assert dataset_name_for_company() == "公司"
    assert "张三" in dataset_name_for_personal(user_id, db)
    assert "研发中心" in dataset_name_for_dept(dept_id, db)
    assert "zt-personal" not in dataset_name_for_personal(user_id, db)
    assert legacy_dataset_name_for_personal(user_id).startswith("zt-personal-")
    assert legacy_dataset_name_for_dept(dept_id).startswith("zt-dept-")
    assert legacy_dataset_name_for_company() == "zt-company"


def test_knowflow_kb_labels_with_personal_include_legacy_aliases():
    db = MagicMock()
    dept_id = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
    user_id = uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
    from app.models.org import Department, User

    dept = MagicMock()
    dept.name = "研发中心"
    user = MagicMock()
    user.id = user_id
    user.username = "zhangsan"
    user.display_name = "张三"

    personal_reg = MagicMock(
        ragflow_dataset_id="ds-personal",
        scope=REG_PERSONAL,
        scope_key=str(user_id),
    )
    dept_reg = MagicMock(
        ragflow_dataset_id="ds-dept",
        scope=REG_DEPARTMENT,
        scope_key=str(dept_id),
    )
    company_reg = MagicMock(
        ragflow_dataset_id="ds-company",
        scope=REG_COMPANY,
        scope_key="global",
    )

    def get_mock(model, pk):
        if model is Department and pk == dept_id:
            return dept
        if model is User and pk == user_id:
            return user
        return None

    db.get.side_effect = get_mock

    with patch(
        "app.services.ragflow_scope_service.user_is_superuser",
        return_value=False,
    ), patch(
        "app.services.ragflow_scope_service._user_has_personal_kb",
        return_value=True,
    ), patch(
        "app.services.ragflow_scope_service._scope_registries_for_user",
        return_value=[personal_reg, dept_reg, company_reg],
    ), patch(
        "app.services.ragflow_scope_service.allowed_dataset_ids_for_user",
        return_value={"ds-personal", "ds-dept", "ds-company"},
    ):
        labels = knowflow_kb_labels_for_user(db, user)

    by_name = {item["name"]: item["label"] for item in labels}
    assert by_name[legacy_dataset_name_for_personal(user_id)] == "张三"
    assert by_name[legacy_dataset_name_for_dept(dept_id)] == "研发中心"
    assert by_name[legacy_dataset_name_for_company()] == "公司"


def test_knowflow_kb_labels_without_personal_excludes_personal_and_company():
    db = MagicMock()
    dept_id = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
    user_id = uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
    from app.models.org import Department, User

    dept = MagicMock()
    dept.name = "研发中心"
    user = MagicMock()
    user.id = user_id
    user.username = "zhangsan"
    user.display_name = "张三"

    dept_reg = MagicMock(
        ragflow_dataset_id="ds-dept",
        scope=REG_DEPARTMENT,
        scope_key=str(dept_id),
    )

    def get_mock(model, pk):
        if model is Department and pk == dept_id:
            return dept
        if model is User and pk == user_id:
            return user
        return None

    db.get.side_effect = get_mock

    with patch(
        "app.services.ragflow_scope_service.user_is_superuser",
        return_value=False,
    ), patch(
        "app.services.ragflow_scope_service._user_has_personal_kb",
        return_value=False,
    ), patch(
        "app.services.ragflow_scope_service._scope_registries_for_user",
        return_value=[dept_reg],
    ), patch(
        "app.services.ragflow_scope_service.allowed_dataset_ids_for_user",
        return_value={"ds-dept"},
    ):
        labels = knowflow_kb_labels_for_user(db, user)

    by_name = {item["name"]: item["label"] for item in labels}
    assert by_name[legacy_dataset_name_for_dept(dept_id)] == "研发中心"
    assert legacy_dataset_name_for_personal(user_id) not in by_name
    assert legacy_dataset_name_for_company() not in by_name


def test_dept_id_from_legacy_dataset_name():
    db = MagicMock()
    dept_id = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
    from app.models.org import Department

    dept = MagicMock()
    dept.id = dept_id
    dept.name = "研发中心"

    def get_mock(model, pk):
        if model is Department and pk == dept_id:
            return dept
        return None

    db.get.side_effect = get_mock
    db.scalars.return_value.all.return_value = [dept]

    legacy = legacy_dataset_name_for_dept(dept_id)
    assert dept_id_from_dataset_name(db, legacy) == dept_id
