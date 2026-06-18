"""AI 智能体临时附件 — 本地文件存储（不入知识库 / 文档库）。"""

from __future__ import annotations

import json
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.config import get_settings

_PLATFORM_DIR = Path(__file__).resolve().parent.parent.parent


def _user_key(user_id: Any) -> str:
    return str(user_id)


def _json_default(value: Any) -> Any:
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def _storage_root() -> Path:
    settings = get_settings()
    raw = (settings.ai_chat_attachment_storage_dir or "").strip()
    if raw:
        return Path(raw).expanduser().resolve()
    return (_PLATFORM_DIR / ".run" / "ai-chat-attachments").resolve()


def _user_root(user_id: Any) -> Path:
    root = _storage_root() / _user_key(user_id)
    root.mkdir(parents=True, exist_ok=True)
    return root


def new_session_id() -> str:
    return uuid.uuid4().hex


def new_file_id() -> str:
    return uuid.uuid4().hex[:16]


def session_dir(user_id: Any, session_id: str) -> Path:
    return _user_root(user_id) / session_id


def manifest_path(user_id: Any, session_id: str) -> Path:
    return session_dir(user_id, session_id) / "manifest.json"


def load_manifest(user_id: Any, session_id: str) -> dict[str, Any] | None:
    path = manifest_path(user_id, session_id)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except (OSError, json.JSONDecodeError):
        return None


def save_manifest(user_id: Any, session_id: str, manifest: dict[str, Any]) -> None:
    root = session_dir(user_id, session_id)
    root.mkdir(parents=True, exist_ok=True)
    manifest_path(user_id, session_id).write_text(
        json.dumps(manifest, ensure_ascii=False, default=_json_default),
        encoding="utf-8",
    )


def clear_session(user_id: Any, session_id: str) -> None:
    root = session_dir(user_id, session_id)
    if root.is_dir():
        shutil.rmtree(root, ignore_errors=True)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
