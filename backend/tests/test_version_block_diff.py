"""结构化分块 diff 与 OCR 块解析。"""

from __future__ import annotations

from app.integrations.paddleocr_client import extract_layout_blocks
from app.services.version_block_diff_service import compute_block_diffs


def test_extract_layout_blocks_rec_texts():
    raw = {"rec_texts": ["第一段", "第二段"], "rec_boxes": [[0, 0, 100, 20], [0, 30, 120, 50]]}
    blocks = extract_layout_blocks(raw)
    assert len(blocks) == 2
    assert blocks[0]["text"] == "第一段"
    assert blocks[0]["bbox"] == [0.0, 0.0, 100.0, 20.0]


def test_compute_block_diffs(admin_token):
    from sqlalchemy import select

    from app.database import SessionLocal
    from app.models.org import User
    from app.services.documents.crud import (
        complete_upload,
        create_document,
        create_initial_uploaded_version,
        prepare_upload,
        save_upload_blob,
    )
    from app.services.document_version_block_service import ensure_version_blocks

    db = SessionLocal()
    try:
        user = db.scalar(select(User).limit(1))
        if not user:
            import pytest

            pytest.skip("no user")
        doc = create_document(db, user, title="block-diff", scope="personal")
        create_initial_uploaded_version(
            db,
            doc,
            user,
            file_name="a.txt",
            mime_type="text/plain",
            content=b"alpha block\n",
        )
        version, _url = prepare_upload(
            db, user, doc, file_name="a.txt", mime_type="text/plain"
        )
        save_upload_blob(
            db,
            user,
            doc,
            version,
            b"alpha block\nbeta block\n",
            content_type="text/plain",
        )
        complete_upload(
            db,
            user,
            doc,
            version,
            file_size=len(b"alpha block\nbeta block\n"),
            checksum=None,
        )
        db.refresh(doc)
        from sqlalchemy import select

        from app.models.document import DocumentVersion

        versions = list(
            db.scalars(
                select(DocumentVersion)
                .where(DocumentVersion.document_id == doc.id)
                .order_by(DocumentVersion.version_no.asc())
            ).all()
        )
        v1, v2 = versions[0], versions[-1]
        ensure_version_blocks(db, v1)
        ensure_version_blocks(db, v2)
        items, meta = compute_block_diffs(db, v1, v2)
        assert meta["engine"] == "block"
        assert len(items) >= 1
        assert items[0]["anchor_json"]["kind"] == "block"
        assert items[0]["anchor_json"].get("left") or items[0]["anchor_json"].get("right")
    finally:
        db.close()
