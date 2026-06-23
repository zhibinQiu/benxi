"""web-page-insight 入口 — 拉取公开 URL 并在内存中生成分析结论。"""

from __future__ import annotations

import sys

import skill_runtime

from fetch_utils import analyze_html, build_conclusion


def main() -> None:
    if len(sys.argv) < 2:
        skill_runtime.finish("用法：main.py <https://...>")
        return
    url = sys.argv[1].strip()
    if not url.startswith(("http://", "https://")):
        skill_runtime.finish("请提供以 http:// 或 https:// 开头的 URL")
        return
    try:
        html = skill_runtime.fetch_text(url)
        data = analyze_html(html)
        skill_runtime.finish(build_conclusion(url, data))
    except Exception as exc:
        skill_runtime.finish(f"抓取或分析失败：{exc}")


if __name__ == "__main__":
    main()
