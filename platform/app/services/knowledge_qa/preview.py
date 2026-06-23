"""Knowledge QA — 引用截图预览."""

from __future__ import annotations

import logging
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.permissions import PermissionLevel, can_access_document
from app.integrations.ragflow_client import RagflowClient, RagflowError
from app.models.document import Document, DocumentVersion
from app.models.org import User
from app.models.ragflow_document_link import RagflowDocumentLink
from app.services.document_service import get_document, resolve_current_version
from app.services.knowledge_qa.retrieval import _rag_clients_for_qa

logger = logging.getLogger(__name__)


def resolve_citation_image_id(
    db: Session,
    user: User,
    *,
    image_id: str | None = None,
    chunk_id: str | None = None,
    dataset_id: str | None = None,
    ragflow_document_id: str | None = None,
) -> str | None:
    """解析 KnowFlow 切片截图 ID（优先检索带回的 image_id，否则按 chunk 查询）。"""
    iid = (image_id or "").strip()
    if iid:
        return iid
    cid = (chunk_id or "").strip()
    ds_id = (dataset_id or "").strip()
    rid = (ragflow_document_id or "").strip()
    if not cid or not ds_id or not rid:
        return None
    for rag in _rag_clients_for_qa(db, user):
        if not rag.health_ok():
            continue
        try:
            resolved = rag.resolve_chunk_image_id(
                dataset_id=ds_id,
                ragflow_document_id=rid,
                chunk_id=cid,
            )
            if resolved:
                return resolved
        except RagflowError as exc:
            logger.debug("按 chunk 解析截图 ID 失败 chunk=%s: %s", cid, exc)
    return None


def _resolve_chunk_anchor_for_citation(
    db: Session,
    user: User,
    *,
    chunk_id: str | None,
    dataset_id: str | None,
    ragflow_document_id: str | None,
) -> dict[str, Any]:
    """从 KnowFlow 切片列表解析页码与 bbox（KnowFlow 无截图时的兜底）。"""
    cid = (chunk_id or "").strip()
    ds_id = (dataset_id or "").strip()
    rid = (ragflow_document_id or "").strip()
    if not cid or not ds_id or not rid:
        return {}
    for rag in _rag_clients_for_qa(db, user):
        if not rag.health_ok():
            continue
        try:
            page = 1
            while page <= 20:
                chunks, total, _ = rag.list_document_chunks(
                    ds_id, rid, page=page, page_size=50
                )
                for ch in chunks:
                    ch_id = str(ch.get("chunk_id") or ch.get("id") or "").strip()
                    if ch_id != cid:
                        continue
                    anchor = RagflowClient._parse_chunk_positions(ch.get("positions"))
                    page_no = anchor.get("page") or ch.get("page_num") or ch.get("page")
                    if page_no is not None:
                        anchor["page"] = int(page_no)
                    return anchor
                if page * 50 >= int(total or 0):
                    break
                page += 1
        except RagflowError as exc:
            logger.debug("解析切片锚点失败 chunk=%s: %s", cid, exc)
    return {}


def parse_citation_bbox_param(raw: str | None) -> list[float] | None:
    """解析 ?bbox=x0,y0,x1,y1 查询参数。"""
    text = (raw or "").strip()
    if not text:
        return None
    try:
        parts = [float(x.strip()) for x in text.split(",") if x.strip()]
    except ValueError:
        return None
    if len(parts) >= 4:
        return parts[:4]
    return None


def _resolve_platform_version_for_citation(
    db: Session,
    *,
    ragflow_document_id: str,
    platform_document_id: uuid.UUID | None = None,
) -> tuple[Document, DocumentVersion] | None:
    """按 RAGFlow 文档 ID 或平台文档 ID 定位可渲染 PDF 的版本。"""
    from app.models.ragflow_document_link import RagflowDocumentLink
    from app.models.document import DocumentVersion
    from app.services.document_service import resolve_current_version
    from app.services.ragflow_version_link_service import (
        get_version_link_by_ragflow_id,
        resolve_latest_indexed_version,
    )

    def _pick_version(doc: Document) -> DocumentVersion | None:
        if not doc or doc.deleted_at:
            return None
        ver = resolve_latest_indexed_version(db, doc) or resolve_current_version(db, doc)
        if ver and ver.file_key:
            return ver
        return None

    pid = platform_document_id
    if pid:
        doc = get_document(db, pid)
        ver = _pick_version(doc) if doc else None
        if doc and ver:
            return doc, ver

    rid = (ragflow_document_id or "").strip()
    if not rid:
        return None

    link = get_version_link_by_ragflow_id(db, rid)
    if link:
        doc = get_document(db, link.platform_document_id)
        ver = db.get(DocumentVersion, link.platform_version_id)
        if doc and ver and ver.file_key and not doc.deleted_at:
            return doc, ver

    doc_link = db.scalar(
        select(RagflowDocumentLink).where(RagflowDocumentLink.ragflow_document_id == rid)
    )
    if doc_link:
        doc = get_document(db, doc_link.platform_document_id)
        ver = _pick_version(doc) if doc else None
        if doc and ver:
            return doc, ver
    return None


def _fetch_citation_pdf_page_fallback(
    db: Session,
    user: User,
    *,
    chunk_id: str | None = None,
    dataset_id: str | None = None,
    ragflow_document_id: str | None = None,
    platform_document_id: uuid.UUID | None = None,
    page: int | None = None,
    bbox: list[float] | None = None,
    bbox_format: str = "auto",
    highlight_text: str | None = None,
) -> tuple[bytes, str] | None:
    """从平台文档 PDF 渲染页图，并在 bbox 处绘制半透明高亮（兜底）。"""
    from app.core.permissions import PermissionLevel, can_access_document
    from app.integrations.citation_pdf_preview import render_pdf_page_image
    from app.integrations.html_document_export import convert_file_bytes_to_pdf_for_citation
    from app.storage.object_store import get_object_store

    rid = (ragflow_document_id or "").strip()
    if not rid and not platform_document_id:
        return None

    resolved = _resolve_platform_version_for_citation(
        db,
        ragflow_document_id=rid,
        platform_document_id=platform_document_id,
    )
    if not resolved:
        return None
    doc, version = resolved
    if not can_access_document(db, user, doc, PermissionLevel.query.value):
        return None
    try:
        raw = get_object_store().get_object_bytes(version.file_key)
    except Exception as exc:
        logger.debug("读取文档文件失败 doc=%s: %s", doc.id, exc)
        return None
    try:
        converted = convert_file_bytes_to_pdf_for_citation(
            version.file_name,
            raw,
            version.mime_type or "",
            title=doc.title or "",
        )
        if not converted:
            from app.integrations.html_document_export import (
                normalize_file_for_knowflow_upload,
            )

            norm = normalize_file_for_knowflow_upload(
                version.file_name,
                raw,
                version.mime_type or "",
                title=doc.title or "",
                description=getattr(doc, "description", None) or "",
            )
            if norm[1].startswith(b"%PDF"):
                converted = norm
        if not converted:
            return None
        _, pdf_bytes, _ = converted
    except Exception as exc:
        logger.debug("转换引用预览 PDF 失败 doc=%s: %s", doc.id, exc)
        return None
    if not pdf_bytes.startswith(b"%PDF"):
        return None

    anchor = {}
    if chunk_id and dataset_id and rid:
        anchor = _resolve_chunk_anchor_for_citation(
            db,
            user,
            chunk_id=chunk_id,
            dataset_id=dataset_id,
            ragflow_document_id=rid,
        )
    page_num = page or anchor.get("page") or 1
    highlight_bbox = bbox if isinstance(bbox, list) else anchor.get("bbox")
    fmt = bbox_format if bbox_format != "auto" else str(
        anchor.get("bbox_format") or "auto"
    )
    try:
        return render_pdf_page_image(
            pdf_bytes,
            page_num=int(page_num),
            bbox=highlight_bbox if isinstance(highlight_bbox, list) else None,
            bbox_format=fmt,
            highlight_bbox=True,
            crop_to_bbox=bool(
                isinstance(highlight_bbox, list) and len(highlight_bbox) >= 4
            ),
            highlight_text=highlight_text,
        )
    except Exception as exc:
        logger.debug("渲染引用页截图失败 doc=%s page=%s: %s", doc.id, page_num, exc)
        return None


def fetch_citation_preview_bytes(
    db: Session,
    user: User,
    *,
    image_id: str | None = None,
    chunk_id: str | None = None,
    dataset_id: str | None = None,
    ragflow_document_id: str | None = None,
    platform_document_id: uuid.UUID | None = None,
    page: int | None = None,
    bbox: list[float] | None = None,
    bbox_format: str = "auto",
    highlight_text: str | None = None,
) -> tuple[bytes, str] | None:
    """获取引用截图：优先 KnowFlow /v1/document/image（与 KnowFlow 查看器同源），PDF 裁剪兜底。"""
    cid = (chunk_id or "").strip()
    ds_id = (dataset_id or "").strip()
    rid = (ragflow_document_id or "").strip()

    anchor: dict[str, Any] = {}
    if cid and ds_id and rid:
        anchor = _resolve_chunk_anchor_for_citation(
            db,
            user,
            chunk_id=cid,
            dataset_id=ds_id,
            ragflow_document_id=rid,
        )
    if page is not None:
        anchor["page"] = page
    if isinstance(bbox, list) and len(bbox) >= 4:
        anchor["bbox"] = bbox
    if bbox_format != "auto":
        anchor["bbox_format"] = bbox_format

    has_bbox = isinstance(anchor.get("bbox"), list) and len(anchor["bbox"]) >= 4
    fmt = str(anchor.get("bbox_format") or bbox_format or "auto")

    # 1) KnowFlow 切片截图（/v1/document/image，与 embed 查看器同源，区域最准）
    resolved = resolve_citation_image_id(
        db,
        user,
        image_id=image_id,
        chunk_id=chunk_id,
        dataset_id=dataset_id,
        ragflow_document_id=ragflow_document_id,
    )
    if resolved:
        from app.integrations.citation_pdf_preview import apply_image_highlight_wash

        for rag in _rag_clients_for_qa(db, user):
            if not rag.health_ok():
                continue
            try:
                body, content_type = rag.get_chunk_image(resolved)
                return apply_image_highlight_wash(body, content_type)
            except RagflowError as exc:
                logger.debug("获取 KnowFlow 引用截图失败 image=%s: %s", resolved, exc)

    # 2) 平台 PDF 页图兜底（KnowFlow 无图时；Word 等会先转为 PDF）
    fallback = _fetch_citation_pdf_page_fallback(
        db,
        user,
        chunk_id=cid or None,
        dataset_id=ds_id or None,
        ragflow_document_id=rid or None,
        platform_document_id=platform_document_id,
        page=anchor.get("page"),
        bbox=anchor.get("bbox") if has_bbox else None,
        bbox_format=fmt,
        highlight_text=highlight_text,
    )
    if fallback:
        return fallback

    # 3) 无法定位引用区域
    return None


def fetch_citation_image_bytes(
    db: Session, user: User, image_id: str
) -> tuple[bytes, str] | None:
    return fetch_citation_preview_bytes(db, user, image_id=image_id)


