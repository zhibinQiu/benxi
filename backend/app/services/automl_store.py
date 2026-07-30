"""自动化机器学习 — 本地文件存储（数据集、训练 run）。"""

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
    raw = (settings.automl_storage_dir or "").strip()
    if raw:
        return Path(raw).expanduser().resolve()
    return (_PLATFORM_DIR / ".run" / "automl").resolve()


def _user_root(user_id: Any) -> Path:
    root = _storage_root() / _user_key(user_id)
    root.mkdir(parents=True, exist_ok=True)
    return root


def datasets_root(user_id: Any) -> Path:
    root = _user_root(user_id) / "datasets"
    root.mkdir(parents=True, exist_ok=True)
    return root


def runs_root(user_id: Any) -> Path:
    root = _user_root(user_id) / "runs"
    root.mkdir(parents=True, exist_ok=True)
    return root


def new_dataset_id() -> str:
    return uuid.uuid4().hex


def new_run_id() -> str:
    return uuid.uuid4().hex


def dataset_dir(user_id: Any, dataset_id: str) -> Path:
    return datasets_root(user_id) / dataset_id


def run_dir(user_id: Any, run_id: str) -> Path:
    return runs_root(user_id) / run_id


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=_json_default),
        encoding="utf-8",
    )


def read_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def save_dataset_file(
    user_id: Any,
    *,
    dataset_id: str,
    filename: str,
    content: bytes,
) -> Path:
    d = dataset_dir(user_id, dataset_id)
    d.mkdir(parents=True, exist_ok=True)
    dest = d / "data.csv"
    dest.write_bytes(content)
    write_json(
        d / "meta.json",
        {
            "dataset_id": dataset_id,
            "filename": filename,
            "bytes": len(content),
            "created_at": datetime.now(timezone.utc).isoformat(),
        },
    )
    return dest


def dataset_csv_path(user_id: Any, dataset_id: str) -> Path | None:
    path = dataset_dir(user_id, dataset_id) / "data.csv"
    return path if path.is_file() else None


def init_run_dir(user_id: Any, run_id: str, config: dict[str, Any]) -> Path:
    d = run_dir(user_id, run_id)
    if d.exists():
        shutil.rmtree(d)
    d.mkdir(parents=True, exist_ok=True)
    write_json(d / "config.json", config)
    write_json(
        d / "status.json",
        {
            "status": "pending",
            "progress": 0,
            "message": None,
            "error_message": None,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "started_at": None,
            "finished_at": None,
        },
    )
    return d


def update_run_status(
    user_id: Any,
    run_id: str,
    *,
    status: str | None = None,
    progress: int | None = None,
    message: str | None = None,
    error_message: str | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    d = run_dir(user_id, run_id)
    path = d / "status.json"
    current = read_json(path) or {}
    now = datetime.now(timezone.utc).isoformat()
    if status is not None:
        current["status"] = status
        if status == "running" and not current.get("started_at"):
            current["started_at"] = now
        if status in ("done", "failed", "cancelled"):
            current["finished_at"] = now
            if status == "done":
                current["progress"] = 100
    if progress is not None:
        current["progress"] = int(progress)
    if message is not None:
        current["message"] = message
    if error_message is not None:
        current["error_message"] = error_message
    if extra:
        current.update(extra)
    write_json(path, current)
    return current


def list_run_ids(user_id: Any, *, limit: int = 50) -> list[str]:
    root = runs_root(user_id)
    dirs = [p for p in root.iterdir() if p.is_dir() and (p / "config.json").is_file()]
    dirs.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return [p.name for p in dirs[: max(1, limit)]]


def remove_run(user_id: Any, run_id: str) -> None:
    d = run_dir(user_id, run_id)
    if d.exists():
        shutil.rmtree(d, ignore_errors=True)
