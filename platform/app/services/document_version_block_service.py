"""文档版本结构化分块：OCR 解析、持久化与读取。"""

from __future__ import annotations

import logging
import re
import uuid

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.integrations.paddleocr_client import recognize_bytes
from app.integrations.text_extract import ParsedDocument, extract_text_from_bytes
from app.models.document import DocumentVersion
from app.models.document_version_block import DocumentVersionBlock
from app.storage.object_store import StorageObjectNotFoundError, get_object_store

logger = logging.getLogger(__name__)

_MIN_KNOWFLOW_TEXT_CHARS = 32


def _plain_text_char_count(text: str) -> int:
    return len(re.sub(r"\s+", "", text or ""))


def load_version_full_text_from_blocks(
    db: Session,
    version_id: uuid.UUID,
    *,
    min_chars: int = _MIN_KNOWFLOW_TEXT_CHARS,
) -> str | None:
    """仅从 DB 读取已缓存分块文本（不访问 MinIO），供 KnowFlow 复用。"""
    parts = db.scalars(
        select(DocumentVersionBlock.text)
        .where(DocumentVersionBlock.version_id == version_id)
        .order_by(DocumentVersionBlock.block_index.asc())
    ).all()
    if not parts:
        return None
    text = "\n\n".join(p for p in parts if (p or "").strip()).strip()
    if _plain_text_char_count(text) < min_chars:
        return None
    return text


def build_knowflow_upload_from_block_text(
    version: DocumentVersion,
    text: str,
    *,
    title: str = "",
) -> tuple[str, bytes, str]:
    """将平台分块文本打包为 PDF 上传 KnowFlow（DeepDOC 解析后可生成引用截图）。"""
    from app.integrations.article_pdf_export import markdown_text_to_pdf_bytes
    from app.integrations.html_document_export import _safe_base_name

    stem = _safe_base_name(
        title or (version.file_name or "").rsplit(".", 1)[0],
        "document",
    )
    doc_title = (title or stem).strip()
    pdf = markdown_text_to_pdf_bytes(doc_title, text.strip())
    return f"{stem}.pdf", pdf, "application/pdf"


def resolve_knowflow_upload_from_version(
    db: Session,
    document,
    version: DocumentVersion,
    *,
    read_object_bytes,
) -> tuple[str, bytes, str, bool]:
    """优先复用 DB 分块；否则读取原文件。返回 (name, content, mime, from_cached_blocks)。

    PDF / Office / 表格 / 纯文本等可索引原文件始终走原文件上传（必要时转为 PDF），
    以便 KnowFlow 解析后生成引用溯源页截图；仅无法保留版式的类型才复用 Markdown 分块。
    """
    from app.integrations.html_document_export import (
        file_supports_knowflow_original_upload,
        normalize_file_for_knowflow_upload,
    )

    if not file_supports_knowflow_original_upload(
        version.file_name, version.mime_type or ""
    ):
        text = load_version_full_text_from_blocks(db, version.id)
        if not text:
            ensure_version_blocks(db, version)
            text = load_version_full_text_from_blocks(db, version.id)
        if text:
            name, body, mime = build_knowflow_upload_from_block_text(
                version,
                text,
                title=getattr(document, "title", None) or "",
            )
            logger.info(
                "KnowFlow 上传复用平台分块 doc=%s version=%s bytes=%s",
                version.document_id,
                version.id,
                len(body),
            )
            return name, body, mime, True

    raw = read_object_bytes(document, version)
    name, body, mime = normalize_file_for_knowflow_upload(
        version.file_name,
        raw,
        version.mime_type,
        title=getattr(document, "title", None) or "",
        description=getattr(document, "description", None) or "",
    )
    logger.info(
        "KnowFlow 上传原文件（引用截图） doc=%s version=%s file=%s bytes=%s",
        version.document_id,
        version.id,
        name,
        len(body),
    )
    return name, body, mime, False


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
        from app.services.model_settings_service import get_paddleocr_credentials

        ocr_url, ocr_key, ocr_model = get_paddleocr_credentials(db)
        ocr_url = (ocr_url or "").strip()

    if need_ocr and ocr_url:
        try:
            ocr = recognize_bytes(
                data,
                service_url=ocr_url,
                api_key=ocr_key,
                model_name=ocr_model,
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
                parsed.warning = (parsed.warning or "") + " 文件内容提取失败"

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

    from app.models.document import Document

    doc = db.get(Document, version.document_id)
    if not doc or doc.deleted_at:
        logger.info(
            "版本分块跳过：文档不存在或已删除 doc=%s version=%s",
            version.document_id,
            version.id,
        )
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

    try:
        parsed = parse_version_document(db, version)
    except StorageObjectNotFoundError:
        logger.warning(
            "版本分块跳过：MinIO 对象不存在 version=%s key=%s",
            version.id,
            version.file_key,
        )
        return []
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

    try:
        db.commit()
    except Exception:
        db.rollback()
        raise
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
