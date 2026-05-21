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


def split_paragraphs(text: str) -> list[str]:
    chunks = re.split(r"\n\s*\n+", text)
    return [c.strip() for c in chunks if c.strip()]


def local_search(
    parsed_docs: list[ParsedDocument],
    query: str,
    *,
    limit: int = 20,
) -> list[dict]:
    """Simple keyword search over parsed documents (KnowFlow stub)."""
    q = query.strip().lower()
    if not q:
        return []
    terms = [t for t in re.split(r"\s+", q) if len(t) >= 2]
    if not terms:
        terms = [q]
    hits: list[dict] = []
    for doc in parsed_docs:
        for para in split_paragraphs(doc.full_text):
            lower = para.lower()
            score = sum(lower.count(t) for t in terms)
            if score <= 0:
                continue
            hits.append(
                {
                    "document_id": str(doc.document_id),
                    "snippet": para[:500],
                    "score": float(score),
                    "anchor_json": {"page": 1, "bbox": None, "kind": "text"},
                }
            )
    hits.sort(key=lambda x: x["score"], reverse=True)
    return hits[:limit]
