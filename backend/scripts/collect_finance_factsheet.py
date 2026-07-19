#!/usr/bin/env python3
"""采集并输出理财圆桌「事实底稿」Markdown。

用法（在 backend 目录，已激活含 akshare 的环境）：
  python scripts/collect_finance_factsheet.py 000682
  python scripts/collect_finance_factsheet.py 000682 --name 东方电子 -o /tmp/fact.md
  python scripts/collect_finance_factsheet.py 000682 --matrix   # 仅打印数据源矩阵

原则：AKshare / 东财结构化 API 优先；同一指标不重复拉取；新闻类维度留给 web_search。
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path


def _ensure_app_path() -> None:
    root = Path(__file__).resolve().parents[1]
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))


async def _run(code: str, name: str, out: Path | None, matrix_only: bool) -> int:
    from app.services.finance_factsheet import FACT_SOURCE_MATRIX, build_roundtable_fact_sheet

    if matrix_only:
        print("| 维度 | 主源 | 兜底 |")
        print("|------|------|------|")
        for row in FACT_SOURCE_MATRIX:
            print(f"| {row['维度']} | {row['主源']} | {row['兜底']} |")
        return 0

    bundle = await build_roundtable_fact_sheet(code, name, web_extra="")
    md = bundle.get("fact_sheet_md") or ""
    if out:
        out.write_text(md, encoding="utf-8")
        print(f"written: {out} ({len(md)} chars)")
    else:
        print(md)
    return 0


def main() -> int:
    _ensure_app_path()
    parser = argparse.ArgumentParser(description="采集理财事实底稿")
    parser.add_argument("code", help="股票代码，如 000682")
    parser.add_argument("--name", default="", help="股票名称（可选）")
    parser.add_argument("-o", "--output", default="", help="输出 Markdown 路径")
    parser.add_argument("--matrix", action="store_true", help="仅打印数据源矩阵")
    args = parser.parse_args()
    out = Path(args.output) if args.output else None
    return asyncio.run(_run(args.code, args.name, out, args.matrix))


if __name__ == "__main__":
    raise SystemExit(main())
