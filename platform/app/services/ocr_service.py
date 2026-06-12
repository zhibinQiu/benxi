"""OCR 识别：调用平台配置的 PaddleOCR-VL / layout-parsing 服务。"""

from __future__ import annotations

import io
import json
import re
import zipfile
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.integrations.paddleocr_client import is_openai_compatible_ocr_base, recognize_bytes
from app.schemas.ocr import (
    OcrBlockOut,
    OcrExportIn,
    OcrMetaOut,
    OcrPageOut,
    OcrRecognizeOut,
)
from app.services.model_settings_service import get_paddleocr_credentials

_ACCEPTED_EXTENSIONS = (
    ".png",
    ".jpg",
    ".jpeg",
    ".webp",
    ".bmp",
    ".tif",
    ".tiff",
    ".pdf",
)
_MAX_FILE_MB = 50


def _provider_label(base_url: str, model: str) -> str:
    if is_openai_compatible_ocr_base(base_url):
        host = (base_url or "").lower()
        if "siliconflow" in host:
            return "硅基流动 PaddleOCR-VL"
        return "OpenAI 兼容 OCR"
    if base_url:
        return "PaddleOCR layout-parsing"
    return "未配置"


def get_meta(db: Session) -> OcrMetaOut:
    base, _, model = get_paddleocr_credentials(db)
    configured = bool(base)
    hint = None
    if not configured:
        hint = "请在资源管理中配置 PaddleOCR-VL 的 API URL、模型名与 Key。"
    return OcrMetaOut(
        configured=configured,
        provider=_provider_label(base, model),
        model=model or "",
        max_file_mb=_MAX_FILE_MB,
        accepted_extensions=list(_ACCEPTED_EXTENSIONS),
        default_language=None,
        service_hint=hint,
    )


def _blocks_to_pages(blocks: list[dict]) -> list[OcrPageOut]:
    by_page: dict[int, list[OcrBlockOut]] = {}
    for blk in blocks:
        page = int(blk.get("page") or 1)
        by_page.setdefault(page, []).append(
            OcrBlockOut(
                text=str(blk.get("text") or ""),
                page=page,
                bbox=blk.get("bbox"),
                block_type=str(blk.get("block_type") or "text"),
            )
        )
    pages: list[OcrPageOut] = []
    for page_no in sorted(by_page.keys()):
        page_blocks = by_page[page_no]
        text = "\n\n".join(b.text for b in page_blocks if b.text).strip()
        pages.append(OcrPageOut(page=page_no, text=text, blocks=page_blocks))
    return pages


def blocks_to_markdown(file_name: str, pages: list[OcrPageOut], text: str = "") -> str:
    lines = [f"# {file_name}", ""]
    if pages:
        for page in pages:
            lines.append(f"## 第 {page.page} 页")
            lines.append("")
            if page.text.strip():
                lines.append(page.text.strip())
            lines.append("")
    elif text.strip():
        lines.append(text.strip())
        lines.append("")
    return "\n".join(lines).strip() + "\n"


def _safe_zip_name(file_name: str, suffix: str) -> str:
    stem = Path(file_name or "ocr").stem
    stem = re.sub(r"[^\w\u4e00-\u9fff.-]+", "_", stem).strip("._") or "ocr"
    return f"{stem}{suffix}"


def recognize_file(
    db: Session,
    *,
    content: bytes,
    file_name: str,
    mime_type: str | None = None,
    language: str | None = None,
) -> OcrRecognizeOut:
    base, api_key, model = get_paddleocr_credentials(db)
    if not base:
        raise ValueError("未配置文件内容提取服务，请在资源管理中设置 PaddleOCR-VL")

    size_mb = len(content) / (1024 * 1024)
    if size_mb > _MAX_FILE_MB:
        raise ValueError(f"文件超过 {_MAX_FILE_MB} MB 限制")

    ext = Path(file_name or "").suffix.lower()
    if ext and ext not in _ACCEPTED_EXTENSIONS:
        raise ValueError(f"不支持的文件类型：{ext}")

    raw = recognize_bytes(
        content,
        service_url=base,
        api_key=api_key,
        model_name=model,
        file_name=file_name,
        mime_type=mime_type or "application/octet-stream",
        language=(language or "").strip(),
    )
    blocks_raw = raw.get("blocks") or []
    pages = _blocks_to_pages(blocks_raw)
    text = str(raw.get("text") or "").strip()
    if not text and pages:
        text = "\n\n".join(p.text for p in pages if p.text).strip()

    block_out = [
        OcrBlockOut(
            text=str(b.get("text") or ""),
            page=int(b.get("page") or 1),
            bbox=b.get("bbox"),
            block_type=str(b.get("block_type") or "text"),
        )
        for b in blocks_raw
    ]
    if not pages and text:
        pages = [
            OcrPageOut(
                page=1,
                text=text,
                blocks=block_out or [OcrBlockOut(text=text, page=1)],
            )
        ]

    markdown = blocks_to_markdown(file_name, pages, text=text)
    provider = _provider_label(base, model)
    return OcrRecognizeOut(
        file_name=file_name,
        text=text,
        markdown=markdown,
        blocks=block_out,
        pages=pages,
        model=model or provider,
        provider=provider,
    )


def build_export_zip(body: OcrExportIn) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for item in body.items:
            if body.format == "markdown":
                content = (item.markdown or "").strip()
                if not content:
                    pages = item.pages or []
                    content = blocks_to_markdown(item.file_name, pages, text=item.text)
                zf.writestr(_safe_zip_name(item.file_name, ".md"), content)
            else:
                doc: dict[str, Any] = {
                    "file_name": item.file_name,
                    "text": item.text,
                    "pages": [p.model_dump() for p in item.pages],
                    "blocks": [b.model_dump() for b in item.blocks],
                }
                if not doc["pages"] and item.text:
                    doc["pages"] = [
                        {
                            "page": 1,
                            "text": item.text,
                            "blocks": [b.model_dump() for b in item.blocks],
                        }
                    ]
                zf.writestr(
                    _safe_zip_name(item.file_name, ".json"),
                    json.dumps(doc, ensure_ascii=False, indent=2),
                )
    return buf.getvalue()
