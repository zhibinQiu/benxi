"""Compare service: prefer cached version blocks over live extraction."""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

from app.integrations.text_extract import ParsedDocument
from app.services.compare_service import (
    _load_cached_parsed_version,
    load_parsed_documents,
    load_parsed_version,
)


def test_load_cached_parsed_version_reads_blocks_only():
    version = MagicMock()
    version.id = uuid.uuid4()
    version.document_id = uuid.uuid4()
    version.file_name = "scan.pdf"

    block = MagicMock()
    payload = {
        "full_text": "OCR 缓存正文",
        "pages": [{"page": 1, "text": "OCR 缓存正文", "blocks": []}],
        "parse_quality": "ocr",
    }

    with (
        patch(
            "app.services.document_version_block_service.load_version_blocks",
            return_value=[block],
        ),
        patch(
            "app.services.document_version_block_service.blocks_to_content_dict",
            return_value=payload,
        ),
    ):
        parsed = _load_cached_parsed_version(MagicMock(), version)

    assert parsed is not None
    assert parsed.full_text == "OCR 缓存正文"
    assert parsed.parse_quality == "ocr"


def test_load_parsed_version_prefers_cached_blocks():
    version = MagicMock()
    version.id = uuid.uuid4()
    version.document_id = uuid.uuid4()
    version.file_name = "a.pdf"
    version.file_key = "k"
    version.mime_type = "application/pdf"

    cached = ParsedDocument(
        document_id=version.document_id,
        file_name=version.file_name,
        full_text="from blocks",
        pages=[],
        parse_quality="ocr",
    )

    with (
        patch(
            "app.services.compare_service._load_cached_parsed_version",
            return_value=cached,
        ),
        patch(
            "app.services.document_version_block_service.ensure_version_blocks",
        ) as ensure_blocks,
        patch("app.services.compare_service.get_object_store") as store,
    ):
        result = load_parsed_version(MagicMock(), version)

    assert result.full_text == "from blocks"
    ensure_blocks.assert_not_called()
    store.assert_not_called()


def test_load_parsed_documents_delegates_to_load_parsed_version():
    doc_id = uuid.uuid4()
    doc = MagicMock(id=doc_id)
    version = MagicMock()
    parsed = ParsedDocument(
        document_id=doc_id,
        file_name="b.docx",
        full_text="cached",
        pages=[],
        parse_quality="blocks",
    )

    with (
        patch(
            "app.services.document_service.resolve_current_version",
            return_value=version,
        ),
        patch(
            "app.services.compare_service.load_parsed_version",
            return_value=parsed,
        ) as load_version,
    ):
        rows = load_parsed_documents(MagicMock(), [doc])

    assert len(rows) == 1
    assert rows[0].full_text == "cached"
    load_version.assert_called_once()
