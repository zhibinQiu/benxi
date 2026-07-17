"""双碳咨询获取 — 从官方渠道获取碳市场/政策/排放数据。"""
from __future__ import annotations

import sys

import skill_runtime

from fetch_utils import analyze_html, build_conclusion

_SOURCES: dict[str, tuple[str, ...]] = {
    "price": (
        "https://www.cets.org.cn",
        "https://www.cneeex.com",
    ),
    "policy": (
        "https://www.gov.cn/zhengce/",
        "https://www.ndrc.gov.cn/",
        "https://www.mee.gov.cn/ywgz/ydqhbh/wsqtkz/",
    ),
    "news": (
        "https://www.cenews.com.cn",
        "https://www.tandao.org",
    ),
}


def main() -> None:
    args = sys.argv[1:]
    if not args:
        types = "\n".join(f"  {k}" for k in _SOURCES)
        skill_runtime.finish(f"用法: run_skill_script carbon-consulting <类型>\n类型:\n{types}")
        return

    query_type = args[0].strip().lower()
    keyword = args[1] if len(args) > 1 else ""

    if keyword.startswith(("http://", "https://")):
        try:
            html = skill_runtime.fetch_text(keyword, timeout=15)
            data = analyze_html(html, query_type=query_type)
            skill_runtime.finish(build_conclusion(keyword, data, query_type=query_type))
        except Exception as exc:
            skill_runtime.finish(f"获取指定 URL 失败: {exc}")
        return

    sources = _SOURCES.get(query_type, _SOURCES.get("news", ()))
    conclusions: list[str] = []
    errors: list[str] = []

    for url in sources:
        try:
            html = skill_runtime.fetch_text(url, timeout=10)
            data = analyze_html(html, query_type=query_type)
            conclusions.append(build_conclusion(url, data, query_type=query_type))
        except Exception:
            errors.append(url)

    if conclusions:
        report = "\n\n---\n\n".join(conclusions)
        if errors:
            report += f"\n\n（以下来源暂时无法访问，已跳过：{', '.join(errors)}）"
        skill_runtime.finish(report)
    else:
        skill_runtime.finish(
            f"所有数据源均暂时无法访问，无法获取 [{query_type}] 数据。"
            f"尝试的来源：{', '.join(sources)}"
        )


if __name__ == "__main__":
    main()
