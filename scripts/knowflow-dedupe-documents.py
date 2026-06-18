#!/usr/bin/env python3
"""KnowFlow document 去重：同知识库 + 同名基名 + 同 size 仅保留一条，删除 (N) 重复副本。"""

from __future__ import annotations

import argparse
import os
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "platform"))

_DUP_SUFFIX_RE = re.compile(r"\(\d+\)(\.[^.]+)?$")


def _load_env() -> None:
    env_file = ROOT / "platform" / ".env"
    if not env_file.is_file():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, val = line.split("=", 1)
        os.environ.setdefault(key.strip(), val.strip())


def _base_name(name: str) -> str:
    text = (name or "").strip()
    return _DUP_SUFFIX_RE.sub(lambda m: m.group(1) or "", text).strip()


def main() -> int:
    parser = argparse.ArgumentParser(description="KnowFlow 重复 document 清理")
    parser.add_argument("--apply", action="store_true", help="实际删除（默认 dry-run）")
    parser.add_argument("--limit", type=int, default=500, help="最多删除条数")
    args = parser.parse_args()
    _load_env()

    import pymysql
    from app.integrations.ragflow_client import RagflowClient

    host = os.environ.get("RAGFLOW_MYSQL_HOST", "127.0.0.1")
    port = int(os.environ.get("RAGFLOW_MYSQL_PORT", "5455"))
    password = os.environ.get("RAGFLOW_MYSQL_PASSWORD", "infini_rag_flow")
    db_name = os.environ.get("RAGFLOW_MYSQL_DB", "rag_flow")

    conn = pymysql.connect(
        host=host,
        port=port,
        user="root",
        password=password,
        database=db_name,
        charset="utf8mb4",
    )
    cur = conn.cursor()
    cur.execute(
        """
        SELECT d.id, d.kb_id, d.name, d.size, d.run, d.create_time, kb.name
        FROM document d
        LEFT JOIN knowledgebase kb ON kb.id = d.kb_id
        WHERE d.status = '1'
        ORDER BY d.create_time DESC
        """
    )
    rows = cur.fetchall()
    conn.close()

    groups: dict[tuple[str, str, int], list[dict]] = defaultdict(list)
    for rid, kb_id, name, size, run, created, kb_name in rows:
        base = _base_name(name)
        if not base:
            continue
        groups[(kb_id or "", base, int(size or 0))].append(
            {
                "id": rid,
                "name": name,
                "run": str(run or ""),
                "created": created,
                "kb_name": kb_name or "",
            }
        )

    to_delete: list[tuple[str, str, str]] = []
    for _key, items in groups.items():
        if len(items) <= 1:
            continue

        def rank(item: dict) -> tuple:
            done = 1 if item["run"] == "3" else 0
            return (done, item["created"] or 0)

        keep = max(items, key=rank)
        for item in items:
            if item["id"] == keep["id"]:
                continue
            to_delete.append((item["kb_name"], item["name"], item["id"]))

    to_delete = to_delete[: max(0, args.limit)]
    print(f"重复组数: {sum(1 for v in groups.values() if len(v) > 1)}")
    print(f"待删除 document: {len(to_delete)} ({'apply' if args.apply else 'dry-run'})")
    for kb_name, name, rid in to_delete[:20]:
        print(f"  - [{kb_name}] {name} ({rid})")
    if len(to_delete) > 20:
        print(f"  ... 还有 {len(to_delete) - 20} 条")

    if not args.apply or not to_delete:
        return 0

    rag = RagflowClient()
    deleted = 0
    by_kb: dict[str, list[str]] = defaultdict(list)
    for _kb_name, _name, rid in to_delete:
        cur2 = pymysql.connect(
            host=host,
            port=port,
            user="root",
            password=password,
            database=db_name,
            charset="utf8mb4",
        )
        with cur2.cursor() as c:
            c.execute("SELECT kb_id FROM document WHERE id = %s", (rid,))
            row = c.fetchone()
        cur2.close()
        if row and row[0]:
            by_kb[row[0]].append(rid)

    for kb_id, ids in by_kb.items():
        try:
            rag.delete_documents(kb_id, ids)
            deleted += len(ids)
            print(f"已删除 kb={kb_id} count={len(ids)}")
        except Exception as exc:
            print(f"API 删除失败 kb={kb_id}: {exc}", file=sys.stderr)

    # 校验 API 是否真正删除；未删除则直接清理 MySQL（运维脚本）
    conn = pymysql.connect(
        host=host,
        port=port,
        user="root",
        password=password,
        database=db_name,
        charset="utf8mb4",
    )
    all_ids = [rid for _kb, _name, rid in to_delete]
    placeholders = ",".join(["%s"] * len(all_ids))
    with conn.cursor() as cur:
        cur.execute(
            f"SELECT id FROM document WHERE id IN ({placeholders})",
            all_ids,
        )
        remaining = [row[0] for row in cur.fetchall()]
    if remaining:
        ph2 = ",".join(["%s"] * len(remaining))
        with conn.cursor() as cur:
            cur.execute(
                f"DELETE FROM task WHERE doc_id IN ({ph2})",
                remaining,
            )
            cur.execute(
                f"DELETE FROM document WHERE id IN ({ph2})",
                remaining,
            )
        conn.commit()
        print(f"MySQL 直接清理剩余 document: {len(remaining)}")
        deleted += len(remaining)
    conn.close()

    print(f"共删除 {deleted} 个重复 document")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
