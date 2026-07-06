"""KnowFlow 上传复用平台分块文本。"""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

from app.models.document import Document, DocumentVersion
from app.services.document_version_block_service import (
    load_version_full_text_from_blocks,
    resolve_knowflow_upload_from_version,
)


def test_resolve_knowflow_upload_pdf_uses_original_file():
    doc = Document(id=uuid.uuid4(), title="t", description="")
    version = DocumentVersion(
        id=uuid.uuid4(),
        document_id=doc.id,
        version_no=1,
        file_key="docs/x/v1/a.pdf",
        file_name="a.pdf",
        file_size=100,
        mime_type="application/pdf",
        created_by=uuid.uuid4(),
    )
    db = MagicMock()
    read_mock = MagicMock(return_value=b"%PDF-1.4 fake")

    with patch(
        "app.services.document_version_block_service.load_version_full_text_from_blocks",
        return_value="cached body text long enough for knowflow upload",
    ), patch(
        "app.integrations.html_document_export.normalize_file_for_knowflow_upload",
        return_value=("a.pdf", b"%PDF-1.4 fake", "application/pdf"),
    ):
        name, body, mime, from_blocks = resolve_knowflow_upload_from_version(
            db,
            doc,
            version,
            read_object_bytes=read_mock,
        )

    assert from_blocks is False
    assert mime == "application/pdf"
    assert body.startswith(b"%PDF")
    read_mock.assert_called_once()


def test_resolve_knowflow_upload_docx_uses_original_file():
    doc = Document(id=uuid.uuid4(), title="t", description="")
    version = DocumentVersion(
        id=uuid.uuid4(),
        document_id=doc.id,
        version_no=1,
        file_key="docs/x/v1/a.docx",
        file_name="a.docx",
        file_size=100,
        mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        created_by=uuid.uuid4(),
    )
    db = MagicMock()
    read_mock = MagicMock(return_value=b"PK fake docx")

    with patch(
        "app.services.document_version_block_service.load_version_full_text_from_blocks",
        return_value="cached body text long enough for knowflow upload",
    ), patch(
        "app.integrations.html_document_export.normalize_file_for_knowflow_upload",
        return_value=("a.docx", b"PK fake docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
    ):
        name, body, mime, from_blocks = resolve_knowflow_upload_from_version(
            db,
            doc,
            version,
            read_object_bytes=read_mock,
        )

    assert from_blocks is False
    assert name == "a.docx"
    read_mock.assert_called_once()


def test_resolve_knowflow_upload_unknown_type_uses_blocks_without_reading_object():
    doc = Document(id=uuid.uuid4(), title="t", description="")
    version = DocumentVersion(
        id=uuid.uuid4(),
        document_id=doc.id,
        version_no=1,
        file_key="docs/x/v1/a.bin",
        file_name="a.bin",
        file_size=100,
        mime_type="application/octet-stream",
        created_by=uuid.uuid4(),
    )
    db = MagicMock()
    read_mock = MagicMock(side_effect=AssertionError("should not read MinIO"))

    with patch(
        "app.services.document_version_block_service.load_version_full_text_from_blocks",
        side_effect=["", "cached body text long enough for knowflow upload"],
    ), patch(
        "app.services.document_version_block_service.ensure_version_blocks",
        return_value=[MagicMock()],
    ):
        name, body, mime, from_blocks = resolve_knowflow_upload_from_version(
            db,
            doc,
            version,
            read_object_bytes=read_mock,
        )

    assert from_blocks is True
    assert mime == "application/pdf"
    assert body.startswith(b"%PDF")
    read_mock.assert_not_called()


def test_load_version_full_text_from_blocks_queries_text_only():
    db = MagicMock()
    db.scalars.return_value.all.return_value = [
        "line one with enough content",
        "line two with enough content",
    ]
    text = load_version_full_text_from_blocks(db, uuid.uuid4())
    assert "line one" in text
    assert "line two" in text
