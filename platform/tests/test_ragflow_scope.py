"""分级知识库：单库共享 + 平台 ACL 映射。"""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import pytest

from app.core.document_scope import SCOPE_COMPANY, SCOPE_DEPARTMENT, SCOPE_PERSONAL
from app.services.ragflow_naming import (
    dataset_name_for_company,
    dataset_name_for_dept,
    dataset_name_for_personal,
)
from app.services.ragflow_scope_service import (
    COMPANY_SCOPE_KEY,
    scope_key_for_document,
)


def test_dataset_names_by_scope():
    uid = uuid.UUID("caf46c9d-81cd-4faa-a20b-285c7ed0fe54")
    did = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
    assert dataset_name_for_company() == "公司"
    assert dataset_name_for_personal(uid).startswith("zt-personal-")
    assert dataset_name_for_dept(did).startswith("zt-dept-")


def test_scope_key_for_document():
    owner = uuid.uuid4()
    dept = uuid.uuid4()
    db = MagicMock()

    company = MagicMock(dept_id=None, owner_id=owner, scope=SCOPE_COMPANY)
    assert scope_key_for_document(db, company) == COMPANY_SCOPE_KEY

    dept_doc = MagicMock(dept_id=dept, owner_id=owner, scope=SCOPE_DEPARTMENT)
    assert scope_key_for_document(db, dept_doc) == str(dept)

    personal = MagicMock(dept_id=None, owner_id=owner, scope=SCOPE_PERSONAL)
    assert scope_key_for_document(db, personal) == str(owner)


def test_kb_level_maps_delete_to_admin():
    from app.services.ragflow_scope_service import kb_level_for_user_on_document

    db = MagicMock()
    user = MagicMock()
    doc = MagicMock()
    with patch(
        "app.services.ragflow_scope_service.can_query_document", return_value=True
    ), patch(
        "app.services.ragflow_scope_service.can_delete_document", return_value=True
    ):
        assert kb_level_for_user_on_document(db, user, doc) == "admin"
