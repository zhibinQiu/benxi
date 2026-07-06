"""单文档版本 Git 仓：上传时提交解析文本，对比时用 git diff。"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import threading
import uuid
from pathlib import Path

from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.document import DocumentVersion
from app.services.compare_service import load_parsed_version
from app.services.document_version_block_service import ensure_version_blocks

logger = logging.getLogger(__name__)

CONTENT_FILE = "content.txt"
_repo_locks: dict[uuid.UUID, threading.Lock] = {}
_lock_guard = threading.Lock()


def _require_git() -> str:
    git = shutil.which("git")
    if not git:
        raise RuntimeError("未找到 git 可执行文件，无法做版本对比")
    return git


def _repo_root(document_id: uuid.UUID) -> Path:
    root = get_settings().resolved_document_git_repos_root
    root.mkdir(parents=True, exist_ok=True)
    return root / str(document_id)


def _repo_lock(document_id: uuid.UUID) -> threading.Lock:
    with _lock_guard:
        if document_id not in _repo_locks:
            _repo_locks[document_id] = threading.Lock()
        return _repo_locks[document_id]


def _tag_name(version_no: int) -> str:
    return f"v{version_no}"


def _git(repo: Path, *args: str, check: bool = True) -> str:
    _require_git()
    env = {
        **os.environ,
        "GIT_TERMINAL_PROMPT": "0",
        "GIT_AUTHOR_NAME": "benxi-platform",
        "GIT_AUTHOR_EMAIL": "platform@local",
        "GIT_COMMITTER_NAME": "benxi-platform",
        "GIT_COMMITTER_EMAIL": "platform@local",
    }
    result = subprocess.run(
        ["git", *args],
        cwd=repo,
        capture_output=True,
        text=True,
        env=env,
    )
    if check and result.returncode != 0:
        msg = (result.stderr or result.stdout or "").strip()
        raise RuntimeError(msg or f"git {' '.join(args)} failed")
    return (result.stdout or "").strip()


def ensure_repo(document_id: uuid.UUID) -> Path:
    repo = _repo_root(document_id)
    if (repo / ".git").is_dir():
        return repo
    with _repo_lock(document_id):
        repo.mkdir(parents=True, exist_ok=True)
        if not (repo / ".git").is_dir():
            _git(repo, "init")
        if not (repo / ".gitignore").exists():
            (repo / ".gitignore").write_text(".DS_Store\n", encoding="utf-8")
            _git(repo, "add", ".gitignore")
            _git(repo, "commit", "-m", "init document repo")
    return repo


def _tag_exists(repo: Path, tag: str) -> bool:
    result = subprocess.run(
        ["git", "rev-parse", "-q", "--verify", f"refs/tags/{tag}"],
        cwd=repo,
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


def sync_version_to_git(db: Session, version: DocumentVersion) -> str:
    """将版本解析文本写入 Git 并打 tag v{version_no}，返回 commit hash。"""
    if version.file_size <= 0:
        raise ValueError("版本文件未上传")

    repo = ensure_repo(version.document_id)
    tag = _tag_name(version.version_no)
    if _tag_exists(repo, tag):
        return _git(repo, "rev-parse", tag)

    blocks = ensure_version_blocks(db, version)
    if blocks:
        full_text = "\n\n".join(b.text for b in blocks).strip()
    else:
        parsed = load_parsed_version(db, version)
        if parsed.parse_quality == "unsupported" and not parsed.full_text:
            raise ValueError(parsed.warning or "无法解析文档文本，暂不支持对比")
        full_text = parsed.full_text

    message = f"version {version.version_no}"
    if version.change_description:
        message = f"{message}: {version.change_description[:200]}"

    with _repo_lock(version.document_id):
        if _tag_exists(repo, tag):
            return _git(repo, "rev-parse", tag)
        (repo / CONTENT_FILE).write_text(full_text, encoding="utf-8")
        _git(repo, "add", CONTENT_FILE)
        _git(repo, "commit", "-m", message)
        _git(repo, "tag", tag, "-m", message)
        return _git(repo, "rev-parse", "HEAD")


def git_diff_versions(
    document_id: uuid.UUID,
    from_version_no: int,
    to_version_no: int,
) -> str:
    """返回 git diff 统一 diff 文本（左=from，右=to）。"""
    repo = ensure_repo(document_id)
    left = _tag_name(from_version_no)
    right = _tag_name(to_version_no)
    for tag in (left, right):
        if not _tag_exists(repo, tag):
            raise ValueError(f"Git 标签不存在: {tag}")
    return _git(repo, "diff", left, right, "--", CONTENT_FILE, check=False)


def parse_git_unified_diff(diff_text: str) -> list[dict]:
    """将 git unified diff 转为前端 diff_items 结构。"""
    if not (diff_text or "").strip():
        return []

    items: list[dict] = []
    left_lines: list[str] = []
    right_lines: list[str] = []

    def flush() -> None:
        nonlocal left_lines, right_lines
        if not left_lines and not right_lines:
            return
        left = "\n".join(left_lines).strip() or None
        right = "\n".join(right_lines).strip() or None
        if left and right:
            dtype = "modify"
        elif left:
            dtype = "delete"
        else:
            dtype = "add"
        items.append(
            {
                "diff_type": dtype,
                "text_left": left,
                "text_right": right,
                "anchor_json": {
                    "page": 1,
                    "bbox": None,
                    "kind": "git_hunk",
                },
            }
        )
        left_lines = []
        right_lines = []

    for raw in diff_text.splitlines():
        if raw.startswith("diff --") or raw.startswith("index "):
            continue
        if raw.startswith("---") or raw.startswith("+++"):
            continue
        if raw.startswith("@@"):
            flush()
            continue
        if raw.startswith("-") and not raw.startswith("---"):
            left_lines.append(raw[1:])
        elif raw.startswith("+") and not raw.startswith("+++"):
            right_lines.append(raw[1:])
        elif raw.startswith(" "):
            flush()

    flush()
    return items


def compute_version_diff_via_git(
    db: Session,
    from_version: DocumentVersion,
    to_version: DocumentVersion,
) -> tuple[list[dict], dict]:
    """确保 Git 标签存在并执行 diff，返回 (diff_items, payload_meta)。"""
    sync_version_to_git(db, from_version)
    sync_version_to_git(db, to_version)
    diff_text = git_diff_versions(
        from_version.document_id,
        from_version.version_no,
        to_version.version_no,
    )
    items = parse_git_unified_diff(diff_text)
    payload = {
        "engine": "git",
        "from_version_no": from_version.version_no,
        "to_version_no": to_version.version_no,
        "from_file_name": from_version.file_name,
        "to_file_name": to_version.file_name,
        "git_diff_chars": len(diff_text),
    }
    return items, payload


def remove_document_git_repo(document_id: uuid.UUID) -> None:
    """删除文档时清理 Git 仓（best-effort）。"""
    repo = _repo_root(document_id)
    if repo.is_dir():
        shutil.rmtree(repo, ignore_errors=True)
