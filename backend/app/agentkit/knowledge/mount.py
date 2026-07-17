"""Agent 知识库文件夹挂载管理 — 通用实现。

允许为 Agent 挂载知识库文件夹，挂载后该 Agent 的知识库搜索
自动限定在挂载文件夹内的文档中，实现细粒度的知识访问控制。

与 ``app.services.agent_knowledge_mount_service`` 的区别：
本模块仅包含纯逻辑（无 HTTP 异常），供 service 和 agentkit 共用。
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.agent_profile_binding import AgentProfileBinding
from app.models.document import Document, DocumentLibraryFolder
from app.models.org import User
from app.models.ragflow_document_link import RagflowDocumentLink

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class KnowledgeMountEntry:
    """单个挂载条目。"""

    id: str
    dataset_id: str
    folder_id: str
    scope: str
    label: str


def _get_binding(db: Session, agent_id: str) -> AgentProfileBinding | None:
    return db.get(AgentProfileBinding, (agent_id or "").strip())


def list_mounts(db: Session, agent_id: str) -> list[dict[str, Any]]:
    """列出指定 Agent 的所有知识库挂载。"""
    binding = _get_binding(db, agent_id)
    if not binding:
        return []
    return list(binding.knowledge_mounts or [])


def add_mount(
    db: Session,
    agent_id: str,
    *,
    dataset_id: str,
    folder_id: str,
    scope: str,
    label: str | None = None,
) -> dict[str, Any]:
    """为 Agent 添加一个知识库文件夹挂载。

    Returns:
        挂载条目字典。

    Raises:
        ValueError: Agent 不存在或文件夹已挂载。
    """
    binding = _get_binding(db, agent_id)
    if not binding:
        raise ValueError(f"Agent `{agent_id}` 不存在或未初始化")
    mount_id = uuid.uuid4().hex[:12]

    # 验证文件夹存在
    folder = _resolve_folder(db, dataset_id, folder_id, scope)
    resolved_label = (
        label
        or (folder.name if folder else None)
        or "文件夹"
    )

    mounts = list(binding.knowledge_mounts or [])
    for existing in mounts:
        if existing.get("dataset_id") == dataset_id and existing.get("folder_id") == folder_id:
            raise ValueError("该文件夹已经挂载")

    entry = {
        "id": mount_id,
        "dataset_id": dataset_id,
        "folder_id": folder_id,
        "scope": scope,
        "label": resolved_label,
    }
    mounts.append(entry)
    binding.knowledge_mounts = mounts
    db.commit()
    db.refresh(binding)
    return entry


def remove_mount(db: Session, agent_id: str, mount_id: str) -> None:
    """移除指定 Agent 的一个知识库挂载。

    Raises:
        ValueError: Agent 不存在或挂载条目不存在。
    """
    binding = _get_binding(db, agent_id)
    if not binding:
        raise ValueError(f"Agent `{agent_id}` 不存在或未初始化")
    mounts = list(binding.knowledge_mounts or [])
    before = len(mounts)
    mounts = [m for m in mounts if m.get("id") != mount_id]
    if len(mounts) == before:
        raise ValueError(f"挂载 `{mount_id}` 不存在")
    binding.knowledge_mounts = mounts
    db.commit()
    db.refresh(binding)


def resolve_mounts_to_doc_ids(
    db: Session,
    user: User,
    mounts: list[dict[str, Any]] | None,
) -> list[str]:
    """将挂载列表解析为文档 ID 列表。

    遍历每个挂载项的 dataset_id + folder_id，查询该 dataset 下的文档链接，
    过滤出匹配 folder_id 且用户有权访问的文档。
    """
    if not mounts:
        return []
    doc_ids: list[str] = []
    seen: set[str] = set()

    from app.core.document_scope import can_query_document

    for mount in mounts:
        dataset_id = (mount.get("dataset_id") or "").strip()
        folder_id = (mount.get("folder_id") or "").strip()
        if not dataset_id or not folder_id:
            continue

        links = list(
            db.scalars(
                select(RagflowDocumentLink).where(
                    RagflowDocumentLink.dataset_id == dataset_id
                )
            ).all()
        )
        if not links:
            continue

        doc_uuids = {ln.platform_document_id for ln in links if ln.platform_document_id}
        if not doc_uuids:
            continue

        docs = list(
            db.scalars(
                select(Document).where(
                    Document.id.in_(doc_uuids),
                    Document.deleted_at.is_(None),
                )
            ).all()
        )

        for doc in docs:
            if not can_query_document(db, user, doc):
                continue
            doc_folder_id = str(doc.folder_id) if doc.folder_id else None
            mount_folder = folder_id if folder_id != "__uncategorized__" else None
            if doc_folder_id == mount_folder:
                did = str(doc.id)
                if did not in seen:
                    seen.add(did)
                    doc_ids.append(did)

    return doc_ids


def _resolve_folder(
    db: Session,
    dataset_id: str,
    folder_id: str,
    scope: str,
) -> DocumentLibraryFolder | None:
    """按 scope + folder_id 查找文件夹。"""
    if folder_id == "__uncategorized__" or not folder_id:
        return None
    try:
        fid = uuid.UUID(folder_id)
    except (TypeError, ValueError):
        return None
    folder = db.get(DocumentLibraryFolder, fid)
    if folder and folder.scope == scope:
        return folder
    return None
