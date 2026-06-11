"""文档中心与知识检索树对齐。"""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

from app.core.document_scope import SCOPE_COMPANY, SCOPE_TEAM
from app.services.document_library_align_service import (
    document_matches_dataset_link,
    document_matches_library_unit,
    expected_scope_for_document,
    folder_matches_document,
    repair_platform_library_data,
)


def test_expected_scope_uses_org_depth():
    db = MagicMock()
    dept_team = uuid.uuid4()
    with patch(
        "app.services.document_library_align_service.scope_for_department",
        return_value=SCOPE_TEAM,
    ):
        doc = MagicMock(dept_id=dept_team, scope=SCOPE_COMPANY)
        assert expected_scope_for_document(db, doc) == SCOPE_TEAM


def test_folder_matches_document_requires_same_scope_and_dept():
    db = MagicMock()
    dept = uuid.uuid4()
    doc = MagicMock(
        dept_id=dept,
        scope=SCOPE_TEAM,
        folder_id=uuid.uuid4(),
        owner_id=uuid.uuid4(),
    )
    folder = MagicMock(scope=SCOPE_COMPANY, dept_id=dept, owner_id=None)
    with patch(
        "app.services.document_library_align_service.expected_scope_for_document",
        return_value=SCOPE_TEAM,
    ), patch(
        "app.services.document_library_align_service.expected_scope_for_folder",
        return_value=SCOPE_COMPANY,
    ):
        assert not folder_matches_document(db, folder, doc)


def test_document_matches_library_unit_team():
    db = MagicMock()
    dept = uuid.uuid4()
    doc = MagicMock(
        deleted_at=None,
        status="active",
        dept_id=dept,
        scope=SCOPE_TEAM,
        owner_id=uuid.uuid4(),
    )
    with patch(
        "app.services.document_library_align_service.expected_scope_for_document",
        return_value=SCOPE_TEAM,
    ):
        assert document_matches_library_unit(
            db, doc, scope=SCOPE_TEAM, dept_id=dept
        )
        assert not document_matches_library_unit(
            db, doc, scope=SCOPE_COMPANY, dept_id=dept
        )


def test_document_matches_dataset_link_checks_registry_scope():
    db = MagicMock()
    doc = MagicMock(
        deleted_at=None,
        status="active",
        dept_id=uuid.uuid4(),
        scope=SCOPE_TEAM,
        owner_id=uuid.uuid4(),
    )
    reg = MagicMock(scope="company", scope_key=str(uuid.uuid4()))
    with patch(
        "app.services.ragflow_scope_service._registry_for_dataset_id",
        return_value=reg,
    ), patch(
        "app.services.document_library_align_service.document_matches_library_unit",
        return_value=False,
    ):
        assert not document_matches_dataset_link(db, doc, "ds-company")


def test_repair_returns_report_keys():
    db = MagicMock()
    db.scalar.return_value = None

    def _scalars_result(items):
        result = MagicMock()
        result.all.return_value = items
        return result

    db.scalars.side_effect = [
        _scalars_result([]),
        _scalars_result([]),
        _scalars_result([]),
    ]
    report = repair_platform_library_data(db)
    assert "documents_folder_cleared" in report
    assert "documents_scope_fixed" in report
