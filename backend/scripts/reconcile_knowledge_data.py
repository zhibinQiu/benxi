#!/usr/bin/env python3
"""知识库与文档存储一致性对账（干跑 / 应用）。

用法:
  cd platform && python scripts/reconcile_knowledge_data.py           # 仅统计
  cd platform && python scripts/reconcile_knowledge_data.py --apply   # 写库 + 清 KnowFlow 残留
  cd platform && python scripts/reconcile_knowledge_data.py --apply --purge-minio
  cd platform && python scripts/reconcile_knowledge_data.py --apply --purge-kbs
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.database import SessionLocal
from app.services.knowledge_data_reconcile_service import run_full_reconcile


def main() -> int:
    parser = argparse.ArgumentParser(description="知识库与文档存储一致性对账")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="应用清理（默认仅干跑统计）",
    )
    parser.add_argument(
        "--purge-minio",
        action="store_true",
        help="删除 MinIO 中无平台文档绑定的 docs/{id}/ 前缀（需 --apply）",
    )
    parser.add_argument(
        "--purge-kbs",
        action="store_true",
        help="删除未在 ragflow_scope_datasets 登记的 KnowFlow 知识库",
    )
    parser.add_argument(
        "--no-repair-library",
        action="store_true",
        help="跳过文档库 scope ↔ dataset 错位修复",
    )
    args = parser.parse_args()

    db = SessionLocal()
    try:
        report = run_full_reconcile(
            db,
            dry_run=not args.apply,
            purge_minio=args.purge_minio,
            repair_library=not args.no_repair_library,
            purge_unregistered_kbs=args.purge_kbs,
        )
        if args.apply:
            db.commit()
        else:
            db.rollback()
        print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
        return 0 if not report.errors else 1
    except Exception as exc:
        db.rollback()
        print(f"对账失败: {exc}", file=sys.stderr)
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
