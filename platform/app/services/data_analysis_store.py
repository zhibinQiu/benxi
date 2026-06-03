"""数据分析 — 本地文件存储（数据集、会话状态）。"""

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
    """用户 ID 在 ORM 中为 UUID，存储路径与 JSON 均使用字符串。"""
    return str(user_id)


def _json_default(value: Any) -> Any:
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def _storage_root() -> Path:
    settings = get_settings()
    raw = (settings.data_analysis_storage_dir or "").strip()
    if raw:
        return Path(raw).expanduser().resolve()
    return (_PLATFORM_DIR / ".run" / "data-analysis").resolve()


def _user_root(user_id: Any) -> Path:
    root = _storage_root() / _user_key(user_id)
    root.mkdir(parents=True, exist_ok=True)
    return root


def _datasets_root(user_id: Any) -> Path:
    root = _user_root(user_id) / "datasets"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _sessions_root(user_id: Any) -> Path:
    root = _user_root(user_id) / "sessions"
    root.mkdir(parents=True, exist_ok=True)
    return root


def new_dataset_id() -> str:
    return uuid.uuid4().hex


def new_session_id() -> str:
    return uuid.uuid4().hex


def new_cell_id() -> str:
    return uuid.uuid4().hex[:12]


def dataset_dir(user_id: Any, dataset_id: str) -> Path:
    return _datasets_root(user_id) / dataset_id


_ACCEPTED_EXTENSIONS = (".xlsx", ".xls", ".csv")


def dataset_file_path(user_id: Any, dataset_id: str) -> Path:
    base = dataset_dir(user_id, dataset_id)
    for name in ("data.xlsx", "data.xls", "data.csv"):
        path = base / name
        if path.is_file():
            return path
    return base / "data.xlsx"


def dataset_file_type(user_id: Any, dataset_id: str) -> str:
    path = dataset_file_path(user_id, dataset_id)
    ext = path.suffix.lower()
    if ext == ".csv":
        return "csv"
    return "excel"


def profile_path(user_id: Any, dataset_id: str) -> Path:
    return dataset_dir(user_id, dataset_id) / "profile.json"


def save_dataset_bytes(
    user_id: Any,
    dataset_id: str,
    *,
    filename: str,
    content: bytes,
) -> Path:
    ext = Path(filename or "data.xlsx").suffix.lower()
    if ext not in _ACCEPTED_EXTENSIONS:
        ext = ".xlsx"
    base = dataset_dir(user_id, dataset_id)
    if base.exists():
        shutil.rmtree(base)
    base.mkdir(parents=True, exist_ok=True)
    path = base / f"data{ext}"
    path.write_bytes(content)
    return path


def save_profile(user_id: Any, dataset_id: str, profile: dict[str, Any]) -> None:
    path = profile_path(user_id, dataset_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(profile, ensure_ascii=False, indent=2, default=_json_default),
        encoding="utf-8",
    )


def load_profile(user_id: Any, dataset_id: str) -> dict[str, Any] | None:
    path = profile_path(user_id, dataset_id)
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def dataset_exists(user_id: Any, dataset_id: str) -> bool:
    base = dataset_dir(user_id, dataset_id)
    return any((base / name).is_file() for name in ("data.xlsx", "data.xls", "data.csv"))


def session_path(user_id: Any, session_id: str) -> Path:
    return _sessions_root(user_id) / f"{session_id}.json"


def load_session(user_id: Any, session_id: str) -> dict[str, Any] | None:
    path = session_path(user_id, session_id)
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def save_session(user_id: Any, session_id: str, state: dict[str, Any]) -> None:
    state["updated_at"] = datetime.now(timezone.utc).isoformat()
    path = session_path(user_id, session_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(state, ensure_ascii=False, indent=2, default=_json_default),
        encoding="utf-8",
    )


def create_session_state(
    *,
    user_id: Any,
    session_id: str,
    dataset_id: str | None = None,
    profile: dict[str, Any] | None = None,
) -> dict[str, Any]:
    active_sheet = None
    if profile:
        active_sheet = profile.get("active_sheet")
    return {
        "session_id": session_id,
        "user_id": _user_key(user_id),
        "dataset_id": dataset_id,
        "active_sheet": active_sheet,
        "profile": profile,
        "messages": [],
        "cells": [],
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
