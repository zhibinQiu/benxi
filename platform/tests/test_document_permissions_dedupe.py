"""文档分享：每用户仅保留最高级别授权。"""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock

from app.core.permissions import PermissionLevel
from app.models.document import DocumentPermission
from app.services import document_service


def test_list_permissions_merges_user_rows_to_highest_level():
    db = MagicMock()
    uid = uuid.uuid4()
    doc_id = uuid.uuid4()
    low = DocumentPermission(
        id=uuid.uuid4(),
        document_id=doc_id,
        subject_type="user",
        subject_id=uid,
        level=PermissionLevel.visible.value,
        granted_by=uuid.uuid4(),
    )
    high = DocumentPermission(
        id=uuid.uuid4(),
        document_id=doc_id,
        subject_type="user",
        subject_id=uid,
        level=PermissionLevel.full.value,
        granted_by=uuid.uuid4(),
    )
    db.scalars.return_value.all.return_value = [low, high]
    db.scalars.side_effect = [
        MagicMock(all=MagicMock(return_value=[low, high])),
        MagicMock(all=MagicMock(return_value=[low])),
    ]

    result = document_service.list_document_permissions(db, doc_id)
    user_rows = [p for p in result if p.subject_type == "user"]
    assert len(user_rows) == 1
    assert user_rows[0].level == PermissionLevel.full.value
    assert db.delete.called


def test_list_document_shares_one_row_per_user():
    db = MagicMock()
    uid = uuid.uuid4()
    doc_id = uuid.uuid4()
    low = DocumentPermission(
        id=uuid.uuid4(),
        document_id=doc_id,
        subject_type="user",
        subject_id=uid,
        level=PermissionLevel.visible.value,
        granted_by=uuid.uuid4(),
    )
    high = DocumentPermission(
        id=uuid.uuid4(),
        document_id=doc_id,
        subject_type="user",
        subject_id=uid,
        level=PermissionLevel.full.value,
        granted_by=uuid.uuid4(),
    )
    user_mock = MagicMock()
    user_mock.id = uid
    user_mock.display_name = "张三"
    user_mock.username = "zhang"

    db.scalars.return_value.all.side_effect = [
        [low, high],
        [low],
        [user_mock],
    ]

    shares = document_service.list_document_shares(db, doc_id)
    assert len(shares) == 1
    assert shares[0]["user_id"] == uid
    assert shares[0]["level"] == PermissionLevel.full.value
    assert shares[0]["user_name"] == "张三"
