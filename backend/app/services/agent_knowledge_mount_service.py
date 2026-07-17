"""Agent 知识库文件夹挂载管理 — Service 层。

委托给 agentkit 模块，在此层做 HTTP 异常适配。
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.orm import Session

from app.agentkit.knowledge.mount import (
    add_mount as _add_mount,
    list_mounts as _list_mounts,
    remove_mount as _remove_mount,
    resolve_mounts_to_doc_ids as _resolve_mounts_to_doc_ids,
)
from app.core.exceptions import bad_request, not_found
from app.models.org import User

logger = logging.getLogger(__name__)


def list_mounts(db: Session, agent_id: str) -> list[dict[str, Any]]:
    """列出指定 Agent 的所有知识库挂载。"""
    return _list_mounts(db, agent_id)


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

    Raises:
        bad_request: 文件夹已挂载或 Agent 不存在。
    """
    try:
        return _add_mount(
            db, agent_id,
            dataset_id=dataset_id, folder_id=folder_id,
            scope=scope, label=label,
        )
    except ValueError as exc:
        raise bad_request(str(exc)) from exc


def remove_mount(db: Session, agent_id: str, mount_id: str) -> None:
    """移除指定 Agent 的一个知识库挂载。

    Raises:
        not_found: 挂载条目不存在或 Agent 不存在。
    """
    try:
        _remove_mount(db, agent_id, mount_id)
    except ValueError as exc:
        raise not_found(str(exc)) from exc


def resolve_mounts_to_doc_ids(
    db: Session,
    user: User,
    mounts: list[dict[str, Any]] | None,
) -> list[str]:
    """将挂载列表解析为文档 ID 列表。"""
    return _resolve_mounts_to_doc_ids(db, user, mounts)
