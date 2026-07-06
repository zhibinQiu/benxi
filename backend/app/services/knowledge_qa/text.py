"""Knowledge QA — 回答文本后处理."""

from __future__ import annotations


def strip_meta_footer(text: str) -> str:
    lines = []
    for line in (text or "").splitlines():
        if "以上内容来自" in line and "检索" in line:
            continue
        if "知识服务就绪" in line:
            continue
        lines.append(line)
    return "\n".join(lines).strip()
