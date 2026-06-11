"""知识库与文档存储一致性对账：孤儿清理、增量复用原则落地。

原则：存在且已索引则复用（checksum + dataset）；仅清理无平台绑定或已失效的远端/对象。
"""

from __future__ import annotations

import logging
import re
import uuid
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.document import Document, DocumentVersion
from app.models.org import User
from app.models.ragflow_document_link import RagflowDocumentLink
from app.models.ragflow_document_mirror_link import RagflowDocumentMirrorLink
from app.models.ragflow_document_version_link import RagflowDocumentVersionLink
from app.services.documents.crud import is_version_uploaded

logger = logging.getLogger(__name__)

_DOC_PREFIX_RE = re.compile(r"^docs/([0-9a-f-]{36})/")


@dataclass
class ReconcileReport:
    """对账结果摘要（apply=False 时仅统计，不写库/不删对象）。"""

    dry_run: bool = True
    stale_knowflow_links_removed: int = 0
    orphan_document_links_dropped: int = 0
    unregistered_kbs_removed: int = 0
    library_alignment: dict[str, Any] = field(default_factory=dict)
    zero_byte_versions: list[str] = field(default_factory=list)
    minio_orphan_doc_ids: list[str] = field(default_factory=list)
    minio_orphan_keys_deleted: int = 0
    shared_rag_refs_preserved: int = 0
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "dry_run": self.dry_run,
            "stale_knowflow_links_removed": self.stale_knowflow_links_removed,
            "orphan_document_links_dropped": self.orphan_document_links_dropped,
            "unregistered_kbs_removed": self.unregistered_kbs_removed,
            "library_alignment": self.library_alignment,
            "zero_byte_versions": self.zero_byte_versions,
            "minio_orphan_doc_ids": self.minio_orphan_doc_ids,
            "minio_orphan_keys_deleted": self.minio_orphan_keys_deleted,
            "shared_rag_refs_preserved": self.shared_rag_refs_preserved,
            "errors": self.errors,
        }


def should_force_knowledge_index_after_upload(
    db: Session,
    *,
    document_id: uuid.UUID,
    version_id: uuid.UUID | None,
) -> bool:
    """上传完成后是否强制重同步：当前版本已索引则仅刷新 ACL（force=False）。"""
    if not version_id:
        return True
    vl = db.scalar(
        select(RagflowDocumentVersionLink).where(
            RagflowDocumentVersionLink.platform_version_id == version_id
        )
    )
    if not vl:
        return True
    if not (vl.ragflow_document_id or "").strip():
        return True
    if vl.index_completed_at is None:
        return True
    ver = db.get(DocumentVersion, version_id)
    if not ver or not is_version_uploaded(ver):
        return True
    return False


def scan_zero_byte_versions(db: Session) -> list[str]:
    """未成功上传（file_size=0）的版本 ID。"""
    rows = db.scalars(
        select(DocumentVersion.id).where(DocumentVersion.file_size <= 0)
    ).all()
    return [str(v) for v in rows]


def scan_minio_orphan_document_ids(db: Session) -> list[str]:
    """MinIO docs/ 前缀下无对应平台文档或文档已删的 document_id。"""
    settings = get_settings()
    try:
        import boto3
        from botocore.client import Config

        scheme = "https" if settings.minio_secure else "http"
        client = boto3.client(
            "s3",
            endpoint_url=f"{scheme}://{settings.minio_endpoint}",
            aws_access_key_id=settings.minio_access_key,
            aws_secret_access_key=settings.minio_secret_key,
            region_name=settings.minio_region,
            config=Config(signature_version="s3v4"),
        )
        paginator = client.get_paginator("list_objects_v2")
        orphan_ids: set[str] = set()
        for page in paginator.paginate(Bucket=settings.minio_bucket, Prefix="docs/"):
            for obj in page.get("Contents") or []:
                key = obj.get("Key") or ""
                m = _DOC_PREFIX_RE.match(key)
                if not m:
                    continue
                doc_id = m.group(1)
                try:
                    uid = uuid.UUID(doc_id)
                except ValueError:
                    orphan_ids.add(doc_id)
                    continue
                doc = db.get(Document, uid)
                if doc is None or doc.deleted_at is not None:
                    orphan_ids.add(doc_id)
        return sorted(orphan_ids)
    except Exception as exc:
        logger.warning("MinIO 孤儿扫描失败: %s", exc)
        return []


def purge_minio_orphan_documents(
    db: Session, doc_ids: list[str], *, dry_run: bool = True
) -> int:
    from app.storage.object_store import get_object_store

    deleted = 0
    store = get_object_store()
    for raw in doc_ids:
        prefix = f"docs/{raw}/"
        if dry_run:
            continue
        try:
            store.delete_prefix(prefix)
            deleted += 1
        except Exception as exc:
            logger.warning("删除 MinIO 前缀 %s 失败: %s", prefix, exc)
    return deleted


def drop_orphan_canonical_links(db: Session, *, kf=None) -> int:
    """删除指向已不存在 KnowFlow dataset 的 canonical link（需 kf 客户端）。"""
    from app.services.knowflow_catalog_service import _drop_orphan_document_links

    if kf is None:
        from app.integrations.knowflow_client import get_knowflow_client

        kf = get_knowflow_client()
    return _drop_orphan_document_links(db, kf)


def run_full_reconcile(
    db: Session,
    *,
    dry_run: bool = True,
    purge_minio: bool = False,
    repair_library: bool = True,
    purge_unregistered_kbs: bool = False,
    actor: User | None = None,
) -> ReconcileReport:
    """全量对账：统计并可选应用清理（登录 reconcile 的子集超集，适合运维手动执行）。"""
    report = ReconcileReport(dry_run=dry_run)
    settings = get_settings()

    if not settings.knowflow_enabled:
        report.errors.append("KNOWFLOW_ENABLED=false，跳过 KnowFlow 对账")
        report.zero_byte_versions = scan_zero_byte_versions(db)
        report.minio_orphan_doc_ids = scan_minio_orphan_document_ids(db)
        return report

    try:
        from app.domains.knowledge.gateway import knowledge

        from app.models.document import DocumentStatus

        stale = 0
        for link in db.scalars(select(RagflowDocumentLink)).all():
            doc = db.get(Document, link.platform_document_id)
            if (
                doc is None
                or doc.deleted_at is not None
                or doc.status != DocumentStatus.active.value
            ):
                stale += 1
        report.stale_knowflow_links_removed = stale
        if not dry_run and stale:
            report.stale_knowflow_links_removed = knowledge.purge_stale_links(db)

        if purge_unregistered_kbs:
            from app.services.ragflow_scope_service import (
                purge_unregistered_knowledge_bases,
            )

            if dry_run:
                report.unregistered_kbs_removed = 0  # 干跑不枚举远端
            else:
                report.unregistered_kbs_removed = purge_unregistered_knowledge_bases(
                    db
                )

        if repair_library:
            from app.services.document_library_align_service import (
                list_misaligned_ragflow_links,
                repair_document_library_alignment,
            )

            misaligned = list_misaligned_ragflow_links(db)
            if dry_run:
                report.library_alignment = {
                    "misaligned_links": len(misaligned),
                    "repaired": 0,
                }
            else:
                report.library_alignment = repair_document_library_alignment(
                    db, actor=actor
                )

        try:
            if dry_run:
                from app.integrations.knowflow_client import get_knowflow_client
                from app.models.ragflow_scope_dataset import RagflowScopeDataset
                from app.services.knowflow_catalog_service import _visible_dataset_ids

                kf = get_knowflow_client()
                visible = _visible_dataset_ids(kf)
                registered = {
                    reg.ragflow_dataset_id
                    for reg in db.scalars(select(RagflowScopeDataset)).all()
                    if reg.ragflow_dataset_id
                }
                orphan = 0
                for link in db.scalars(select(RagflowDocumentLink)).all():
                    ds = link.dataset_id
                    if ds and ds not in visible and ds not in registered:
                        orphan += 1
                report.orphan_document_links_dropped = orphan
            else:
                report.orphan_document_links_dropped = drop_orphan_canonical_links(db)
                db.flush()
        except Exception as exc:
            report.errors.append(f"orphan link 清理: {exc}")

    except Exception as exc:
        report.errors.append(f"KnowFlow 对账: {exc}")
        logger.exception("知识库对账异常")

    report.zero_byte_versions = scan_zero_byte_versions(db)
    report.minio_orphan_doc_ids = scan_minio_orphan_document_ids(db)

    if purge_minio and report.minio_orphan_doc_ids:
        report.minio_orphan_keys_deleted = purge_minio_orphan_documents(
            db,
            report.minio_orphan_doc_ids,
            dry_run=dry_run,
        )

    return report
