"""KnowFlow RBAC：为平台同步的 RAGFlow 用户授予全局 admin（可创建知识库）。"""

from __future__ import annotations

import logging

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)


def _rbac_base_url() -> str:
    settings = get_settings()
    return (settings.knowflow_backend_url or "http://127.0.0.1:5001").rstrip("/")


def ensure_ragflow_global_admin(ragflow_user_id: str | None) -> bool:
    """授予全局 admin 角色，解决「没有创建知识库的权限」。"""
    if not ragflow_user_id:
        return False
    url = f"{_rbac_base_url()}/api/v1/rbac/users/{ragflow_user_id}/roles"
    try:
        with httpx.Client(timeout=10.0) as client:
            check = client.post(
                f"{_rbac_base_url()}/api/v1/rbac/permissions/check-global",
                json={
                    "user_id": ragflow_user_id,
                    "permission_type": "admin",
                    "tenant_id": "default",
                },
            )
            if check.status_code == 200 and check.json().get("has_permission"):
                return True
            r = client.post(
                url,
                json={"role_code": "admin", "tenant_id": "default"},
            )
        if r.status_code == 200:
            logger.info("已为 RAGFlow 用户 %s 授予全局 admin 角色", ragflow_user_id)
            return True
        logger.warning("授予 RAGFlow admin 失败: %s %s", r.status_code, r.text[:300])
        return False
    except Exception as e:
        logger.warning("KnowFlow RBAC 不可用: %s", e)
        return False
