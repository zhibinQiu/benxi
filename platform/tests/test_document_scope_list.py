"""公司/部门库列表展示已发布到该分级的文档。"""

import uuid
from unittest.mock import MagicMock

from app.core.document_scope import owner_qualifies_for_scope_list


def test_company_list_any_published_doc():
    db = MagicMock()
    doc = MagicMock(scope="company", dept_id=None, owner_id=uuid.uuid4())
    assert owner_qualifies_for_scope_list(db, doc)


def test_dept_list_requires_dept_id():
    db = MagicMock()
    doc_ok = MagicMock(scope="department", dept_id=uuid.uuid4(), owner_id=uuid.uuid4())
    doc_bad = MagicMock(scope="department", dept_id=None, owner_id=uuid.uuid4())
    assert owner_qualifies_for_scope_list(db, doc_ok)
    assert not owner_qualifies_for_scope_list(db, doc_bad)
