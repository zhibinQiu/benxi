"""单文档版本对比：预计算（V0 / 相邻）与按需异步任务。"""

from __future__ import annotations

import logging
import threading
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.permissions import PermissionLevel, can_access_document
from app.database import SessionLocal
from app.models.document import Document, DocumentVersion
from app.models.document_version_compare import (
    DocumentVersionCompareRelation,
    DocumentVersionDiffItem,
    VersionCompareRelationType,
    VersionCompareStatus,
)
from app.models.org import User
from app.services.version_block_diff_service import compute_block_diffs

logger = logging.getLogger(__name__)


def _ordered_versions(
    db: Session, version_a_id: uuid.UUID, version_b_id: uuid.UUID
) -> tuple[DocumentVersion, DocumentVersion]:
    va = db.get(DocumentVersion, version_a_id)
    vb = db.get(DocumentVersion, version_b_id)
    if not va or not vb:
        from app.core.exceptions import bad_request

        raise bad_request("版本不存在")
    if va.document_id != vb.document_id:
        from app.core.exceptions import bad_request

        raise bad_request("两个版本必须属于同一文档")
    if va.version_no <= vb.version_no:
        return va, vb
    return vb, va


def _require_document_access(
    db: Session, user: User, document: Document, *, level: str | None = None
) -> None:
    if not can_access_document(
        db, user, document, level or PermissionLevel.query.value
    ):
        from app.core.exceptions import forbidden

        raise forbidden("无权访问该文档")


def get_relation_by_pair(
    db: Session,
    document_id: uuid.UUID,
    from_version_id: uuid.UUID,
    to_version_id: uuid.UUID,
) -> DocumentVersionCompareRelation | None:
    from_ver, to_ver = _ordered_versions(db, from_version_id, to_version_id)
    return db.scalar(
        select(DocumentVersionCompareRelation).where(
            DocumentVersionCompareRelation.document_id == document_id,
            DocumentVersionCompareRelation.from_version_id == from_ver.id,
            DocumentVersionCompareRelation.to_version_id == to_ver.id,
        )
    )


def _upsert_relation(
    db: Session,
    *,
    document_id: uuid.UUID,
    from_version: DocumentVersion,
    to_version: DocumentVersion,
    relation_type: str,
) -> DocumentVersionCompareRelation:
    rel = get_relation_by_pair(
        db, document_id, from_version.id, to_version.id
    )
    if rel:
        if rel.relation_type == VersionCompareRelationType.on_demand.value and (
            relation_type != VersionCompareRelationType.on_demand.value
        ):
            rel.relation_type = relation_type
        return rel
    rel = DocumentVersionCompareRelation(
        document_id=document_id,
        from_version_id=from_version.id,
        to_version_id=to_version.id,
        relation_type=relation_type,
        status=VersionCompareStatus.pending.value,
        progress=0,
    )
    db.add(rel)
    db.flush()
    return rel


def run_version_compare_relation(db: Session, relation_id: uuid.UUID) -> None:
    rel = db.get(DocumentVersionCompareRelation, relation_id)
    if not rel:
        return
    if rel.status == VersionCompareStatus.done.value:
        return

    rel.status = VersionCompareStatus.running.value
    rel.started_at = datetime.now(timezone.utc)
    rel.progress = 10
    rel.error_message = None
    db.commit()

    try:
        from_ver = db.get(DocumentVersion, rel.from_version_id)
        to_ver = db.get(DocumentVersion, rel.to_version_id)
        if not from_ver or not to_ver:
            raise ValueError("版本不存在")
        if from_ver.file_size <= 0 or to_ver.file_size <= 0:
            raise ValueError("版本文件未上传")

        rel.progress = 40
        db.commit()

        try:
            from app.services.document_git_service import compute_version_diff_via_git

            diff_rows, meta = compute_version_diff_via_git(db, from_ver, to_ver)
        except Exception as git_exc:
            logger.info(
                "Git diff 不可用，回退分块 diff relation_id=%s: %s",
                relation_id,
                git_exc,
            )
            diff_rows, meta = compute_block_diffs(db, from_ver, to_ver)

        db.query(DocumentVersionDiffItem).filter(
            DocumentVersionDiffItem.relation_id == rel.id
        ).delete()

        for item in diff_rows:
            db.add(
                DocumentVersionDiffItem(
                    relation_id=rel.id,
                    document_id=rel.document_id,
                    from_version_id=rel.from_version_id,
                    to_version_id=rel.to_version_id,
                    diff_type=item["diff_type"],
                    text_left=item.get("text_left"),
                    text_right=item.get("text_right"),
                    anchor_json=item.get("anchor_json"),
                )
            )

        rel.payload = {
            **meta,
            "diff_count": len(diff_rows),
        }
        rel.diff_count = len(diff_rows)
        rel.status = VersionCompareStatus.done.value
        rel.progress = 100
        rel.finished_at = datetime.now(timezone.utc)
        db.commit()

        from app.services.version_compare_summary_service import generate_relation_summary

        try:
            generate_relation_summary(db, rel.id)
        except Exception:
            logger.warning("版本对比总结生成失败 relation_id=%s", relation_id, exc_info=True)
    except Exception as exc:
        logger.exception("版本对比失败 relation_id=%s", relation_id)
        rel.status = VersionCompareStatus.failed.value
        rel.error_message = str(exc)[:500]
        rel.finished_at = datetime.now(timezone.utc)
        db.commit()


def _run_relation_in_background(relation_id: uuid.UUID) -> None:
    db = SessionLocal()
    try:
        run_version_compare_relation(db, relation_id)
    finally:
        db.close()


def enqueue_version_compare(relation_id: uuid.UUID) -> None:
    thread = threading.Thread(
        target=_run_relation_in_background,
        args=(relation_id,),
        name=f"version-compare-{relation_id}",
        daemon=True,
    )
    thread.start()


def schedule_precompare_for_version(
    db: Session,
    document_id: uuid.UUID,
    version_id: uuid.UUID,
) -> list[uuid.UUID]:
    """新版本上传后：预对比 V0 与上一相邻版本。"""
    version = db.get(DocumentVersion, version_id)
    if not version or version.document_id != document_id or version.file_size <= 0:
        return []

    all_versions = list(
        db.scalars(
            select(DocumentVersion)
            .where(
                DocumentVersion.document_id == document_id,
                DocumentVersion.file_size > 0,
            )
            .order_by(DocumentVersion.version_no.asc())
        ).all()
    )
    if not all_versions:
        return []

    v0 = all_versions[0]
    relation_ids: list[uuid.UUID] = []

    if version.id != v0.id:
        rel_v0 = _upsert_relation(
            db,
            document_id=document_id,
            from_version=v0,
            to_version=version,
            relation_type=VersionCompareRelationType.baseline_v0.value,
        )
        relation_ids.append(rel_v0.id)

    prev = next(
        (v for v in all_versions if v.version_no == version.version_no - 1),
        None,
    )
    if (
        prev
        and prev.id != version.id
        and prev.id != v0.id
    ):
        rel_adj = _upsert_relation(
            db,
            document_id=document_id,
            from_version=prev,
            to_version=version,
            relation_type=VersionCompareRelationType.adjacent.value,
        )
        relation_ids.append(rel_adj.id)

    db.commit()

    for rid in relation_ids:
        rel = db.get(DocumentVersionCompareRelation, rid)
        if rel and rel.status != VersionCompareStatus.done.value:
            enqueue_version_compare(rid)

    return relation_ids


def relation_to_dict(
    db: Session, rel: DocumentVersionCompareRelation, *, include_items: bool = False
) -> dict:
    from_ver = db.get(DocumentVersion, rel.from_version_id)
    to_ver = db.get(DocumentVersion, rel.to_version_id)
    data = {
        "id": str(rel.id),
        "document_id": str(rel.document_id),
        "from_version_id": str(rel.from_version_id),
        "to_version_id": str(rel.to_version_id),
        "from_version_no": from_ver.version_no if from_ver else None,
        "to_version_no": to_ver.version_no if to_ver else None,
        "relation_type": rel.relation_type,
        "status": rel.status,
        "progress": rel.progress,
        "diff_count": rel.diff_count,
        "error_message": rel.error_message,
        "payload": rel.payload,
        "created_at": rel.created_at.isoformat() if rel.created_at else None,
        "finished_at": rel.finished_at.isoformat() if rel.finished_at else None,
        "llm_summary": rel.llm_summary,
        "llm_summary_status": rel.llm_summary_status,
        "to_change_description": (to_ver.change_description or "").strip() if to_ver else "",
        "precomputed": rel.relation_type
        in (
            VersionCompareRelationType.baseline_v0.value,
            VersionCompareRelationType.adjacent.value,
        ),
    }
    if include_items:
        items = db.scalars(
            select(DocumentVersionDiffItem)
            .where(DocumentVersionDiffItem.relation_id == rel.id)
            .order_by(DocumentVersionDiffItem.id.asc())
        ).all()
        data["diff_items"] = [
            {
                "id": str(it.id),
                "diff_type": it.diff_type,
                "text_left": it.text_left,
                "text_right": it.text_right,
                "anchor_json": it.anchor_json,
                "from_version_id": str(it.from_version_id),
                "to_version_id": str(it.to_version_id),
            }
            for it in items
        ]
    return data


def _placeholder_relation(
    db: Session,
    document_id: uuid.UUID,
    from_ver: DocumentVersion,
    to_ver: DocumentVersion,
    *,
    message: str = "差异尚未预计算，上传新版本后系统将自动分析，请稍后刷新",
) -> dict:
    return {
        "id": "",
        "document_id": str(document_id),
        "from_version_id": str(from_ver.id),
        "to_version_id": str(to_ver.id),
        "from_version_no": from_ver.version_no,
        "to_version_no": to_ver.version_no,
        "relation_type": VersionCompareRelationType.adjacent.value,
        "status": VersionCompareStatus.pending.value,
        "progress": 0,
        "diff_count": 0,
        "error_message": message,
        "payload": None,
        "created_at": None,
        "finished_at": None,
        "llm_summary": None,
        "llm_summary_status": None,
        "to_change_description": (to_ver.change_description or "").strip(),
        "precomputed": True,
        "diff_items": [],
    }


def load_version_pair_relation(
    db: Session,
    user: User,
    document_id: uuid.UUID,
    left_version_id: uuid.UUID,
    right_version_id: uuid.UUID,
) -> dict:
    """只读：返回已入库的版本对 diff，不触发计算。"""
    if left_version_id == right_version_id:
        from app.core.exceptions import bad_request

        raise bad_request("请选择两个不同版本")

    doc = db.get(Document, document_id)
    if not doc or doc.deleted_at:
        from app.core.exceptions import not_found

        raise not_found("文档不存在")
    _require_document_access(db, user, doc)

    from_ver, to_ver = _ordered_versions(db, left_version_id, right_version_id)
    rel = get_relation_by_pair(db, document_id, from_ver.id, to_ver.id)
    if not rel:
        return _placeholder_relation(db, document_id, from_ver, to_ver)
    include_items = rel.status == VersionCompareStatus.done.value
    return relation_to_dict(db, rel, include_items=include_items)


def load_adjacent_version_relations(
    db: Session,
    user: User,
    document_id: uuid.UUID,
    version_ids: list[uuid.UUID],
) -> list[dict]:
    """只读：按时间线相邻版本对加载已预计算的 diff（上传时在后台生成）。"""
    if len(version_ids) < 2:
        from app.core.exceptions import bad_request

        raise bad_request("至少选择两个版本")

    doc = db.get(Document, document_id)
    if not doc or doc.deleted_at:
        from app.core.exceptions import not_found

        raise not_found("文档不存在")
    _require_document_access(db, user, doc)

    versions = []
    for vid in version_ids:
        ver = db.get(DocumentVersion, vid)
        if not ver or ver.document_id != document_id or ver.file_size <= 0:
            from app.core.exceptions import bad_request

            raise bad_request("版本无效或未上传")
        versions.append(ver)
    versions.sort(key=lambda v: v.version_no)

    out: list[dict] = []
    for i in range(len(versions) - 1):
        out.append(
            load_version_pair_relation(
                db,
                user,
                document_id,
                versions[i].id,
                versions[i + 1].id,
            )
        )
    return out


def request_version_pair_compare(
    db: Session,
    user: User,
    document_id: uuid.UUID,
    left_version_id: uuid.UUID,
    right_version_id: uuid.UUID,
    *,
    background: bool = True,
) -> dict:
    """查询或创建版本对 diff；预计算命中则直接返回，否则异步执行。"""
    if left_version_id == right_version_id:
        from app.core.exceptions import bad_request

        raise bad_request("请选择两个不同版本")

    doc = db.get(Document, document_id)
    if not doc or doc.deleted_at:
        from app.core.exceptions import not_found

        raise not_found("文档不存在")
    _require_document_access(db, user, doc)

    from_ver, to_ver = _ordered_versions(db, left_version_id, right_version_id)

    rel = get_relation_by_pair(db, document_id, from_ver.id, to_ver.id)
    need_run = False
    if not rel:
        rel = _upsert_relation(
            db,
            document_id=document_id,
            from_version=from_ver,
            to_version=to_ver,
            relation_type=VersionCompareRelationType.on_demand.value,
        )
        db.commit()
        need_run = True
    elif rel.status == VersionCompareStatus.failed.value:
        rel.status = VersionCompareStatus.pending.value
        rel.error_message = None
        db.commit()
        need_run = True
    elif rel.status == VersionCompareStatus.pending.value:
        need_run = not background
    elif rel.status == VersionCompareStatus.running.value:
        need_run = False

    if need_run:
        if background:
            enqueue_version_compare(rel.id)
        else:
            run_version_compare_relation(db, rel.id)
            db.refresh(rel)

    include_items = rel.status == VersionCompareStatus.done.value
    return relation_to_dict(db, rel, include_items=include_items)


def batch_request_adjacent_version_compares(
    db: Session,
    user: User,
    document_id: uuid.UUID,
    version_ids: list[uuid.UUID],
    *,
    background: bool = True,
) -> list[dict]:
    """加载相邻版本对 diff。默认只读；background=True 时仅对缺失/失败对按需补算。"""
    if not background:
        return load_adjacent_version_relations(db, user, document_id, version_ids)

    if len(version_ids) < 2:
        from app.core.exceptions import bad_request

        raise bad_request("至少选择两个版本")

    doc = db.get(Document, document_id)
    if not doc or doc.deleted_at:
        from app.core.exceptions import not_found

        raise not_found("文档不存在")
    _require_document_access(db, user, doc)

    versions = []
    for vid in version_ids:
        ver = db.get(DocumentVersion, vid)
        if not ver or ver.document_id != document_id or ver.file_size <= 0:
            from app.core.exceptions import bad_request

            raise bad_request("版本无效或未上传")
        versions.append(ver)
    versions.sort(key=lambda v: v.version_no)

    out: list[dict] = []
    for i in range(len(versions) - 1):
        left_id, right_id = versions[i].id, versions[i + 1].id
        rel = get_relation_by_pair(db, document_id, left_id, right_id)
        if rel and rel.status == VersionCompareStatus.done.value:
            out.append(relation_to_dict(db, rel, include_items=True))
            continue
        if rel and rel.status in (
            VersionCompareStatus.pending.value,
            VersionCompareStatus.running.value,
        ):
            out.append(relation_to_dict(db, rel, include_items=False))
            continue
        data = request_version_pair_compare(
            db,
            user,
            document_id,
            left_id,
            right_id,
            background=True,
        )
        out.append(data)
    return out


def list_document_version_relations(
    db: Session,
    user: User,
    document_id: uuid.UUID,
) -> list[dict]:
    doc = db.get(Document, document_id)
    if not doc or doc.deleted_at:
        from app.core.exceptions import not_found

        raise not_found("文档不存在")
    _require_document_access(db, user, doc)

    rows = db.scalars(
        select(DocumentVersionCompareRelation)
        .where(DocumentVersionCompareRelation.document_id == document_id)
        .order_by(DocumentVersionCompareRelation.created_at.desc())
    ).all()
    return [relation_to_dict(db, r) for r in rows]
