#!/usr/bin/env python3
"""清空平台全部文档及 KnowFlow/RAGFlow 切片索引（不可恢复）。

用法:
  cd platform && python scripts/purge_all_documents.py --yes
"""

from __future__ import annotations

import argparse
import shutil
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy import delete, func, select

from app.config import get_settings
from app.database import SessionLocal
from app.integrations.ragflow_client import RagflowClient
from app.integrations.ragflow_llm_template import _mysql_exec
from app.models.document import Document, DocumentLibraryFolder
from app.models.ragflow_document_link import RagflowDocumentLink
from app.models.ragflow_document_mirror_link import RagflowDocumentMirrorLink
from app.models.ragflow_document_version_link import RagflowDocumentVersionLink
from app.services.documents.lifecycle import (
    _purge_document_external_resources_by_id,
    purge_document_completely,
)
from app.services.ragflow_sync_service import (
    KnowflowDeleteTarget,
    _delete_ragflow_documents_mysql,
    schedule_knowflow_deletes,
)
from app.storage.object_store import get_object_store


def _purge_all_ragflow_documents_mysql() -> bool:
    sql = """
DELETE FROM child_chunk;
DELETE FROM parent_chunk;
DELETE FROM file2document;
DELETE FROM document;
"""
    return _mysql_exec(sql)


def _api_delete_targets(targets: list[KnowflowDeleteTarget]) -> int:
    if not targets:
        return 0
    client = RagflowClient()
    ok = 0
    if not client.health_ok():
        return 0
    by_dataset: dict[str, list[str]] = {}
    for t in targets:
        by_dataset.setdefault(t.dataset_id, []).append(t.ragflow_document_id)
    for ds_id, ids in by_dataset.items():
        batch = 20
        for i in range(0, len(ids), batch):
            chunk = ids[i : i + batch]
            try:
                client.delete_documents(ds_id, chunk)
                ok += len(chunk)
            except Exception:
                _delete_ragflow_documents_mysql(chunk)
    return ok


def main() -> int:
    parser = argparse.ArgumentParser(description="清空全部文档与切片索引")
    parser.add_argument(
        "--yes",
        action="store_true",
        help="确认执行（不可恢复）",
    )
    args = parser.parse_args()
    if not args.yes:
        print("请加 --yes 确认执行全量删除", file=sys.stderr)
        return 2

    settings = get_settings()
    db = SessionLocal()
    all_targets: list[KnowflowDeleteTarget] = []
    doc_ids: list = []

    try:
        docs = list(db.scalars(select(Document)).all())
        print(f"平台文档数: {len(docs)}")

        for doc in docs:
            targets = purge_document_completely(
                db, doc, defer_knowflow=True, skip_external=True
            )
            all_targets.extend(targets)
            doc_ids.append(doc.id)

        folder_count = db.scalar(select(func.count()).select_from(DocumentLibraryFolder)) or 0
        db.execute(delete(DocumentLibraryFolder))
        db.commit()
        print(f"已删除文档: {len(docs)}，文件夹: {folder_count}")

        # 兜底：清理残留映射
        for model in (
            RagflowDocumentVersionLink,
            RagflowDocumentLink,
            RagflowDocumentMirrorLink,
        ):
            n = db.scalar(select(func.count()).select_from(model)) or 0
            if n:
                db.execute(delete(model))
                print(f"清理残留 {model.__tablename__}: {n}")
        db.commit()

        # MinIO 平台对象
        store = get_object_store()
        try:
            store.delete_prefix("docs/")
            print("已清空 MinIO docs/ 前缀")
        except Exception as exc:
            print(f"MinIO 清理警告: {exc}")

        # 本地 Git 仓
        git_root = ROOT / "data" / "document-git-repos"
        if git_root.is_dir():
            for child in git_root.iterdir():
                if child.is_dir():
                    shutil.rmtree(child, ignore_errors=True)
            print(f"已清空本地 Git 仓: {git_root}")

        # KnowFlow 远端（先 API，失败走 MySQL）
        unique: dict[tuple[str, str], KnowflowDeleteTarget] = {}
        for t in all_targets:
            unique[(t.dataset_id, t.ragflow_document_id)] = t
        pending = list(unique.values())
        api_ok = _api_delete_targets(pending)
        print(f"KnowFlow API 删除文档: {api_ok}/{len(pending)}")

        # 全量清空 RAGFlow 切片表（含未映射的孤儿文档）
        if settings.knowflow_enabled:
            if _purge_all_ragflow_documents_mysql():
                print("已清空 RAGFlow MySQL 全部 document/chunk 记录")
            else:
                print("RAGFlow MySQL 全量清理失败，请检查连接", file=sys.stderr)

        # 异步兜底（API 未覆盖的个别文档）
        if pending:
            schedule_knowflow_deletes(pending)
            time.sleep(2)

        for did in doc_ids:
            try:
                _purge_document_external_resources_by_id(did)
            except Exception:
                pass

        # 校验
        remain_docs = db.scalar(select(func.count()).select_from(Document)) or 0
        remain_links = db.scalar(
            select(func.count()).select_from(RagflowDocumentVersionLink)
        ) or 0
        remain_folders = db.scalar(
            select(func.count()).select_from(DocumentLibraryFolder)
        ) or 0
        print(
            f"校验 — documents={remain_docs} version_links={remain_links} folders={remain_folders}"
        )
        return 0 if remain_docs == 0 else 1
    except Exception as exc:
        db.rollback()
        print(f"清理失败: {exc}", file=sys.stderr)
        raise
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
