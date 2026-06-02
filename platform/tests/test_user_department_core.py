"""用户部门全局规则（core.user_department）。"""

from __future__ import annotations

import uuid

import pytest

from app.core.user_department import (
    SINGLE_DEPARTMENT_MESSAGE,
    validate_department_id_list,
)


def test_validate_department_id_list_accepts_zero_or_one():
    assert validate_department_id_list([]) == []
    one = uuid.uuid4()
    assert validate_department_id_list([one]) == [one]


def test_validate_department_id_list_rejects_multiple():
    with pytest.raises(ValueError, match=SINGLE_DEPARTMENT_MESSAGE):
        validate_department_id_list([uuid.uuid4(), uuid.uuid4()])
