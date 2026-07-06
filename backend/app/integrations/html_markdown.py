"""HTML 转 Markdown，保留段落与列表结构。"""

from __future__ import annotations

import re
from html import escape

import html2text

_BLOCK_TAG = re.compile(
    r"<(?:p|div|h[1-6]|ul|ol|li|br|table|article|section|blockquote)\b",
    re.I,
)


def _plain_text_to_html(text: str) -> str:
    raw = (text or "").strip()
    if not raw:
        return ""
    paras = [p.strip() for p in re.split(r"\n\s*\n+", raw) if p.strip()]
    if len(paras) <= 1 and len(raw) > 100:
        sentences = [s.strip() for s in re.split(r"(?<=[。！？!?])", raw) if s.strip()]
        if len(sentences) > 1:
            merged: list[str] = []
            buf = ""
            chunk_chars = 80 if len(raw) < 800 else 160
            for sent in sentences:
                buf += sent
                if len(buf) >= chunk_chars:
                    merged.append(buf.strip())
                    buf = ""
            if buf.strip():
                merged.append(buf.strip())
            if len(merged) > 1:
                paras = merged
    if not paras:
        paras = [raw]
    return "".join(f"<p>{escape(p)}</p>" for p in paras)


def html_to_markdown(html: str) -> str:
    text = (html or "").strip()
    if not text:
        return ""
    if not _BLOCK_TAG.search(text):
        text = _plain_text_to_html(text)

    converter = html2text.HTML2Text()
    converter.ignore_links = False
    converter.ignore_images = False
    converter.ignore_emphasis = False
    converter.body_width = 0
    converter.single_line_break = False
    converter.wrap_links = False
    md = converter.handle(text).strip()
    return md
