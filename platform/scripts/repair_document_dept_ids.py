#!/usr/bin/env python3
"""修复文档 dept_id：与所有者所属部门对齐（每人至多一个部门）。"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy import select

from app.core.user_department import user_department_id
from app.database import SessionLocal
from app.models.document import Document


def main() -> int:
    db = SessionLocal()
    fixed_null = 0
    fixed_mismatch = 0
    fixed_company = 0
    try:
        docs = list(
            db.scalars(
                select(Document).where(Document.deleted_at.is_(None))
            ).all()
        )
        for doc in docs:
            owner_dept = user_department_id(db, doc.owner_id)
            if not owner_dept:
                continue
            scope = (doc.scope or "personal").lower()
            if doc.dept_id is None:
                doc.dept_id = owner_dept
                fixed_null += 1
                continue
            if scope == "company" and doc.dept_id != owner_dept:
                doc.scope = "team"
                doc.dept_id = owner_dept
                fixed_company += 1
                continue
            if scope in ("personal", "team") and doc.dept_id != owner_dept:
                doc.dept_id = owner_dept
                fixed_mismatch += 1
        db.commit()
        print(
            f"已修复文档部门：补全 dept_id {fixed_null} 条，"
            f"校正 personal/team 不一致 {fixed_mismatch} 条，"
            f"公司库误挂改小组 {fixed_company} 条"
        )
        return 0
    except Exception as exc:
        db.rollback()
        print(f"修复失败: {exc}", file=sys.stderr)
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
