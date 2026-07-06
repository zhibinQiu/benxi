#!/usr/bin/env python3
"""清理 KnowFlow 中未在平台 ragflow_scope_dataset 登记的知识库（含「部门」等误建库）。"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.database import SessionLocal
from app.services.ragflow_scope_service import purge_unregistered_knowledge_bases


def main() -> int:
    db = SessionLocal()
    try:
        removed = purge_unregistered_knowledge_bases(db)
        db.commit()
        print(f"已清理未登记知识库: {removed} 个")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
