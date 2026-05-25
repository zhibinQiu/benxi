"""KnowFlow 知识库级 RBAC：将平台文档权限映射为 dataset 授权（不复制文件）。"""

from __future__ import annotations

import logging
from typing import Literal

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)

KbPermissionLevel = Literal["read", "write", "admin"]


def _knowflow_api_base() -> str:
    return (get_settings().knowflow_backend_url or "http://127.0.0.1:5001").rstrip("/")


def grant_kb_user_permission(
    kb_id: str,
    ragflow_user_id: str,
    permission_level: KbPermissionLevel,
) -> bool:
    """为用户授予知识库资源角色（viewer/editor/admin）。"""
    if not kb_id or not ragflow_user_id:
        return False
    url = f"{_knowflow_api_base()}/api/v1/knowledgebases/{kb_id}/permissions/users"
    try:
        with httpx.Client(timeout=15.0) as client:
            r = client.post(
                url,
                json={
                    "user_id": ragflow_user_id,
                    "permission_level": permission_level,
                },
            )
        if r.status_code == 200:
            body = r.json()
            if isinstance(body, dict) and body.get("code", 0) == 0:
                return True
        logger.warning(
            "授予知识库权限失败 kb=%s user=%s level=%s: %s %s",
            kb_id,
            ragflow_user_id,
            permission_level,
            r.status_code,
            r.text[:300],
        )
    except Exception as e:
        logger.warning("KnowFlow KB ACL 不可用: %s", e)
    return False


def revoke_kb_user_permission(kb_id: str, ragflow_user_id: str) -> bool:
    """撤销用户在某知识库上的全部资源角色（admin/editor/viewer）。"""
    if not kb_id or not ragflow_user_id:
        return False
    url = (
        f"{_knowflow_api_base()}/api/v1/knowledgebases/{kb_id}"
        f"/permissions/users/{ragflow_user_id}"
    )
    try:
        with httpx.Client(timeout=15.0) as client:
            r = client.delete(url)
        if r.status_code == 200:
            body = r.json()
            if isinstance(body, dict) and body.get("code", 0) == 0:
                return True
        logger.warning(
            "撤销知识库权限失败 kb=%s user=%s: %s %s",
            kb_id,
            ragflow_user_id,
            r.status_code,
            r.text[:300],
        )
    except Exception as e:
        logger.warning("KnowFlow KB ACL 撤销不可用: %s", e)
    return False
