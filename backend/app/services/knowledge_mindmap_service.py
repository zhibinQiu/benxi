"""知识检索思维导图：本地 Markdown 结构回退（KnowFlow 对齐）。"""

from __future__ import annotations

import re


def _strip_citations(text: str) -> str:
    return re.sub(r"\[\d+\]", "", text or "").replace("**", "").strip()


def _sanitize_label(text: str, *, max_len: int = 48) -> str:
    cleaned = _strip_citations(text)
    cleaned = re.sub(r'[()[\]{}<>#;:"\'|]', " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    if not cleaned:
        return "要点"
    if len(cleaned) > max_len:
        return cleaned[: max_len - 1] + "…"
    return cleaned


def build_mindmap_from_answer(question: str, answer: str) -> str | None:
    root = _sanitize_label(question, max_len=36)
    body = _strip_citations(answer)
    if not body:
        return None

    lines = ["mindmap", f"  root(({root}))"]
    last_header_depth = 2

    for raw_line in body.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        header = re.match(r"^(#{1,4})\s+(.+)", line)
        if header:
            level = len(header.group(1))
            label = _sanitize_label(header.group(2))
            depth = min(level + 1, 4)
            last_header_depth = depth
            lines.append("  " * depth + label)
            continue
        bullet = re.match(r"^[-*+]\s+(.+)", line)
        if bullet:
            depth = min(last_header_depth + 1, 5)
            lines.append("  " * depth + _sanitize_label(bullet.group(1)))
            continue
        numbered = re.match(r"^\d+[.)]\s+(.+)", line)
        if numbered:
            depth = min(last_header_depth + 1, 5)
            lines.append("  " * depth + _sanitize_label(numbered.group(1)))

    if len(lines) <= 2:
        sentences = [
            _sanitize_label(part, max_len=40)
            for part in re.split(r"[。！？\n]+", body)
            if len(part.strip()) > 4
        ][:6]
        for sentence in sentences:
            lines.append(f"    {sentence}")

    return "\n".join(lines) if len(lines) > 2 else None
