"""CPU-only document text extraction (no KnowFlow / GPU)."""

from __future__ import annotations

import io
import re
import uuid
from dataclasses import dataclass, field


@dataclass
class TextBlock:
    text: str
    page: int = 1
    bbox: list[float] | None = None


@dataclass
class ParsedDocument:
    document_id: uuid.UUID
    file_name: str
    full_text: str
    pages: list[dict] = field(default_factory=list)
    parse_quality: str = "text_layer"
    warning: str | None = None


def extract_text_from_bytes(
    data: bytes,
    *,
    document_id: uuid.UUID,
    file_name: str,
    mime_type: str = "",
) -> ParsedDocument:
    lower = file_name.lower()
    if lower.endswith(".pdf") or mime_type == "application/pdf":
        return _extract_pdf(data, document_id=document_id, file_name=file_name)
    if lower.endswith((".doc", ".docx")) or "word" in mime_type.lower():
        return _extract_docx(data, document_id=document_id, file_name=file_name)
    if lower.endswith((".txt", ".md", ".csv")):
        text = data.decode("utf-8", errors="replace")
        return ParsedDocument(
            document_id=document_id,
            file_name=file_name,
            full_text=text,
            pages=[{"page": 1, "text": text, "blocks": [{"text": text, "bbox": None}]}],
            parse_quality="text_layer",
        )
    return ParsedDocument(
        document_id=document_id,
        file_name=file_name,
        full_text="",
        parse_quality="unsupported",
        warning=f"暂不支持的文件格式: {file_name}",
    )


def _extract_pdf(data: bytes, *, document_id: uuid.UUID, file_name: str) -> ParsedDocument:
    try:
        from pypdf import PdfReader
    except ImportError:
        return ParsedDocument(
            document_id=document_id,
            file_name=file_name,
            full_text="",
            parse_quality="unsupported",
            warning="未安装 pypdf，无法解析 PDF",
        )

    reader = PdfReader(io.BytesIO(data))
    pages: list[dict] = []
    parts: list[str] = []
    for i, page in enumerate(reader.pages, start=1):
        text = (page.extract_text() or "").strip()
        parts.append(text)
        pages.append(
            {
                "page": i,
                "text": text,
                "blocks": [{"text": text, "bbox": None}] if text else [],
            }
        )
    full = "\n\n".join(parts).strip()
    quality = "text_layer" if full else "ocr_required"
    warning = None if full else "PDF 无文本层，后续可接入 KnowFlow OCR"
    return ParsedDocument(
        document_id=document_id,
        file_name=file_name,
        full_text=full,
        pages=pages,
        parse_quality=quality,
        warning=warning,
    )


def _extract_docx(
    data: bytes, *, document_id: uuid.UUID, file_name: str
) -> ParsedDocument:
    try:
        from docx import Document as DocxDocument
    except ImportError:
        return ParsedDocument(
            document_id=document_id,
            file_name=file_name,
            full_text="",
            parse_quality="unsupported",
            warning="未安装 python-docx，无法解析 Word 文档",
        )
    try:
        doc = DocxDocument(io.BytesIO(data))
        paras = [p.text.strip() for p in doc.paragraphs if p.text.strip()]
        full = "\n\n".join(paras).strip()
        pages = [
            {
                "page": 1,
                "text": full,
                "blocks": [{"text": t, "bbox": None} for t in paras],
            }
        ]
        return ParsedDocument(
            document_id=document_id,
            file_name=file_name,
            full_text=full,
            pages=pages,
            parse_quality="docx",
        )
    except Exception as e:
        return ParsedDocument(
            document_id=document_id,
            file_name=file_name,
            full_text="",
            parse_quality="failed",
            warning=f"Word 解析失败: {e}",
        )


def split_paragraphs(text: str) -> list[str]:
    chunks = re.split(r"\n\s*\n+", text)
    return [c.strip() for c in chunks if c.strip()]


def _parse_field_query(query: str) -> tuple[list[str], list[tuple[str, str]]]:
    """解析自然语言 + 字段匹配，如「违约金」或「条款:违约」。"""
    fields: list[tuple[str, str]] = []
    terms: list[str] = []
    for part in re.split(r"\s+", query.strip()):
        if not part:
            continue
        if ":" in part or "：" in part:
            sep = ":" if ":" in part else "："
            k, v = part.split(sep, 1)
            k, v = k.strip(), v.strip()
            if k and v:
                fields.append((k.lower(), v.lower()))
                continue
        if len(part) >= 2:
            terms.append(part.lower())
    if not terms and not fields:
        terms = [query.strip().lower()]
    return terms, fields


def local_search(
    parsed_docs: list[ParsedDocument],
    query: str,
    *,
    limit: int = 20,
    field_match: bool = True,
) -> list[dict]:
    """关键词 + 可选字段匹配检索（KnowFlow 不可用时的回退）。"""
    q = query.strip()
    if not q:
        return []
    terms, fields = _parse_field_query(q) if field_match else ([q.lower()], [])
    if not terms and not fields:
        terms = [q.lower()]
    hits: list[dict] = []
    for doc in parsed_docs:
        for page in doc.pages or [{"page": 1, "text": doc.full_text}]:
            page_no = page.get("page", 1)
            for para in split_paragraphs(page.get("text") or ""):
                lower = para.lower()
                score = sum(lower.count(t) for t in terms)
                for fk, fv in fields:
                    if fk in lower and fv in lower:
                        score += 5
                if score <= 0:
                    continue
                hits.append(
                    {
                        "document_id": str(doc.document_id),
                        "snippet": para[:500],
                        "score": float(score),
                        "anchor_json": {"page": page_no, "bbox": None, "kind": "text"},
                        "source": "local",
                    }
                )
        if not doc.pages and doc.full_text:
            for para in split_paragraphs(doc.full_text):
                lower = para.lower()
                score = sum(lower.count(t) for t in terms)
                for fk, fv in fields:
                    if fk in lower and fv in lower:
                        score += 5
                if score <= 0:
                    continue
                hits.append(
                    {
                        "document_id": str(doc.document_id),
                        "snippet": para[:500],
                        "score": float(score),
                        "anchor_json": {"page": 1, "bbox": None, "kind": "text"},
                        "source": "local",
                    }
                )
    hits.sort(key=lambda x: x["score"], reverse=True)
    return hits[:limit]
