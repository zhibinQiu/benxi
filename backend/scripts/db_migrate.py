#!/usr/bin/env python3
"""显式执行全量 schema 迁移（拉代码后 schema 版本变化时可用）。"""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.database import SessionLocal, engine  # noqa: E402
from app.db_bootstrap import run_seed_bootstrap  # noqa: E402
from app.schema_migrate import run_all_schema_migrations  # noqa: E402


def main() -> None:
    print("运行全量 schema 迁移…")
    run_all_schema_migrations(engine)
    db = SessionLocal()
    try:
        run_seed_bootstrap(db)
    finally:
        db.close()
    print("完成。")


if __name__ == "__main__":
    main()
