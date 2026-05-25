"""Compare direct search (no diff job required)."""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import pytest

from app.services.compare_service import search_compare_documents
from app.integrations.text_extract import ParsedDocument


@pytest.fixture
def mock_db():
    return MagicMock()


def test_search_compare_documents_local_fallback(mock_db):
    user = MagicMock()
    user.id = uuid.uuid4()
    doc_id = uuid.uuid4()
    parsed = ParsedDocument(
        document_id=doc_id,
        file_name="target.pdf",
        full_text="违约金条款 责任限制",
        pages=[{"page": 1, "text": "违约金条款 责任限制", "blocks": []}],
    )

    with (
        patch(
            "app.services.compare_service.validate_document_scope",
            return_value=[MagicMock(id=doc_id)],
        ),
        patch(
            "app.services.compare_service.load_parsed_documents",
            return_value=[parsed],
        ),
        patch(
            "app.services.compare_service._sync_ragflow_map",
            return_value={},
        ),
        patch(
            "app.services.compare_service.get_knowflow_client_for_user"
        ) as gkf,
        patch("app.services.compare_service.get_settings") as gs,
    ):
        kf = MagicMock()
        kf.enabled.return_value = False
        gkf.return_value = kf
        gs.return_value.knowflow_enabled = False

        hits = search_compare_documents(
            mock_db,
            user,
            right_document_id=doc_id,
            query="违约金",
            sync_knowflow=False,
        )

    assert hits
    assert hits[0]["snippet"]
    assert hits[0]["side"] == "right"
