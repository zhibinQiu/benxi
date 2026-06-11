"""文档版本结构化分块：OCR 解析、持久化与读取。"""

from __future__ import annotations

import logging
import uuid

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.integrations.paddleocr_client import recognize_bytes
from app.integrations.text_extract import ParsedDocument, extract_text_from_bytes
from app.models.document import DocumentVersion
from app.models.document_version_block import DocumentVersionBlock
from app.storage.object_store import get_object_store

logger = logging.getLogger(__name__)


def _blocks_to_pages(blocks: list[dict]) -> list[dict]:
    by_page: dict[int, list[dict]] = {}
    for blk in blocks:
        page = int(blk.get("page") or 1)
        by_page.setdefault(page, []).append(
            {
                "text": blk.get("text") or "",
                "bbox": blk.get("bbox"),
                "block_type": blk.get("block_type") or "text",
            }
        )
    pages: list[dict] = []
    for page_no in sorted(by_page.keys()):
        page_blocks = by_page[page_no]
        text = "\n\n".join(b["text"] for b in page_blocks if b["text"]).strip()
        pages.append({"page": page_no, "text": text, "blocks": page_blocks})
    return pages


def parse_version_document(
    db: Session | None,
    version: DocumentVersion,
    *,
    force_ocr: bool = False,
) -> ParsedDocument:
    """解析版本文件；必要时走 PaddleOCR 版面识别。"""
    store = get_object_store()
    data = store.get_object_bytes(version.file_key)
    parsed = extract_text_from_bytes(
        data,
        document_id=version.document_id,
        file_name=version.file_name,
        mime_type=version.mime_type,
    )

    need_ocr = force_ocr or parsed.parse_quality in ("ocr_required", "failed")
    if not need_ocr and len((parsed.full_text or "").strip()) < 32:
        need_ocr = True

    ocr_url = ""
    if need_ocr and db is not None:
        from app.services.model_settings_service import get_paddleocr_url

        ocr_url = (get_paddleocr_url(db) or "").strip()

    if need_ocr and ocr_url:
        try:
            ocr = recognize_bytes(
                data,
                service_url=ocr_url,
                file_name=version.file_name,
                mime_type=version.mime_type or "application/octet-stream",
            )
            blocks = ocr.get("blocks") or []
            if blocks:
                pages = _blocks_to_pages(blocks)
                full = "\n\n".join(p["text"] for p in pages if p.get("text")).strip()
                return ParsedDocument(
                    document_id=version.document_id,
                    file_name=version.file_name,
                    full_text=full or ocr.get("text") or "",
                    pages=pages,
                    parse_quality="ocr",
                    warning=None,
                )
            if ocr.get("text"):
                text = str(ocr["text"]).strip()
                return ParsedDocument(
                    document_id=version.document_id,
                    file_name=version.file_name,
                    full_text=text,
                    pages=[
                        {
                            "page": 1,
                            "text": text,
                            "blocks": [{"text": text, "bbox": None, "block_type": "ocr"}],
                        }
                    ],
                    parse_quality="ocr",
                )
        except Exception:
            logger.warning(
                "OCR 解析失败 doc=%s version=%s",
                version.document_id,
                version.id,
                exc_info=True,
            )
            if not parsed.full_text:
                parsed.warning = (parsed.warning or "") + " OCR 识别失败"

    return parsed


def _flatten_page_blocks(parsed: ParsedDocument) -> list[dict]:
    flat: list[dict] = []
    pages = parsed.pages or [{"page": 1, "text": parsed.full_text, "blocks": []}]
    for page in pages:
        page_no = int(page.get("page") or 1)
        blocks = page.get("blocks") or []
        if blocks:
            for blk in blocks:
                text = (blk.get("text") or "").strip()
                if not text:
                    continue
                flat.append(
                    {
                        "page": page_no,
                        "text": text,
                        "bbox": blk.get("bbox"),
                        "block_type": blk.get("block_type") or "text",
                    }
                )
        else:
            text = (page.get("text") or "").strip()
            if text:
                for chunk in text.split("\n\n"):
                    chunk = chunk.strip()
                    if chunk:
                        flat.append(
                            {
                                "page": page_no,
                                "text": chunk,
                                "bbox": None,
                                "block_type": "paragraph",
                            }
                        )
    if not flat and parsed.full_text.strip():
        flat.append(
            {
                "page": 1,
                "text": parsed.full_text.strip(),
                "bbox": None,
                "block_type": "text",
            }
        )
    return flat


def ensure_version_blocks(
    db: Session,
    version: DocumentVersion,
    *,
    force: bool = False,
) -> list[DocumentVersionBlock]:
    """解析并持久化版本分块（幂等）。"""
    if version.file_size <= 0:
        return []

    if not force:
        existing = list(
            db.scalars(
                select(DocumentVersionBlock)
                .where(DocumentVersionBlock.version_id == version.id)
                .order_by(DocumentVersionBlock.block_index.asc())
            ).all()
        )
        if existing:
            return existing

    parsed = parse_version_document(db, version)
    flat = _flatten_page_blocks(parsed)

    db.execute(
        delete(DocumentVersionBlock).where(DocumentVersionBlock.version_id == version.id)
    )

    rows: list[DocumentVersionBlock] = []
    for idx, blk in enumerate(flat):
        row = DocumentVersionBlock(
            document_id=version.document_id,
            version_id=version.id,
            block_index=idx,
            page=int(blk.get("page") or 1),
            block_type=str(blk.get("block_type") or "text")[:32],
            text=blk["text"],
            bbox=blk.get("bbox"),
            meta_json={"parse_quality": parsed.parse_quality},
        )
        db.add(row)
        rows.append(row)

    db.commit()
    for row in rows:
        db.refresh(row)
    return rows


def load_version_blocks(db: Session, version_id: uuid.UUID) -> list[DocumentVersionBlock]:
    return list(
        db.scalars(
            select(DocumentVersionBlock)
            .where(DocumentVersionBlock.version_id == version_id)
            .order_by(DocumentVersionBlock.block_index.asc())
        ).all()
    )


def blocks_to_content_dict(blocks: list[DocumentVersionBlock]) -> dict:
    """供对比 API 返回的 pages/blocks 结构。"""
    by_page: dict[int, list[dict]] = {}
    for b in blocks:
        by_page.setdefault(b.page, []).append(
            {
                "block_index": b.block_index,
                "text": b.text,
                "bbox": b.bbox,
                "block_type": b.block_type,
            }
        )
    pages = []
    full_parts: list[str] = []
    for page_no in sorted(by_page.keys()):
        page_blocks = by_page[page_no]
        text = "\n\n".join(x["text"] for x in page_blocks)
        full_parts.append(text)
        pages.append({"page": page_no, "text": text, "blocks": page_blocks})
    parse_quality = "blocks"
    if blocks and blocks[0].meta_json:
        parse_quality = blocks[0].meta_json.get("parse_quality") or parse_quality
    return {
        "pages": pages,
        "full_text": "\n\n".join(full_parts).strip(),
        "parse_quality": parse_quality,
        "blocks": [
            {
                "block_index": b.block_index,
                "page": b.page,
                "text": b.text,
                "bbox": b.bbox,
                "block_type": b.block_type,
            }
            for b in blocks
        ],
    }
