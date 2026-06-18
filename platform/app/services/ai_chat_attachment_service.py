"""AI 智能体临时附件 — 上传、正文提取与问答上下文。"""

from __future__ import annotations

import json
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import UploadFile
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.exceptions import bad_request, not_found
from app.core.text_utils import truncate_text
from app.integrations.text_extract import ParsedDocument, extract_text_from_bytes
from app.schemas.ai_chat import AttachmentFileOut, AttachmentSessionOut, AttachmentUploadOut
from app.services import ai_chat_attachment_store as store

_ATTACHMENTS_INSTRUCTION = """用户上传了临时附件（未写入知识库或文档库），仅供当前对话参考。
请优先依据附件正文回答用户问题。
若用户询问多份文档的差异、对比或异同，请用自然语言归纳要点，不要使用 JSON、表格 diff 或结构化差异列表。
若附件正文不足以回答，请明确说明缺口，不要编造附件中不存在的内容。"""

_ACCEPTED_EXTENSIONS = (
    ".pdf",
    ".doc",
    ".docx",
    ".dot",
    ".dotx",
    ".txt",
    ".md",
    ".markdown",
    ".csv",
    ".html",
    ".htm",
    ".xlsx",
    ".xls",
    ".xlsm",
    ".pptx",
    ".rtf",
    ".json",
    ".xml",
    ".yaml",
    ".yml",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".webp",
    ".bmp",
    ".tif",
    ".tiff",
    ".log",
    ".ini",
    ".conf",
    ".properties",
)

_OCR_EXTENSIONS = (
    ".pdf",
    ".png",
    ".jpg",
    ".jpeg",
    ".webp",
    ".bmp",
    ".tif",
    ".tiff",
)



def _file_ext(name: str) -> str:
    return Path(name or "").suffix.lower()


def _validate_extension(file_name: str) -> None:
    ext = _file_ext(file_name)
    if ext not in _ACCEPTED_EXTENSIONS:
        raise bad_request(f"不支持的文件格式: {file_name}")


def _parse_uploaded_file(
    db: Session | None,
    *,
    content: bytes,
    file_name: str,
    mime_type: str,
) -> ParsedDocument:
    doc_id = uuid.uuid4()
    parsed = extract_text_from_bytes(
        content,
        document_id=doc_id,
        file_name=file_name,
        mime_type=mime_type,
    )
    needs_ocr = (
        not (parsed.full_text or "").strip()
        or parsed.parse_quality in ("ocr_required", "failed")
    )
    if needs_ocr and db is not None and _file_ext(file_name) in _OCR_EXTENSIONS:
        try:
            from app.services.ocr_service import recognize_file

            ocr = recognize_file(
                db,
                content=content,
                file_name=file_name,
                mime_type=mime_type or None,
            )
            text = (ocr.text or "").strip()
            if text:
                return ParsedDocument(
                    document_id=doc_id,
                    file_name=file_name,
                    full_text=text,
                    parse_quality="ocr",
                    warning=parsed.warning,
                )
        except ValueError:
            pass
    return parsed


def _manifest_out(manifest: dict[str, Any]) -> AttachmentSessionOut:
    files = manifest.get("files") or []
    return AttachmentSessionOut(
        attachment_session_id=str(manifest.get("session_id") or ""),
        files=[
            AttachmentFileOut(
                file_id=str(f.get("file_id") or ""),
                file_name=str(f.get("file_name") or ""),
                char_count=int(f.get("char_count") or 0),
                parse_quality=str(f.get("parse_quality") or ""),
                warning=f.get("warning"),
            )
            for f in files
            if isinstance(f, dict)
        ],
    )


def get_owned_session(user_id: Any, session_id: str) -> dict[str, Any]:
    sid = (session_id or "").strip()
    if not sid:
        raise bad_request("缺少附件会话 ID")
    manifest = store.load_manifest(user_id, sid)
    if not manifest:
        raise not_found("附件会话不存在或已过期")
    if str(manifest.get("user_id") or "") != str(user_id):
        raise not_found("附件会话不存在或已过期")
    return manifest


def get_session_out(user_id: Any, session_id: str) -> AttachmentSessionOut:
    manifest = get_owned_session(user_id, session_id)
    return _manifest_out(manifest)


async def upload_attachments(
    db: Session | None,
    *,
    user_id: Any,
    files: list[UploadFile],
    attachment_session_id: str | None = None,
) -> AttachmentUploadOut:
    if not files:
        raise bad_request("请选择至少一个文件")
    settings = get_settings()
    max_files = max(1, settings.ai_chat_attachment_max_files)
    max_bytes = settings.ai_chat_attachment_max_file_mb * 1024 * 1024

    sid = (attachment_session_id or "").strip() or store.new_session_id()
    manifest = store.load_manifest(user_id, sid)
    if manifest and str(manifest.get("user_id") or "") != str(user_id):
        raise not_found("附件会话不存在或已过期")
    if not manifest:
        manifest = {
            "session_id": sid,
            "user_id": str(user_id),
            "created_at": store.utc_now_iso(),
            "updated_at": store.utc_now_iso(),
            "files": [],
        }

    existing = list(manifest.get("files") or [])
    if len(existing) + len(files) > max_files:
        raise bad_request(f"临时附件最多 {max_files} 个，请删除部分后重试")

    added: list[AttachmentFileOut] = []
    for upload in files:
        file_name = (upload.filename or "attachment").strip() or "attachment"
        _validate_extension(file_name)
        content = await upload.read()
        if not content:
            raise bad_request(f"文件为空: {file_name}")
        if len(content) > max_bytes:
            raise bad_request(
                f"文件 {file_name} 超过 {settings.ai_chat_attachment_max_file_mb}MB 限制"
            )
        parsed = _parse_uploaded_file(
            db,
            content=content,
            file_name=file_name,
            mime_type=upload.content_type or "",
        )
        file_id = store.new_file_id()
        entry = {
            "file_id": file_id,
            "file_name": file_name,
            "mime_type": upload.content_type or "",
            "char_count": len(parsed.full_text or ""),
            "full_text": parsed.full_text or "",
            "parse_quality": parsed.parse_quality,
            "warning": parsed.warning,
            "uploaded_at": store.utc_now_iso(),
        }
        existing.append(entry)
        added.append(
            AttachmentFileOut(
                file_id=file_id,
                file_name=file_name,
                char_count=entry["char_count"],
                parse_quality=parsed.parse_quality,
                warning=parsed.warning,
            )
        )

    manifest["files"] = existing
    manifest["updated_at"] = store.utc_now_iso()
    store.save_manifest(user_id, sid, manifest)
    return AttachmentUploadOut(
        attachment_session_id=sid,
        files=added,
        total_files=len(existing),
    )


def remove_attachment_file(user_id: Any, session_id: str, file_id: str) -> AttachmentSessionOut:
    manifest = get_owned_session(user_id, session_id)
    fid = (file_id or "").strip()
    files = [f for f in (manifest.get("files") or []) if str(f.get("file_id")) != fid]
    if len(files) == len(manifest.get("files") or []):
        raise not_found("附件不存在")
    if not files:
        store.clear_session(user_id, session_id)
        return AttachmentSessionOut(attachment_session_id=session_id, files=[])
    manifest["files"] = files
    manifest["updated_at"] = store.utc_now_iso()
    store.save_manifest(user_id, session_id, manifest)
    return _manifest_out(manifest)


def clear_attachment_session(user_id: Any, session_id: str) -> None:
    get_owned_session(user_id, session_id)
    store.clear_session(user_id, session_id)


def build_attachment_context(files: list[dict[str, Any]]) -> str:
    usable = [f for f in files if isinstance(f, dict)]
    if not usable:
        return ""
    settings = get_settings()
    per_doc = max(
        1500,
        settings.deepseek_max_chars // max(len(usable), 1) // 2,
    )
    parts = [_ATTACHMENTS_INSTRUCTION, ""]
    for idx, item in enumerate(usable, 1):
        title = str(item.get("file_name") or f"附件{idx}")
        text = truncate_text(str(item.get("full_text") or ""), per_doc)
        parts.append(f"### 附件 {idx}: {title}")
        warning = (item.get("warning") or "").strip()
        if warning:
            parts.append(f"（提取说明: {warning}）")
        parts.append(text or "（未能提取正文）")
        parts.append("")
    return "\n".join(parts).strip()


def purge_expired_sessions() -> int:
    """清理超过 TTL 的临时附件目录，返回删除的会话数。"""
    settings = get_settings()
    ttl_hours = max(1, settings.ai_chat_attachment_ttl_hours)
    cutoff = datetime.now(timezone.utc).timestamp() - ttl_hours * 3600
    root = store._storage_root()
    if not root.is_dir():
        return 0
    removed = 0
    for user_dir in root.iterdir():
        if not user_dir.is_dir():
            continue
        for session_dir in user_dir.iterdir():
            if not session_dir.is_dir():
                continue
            manifest_file = session_dir / "manifest.json"
            if not manifest_file.is_file():
                shutil_rmtree_safe(session_dir)
                removed += 1
                continue
            try:
                data = json.loads(manifest_file.read_text(encoding="utf-8"))
                updated = data.get("updated_at") or data.get("created_at")
                ts = datetime.fromisoformat(str(updated)).timestamp()
            except (OSError, ValueError, TypeError):
                ts = manifest_file.stat().st_mtime
            if ts < cutoff:
                shutil_rmtree_safe(session_dir)
                removed += 1
    return removed


def shutil_rmtree_safe(path: Path) -> None:
    shutil.rmtree(path, ignore_errors=True)
