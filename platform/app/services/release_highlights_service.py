"""从 RELEASE.md 解析最新版本的功能更新与问题修复，供登录后弹窗展示。"""

from __future__ import annotations

import re
from typing import Any

from app.services.system_docs_service import _repo_root

_SECTION_RE = re.compile(
    r"^##\s+(\d+\.\d+\.\d+)（v[^）]+）\s*[—–-]\s*(.+)$",
    re.MULTILINE,
)
_ITEM_RE = re.compile(r"^- \*\*(.+?)\*\*[：:]\s*(.+)$", re.MULTILINE)
_FIX_TITLE_HINTS = ("修复", "Bug", "bug", "问题", "测试", "清理", "收敛", "精简")


def _is_fix_item(title: str, summary: str) -> bool:
    if any(hint in title for hint in _FIX_TITLE_HINTS):
        return True
    head = summary[:24]
    return "修复" in head or "bug" in head.lower()


def _parse_latest_section(md: str) -> tuple[str, str, list[str]] | None:
    match = _SECTION_RE.search(md)
    if not match:
        return None
    version = match.group(1).strip()
    subtitle = match.group(2).strip()
    start = match.end()
    next_heading = md.find("\n## ", start)
    body = md[start:next_heading] if next_heading >= 0 else md[start:]
    lines = [line for line in body.splitlines() if line.startswith("- ")]
    return version, subtitle, lines


def _parse_items(lines: list[str]) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    features: list[dict[str, str]] = []
    fixes: list[dict[str, str]] = []
    for line in lines:
        item_match = _ITEM_RE.match(line)
        if not item_match:
            continue
        title = item_match.group(1).strip()
        summary = item_match.group(2).strip()
        entry = {"title": title, "summary": summary}
        if _is_fix_item(title, summary):
            fixes.append(entry)
        else:
            features.append(entry)
    return features, fixes


def load_release_highlights() -> dict[str, Any] | None:
    """读取仓库 RELEASE.md 中最新一条版本说明。"""
    release_path = _repo_root() / "RELEASE.md"
    if not release_path.is_file():
        return None
    md = release_path.read_text(encoding="utf-8")
    parsed = _parse_latest_section(md)
    if not parsed:
        return None
    version, subtitle, lines = parsed
    features, fixes = _parse_items(lines)
    if not features and not fixes:
        return None
    return {
        "version": version,
        "subtitle": subtitle,
        "features": features,
        "fixes": fixes,
    }
