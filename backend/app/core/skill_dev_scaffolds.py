"""Skill 脚手架模板 — 供 skill_dev_playbook.py 使用。"""

from __future__ import annotations

_FETCH_UTILS_SCAFFOLD = '''"""网页 HTML 内存分析 — 只产出摘要，不持久化原文。"""
from __future__ import annotations

import re
from html import unescape
from html.parser import HTMLParser

_MAX_SNIPPET = 280
_HEADING_TAGS = frozenset({"h1", "h2", "h3", "h4", "h5", "h6"})
_SKIP_TAGS = frozenset({"script", "style", "noscript", "nav", "footer", "header"})


class _HtmlAnalyzer(HTMLParser):
    """轻量 HTML 分析（纯 stdlib，无需 bs4/lxml）。"""
    def __init__(self) -> None:
        super().__init__()
        self.title = ""
        self.headings: list[str] = []
        self._body_parts: list[str] = []
        self._tag_stack: list[str] = []
        self._skip_depth = 0
        self._in_title = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        t = tag.lower()
        self._tag_stack.append(t)
        if t == "title":
            self._in_title = True
        if t in _SKIP_TAGS:
            self._skip_depth += 1

    def handle_endtag(self, tag: str) -> None:
        t = tag.lower()
        if self._tag_stack and self._tag_stack[-1] == t:
            self._tag_stack.pop()
        if t == "title":
            self._in_title = False
        if t in _SKIP_TAGS and self._skip_depth > 0:
            self._skip_depth -= 1

    def handle_data(self, data: str) -> None:
        text = _clean(data)
        if not text:
            return
        if self._in_title:
            self.title += text
        elif self._skip_depth == 0:
            tag = self._tag_stack[-1] if self._tag_stack else ""
            if tag in _HEADING_TAGS:
                if text not in self.headings:
                    self.headings.append(text)
            else:
                self._body_parts.append(text)


def _clean(text: str) -> str:
    return unescape(re.sub(r"\\s+", " ", (text or ""))).strip()


def analyze_html(html: str) -> dict[str, object]:
    parser = _HtmlAnalyzer()
    try:
        parser.feed(html or "")
    except Exception:
        pass
    title = _clean(parser.title) or "（无 title）"
    snippet = " ".join(parser._body_parts)[:_MAX_SNIPPET] or "（无摘要）"
    return {"title": title, "headings": parser.headings[:6], "snippet": snippet}


def build_conclusion(url: str, data: dict[str, object]) -> str:
    headings = data.get("headings") or []
    heading_text = "、".join(headings[:4]) if headings else "（无明显标题）"
    return (
        f"URL：{url}；标题：{data.get('title')}；主要标题：{heading_text}；"
        f"正文摘要：{data.get('snippet')}"
    )
'''

_MAIN_PY_URL_SCAFFOLD = '''"""发展技能入口 — 平台沙箱执行；结论须 skill_runtime.finish 输出。"""
from __future__ import annotations

import sys

import skill_runtime

from fetch_utils import analyze_html, build_conclusion


def main() -> None:
    url = (sys.argv[1] if len(sys.argv) > 1 else "").strip()
    if not url.startswith(("http://", "https://")):
        skill_runtime.finish("Usage: pass an https:// URL as run_skill_script args")
        return
    try:
        html = skill_runtime.fetch_text(url)
        data = analyze_html(html)
        skill_runtime.finish(build_conclusion(url, data))
    except Exception as exc:
        skill_runtime.finish(f"Fetch failed: {exc}")


if __name__ == "__main__":
    main()
'''

_MAIN_PY_GENERIC_SCAFFOLD = '''"""发展技能入口 — 平台沙箱执行；结论须 skill_runtime.finish 输出。"""
from __future__ import annotations

import skill_runtime


def main() -> None:
    skill_runtime.finish("脚本已执行；请根据 SKILL.md 与调研材料完善解析逻辑")


if __name__ == "__main__":
    main()
'''


def default_fetch_utils_scaffold() -> str:
    return _FETCH_UTILS_SCAFFOLD


def default_main_py_scaffold(*, needs_url: bool = False) -> str:
    return _MAIN_PY_URL_SCAFFOLD if needs_url else _MAIN_PY_GENERIC_SCAFFOLD
