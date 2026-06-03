"""KnowFlow RBAC：为平台同步的 RAGFlow 用户授予全局 admin（可创建知识库）。"""

from __future__ import annotations

import logging

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)


def _rbac_base_url() -> str:
    settings = get_settings()
    return (settings.knowflow_backend_url or "http://127.0.0.1:5001").rstrip("/")


def _has_global_admin(client: httpx.Client, ragflow_user_id: str) -> bool:
    check = client.post(
        f"{_rbac_base_url()}/api/v1/rbac/permissions/check-global",
        json={
            "user_id": ragflow_user_id,
            "permission_type": "admin",
            "tenant_id": "default",
        },
    )
    return check.status_code == 200 and bool(check.json().get("has_permission"))


def ensure_ragflow_global_admin(ragflow_user_id: str | None) -> bool:
    """授予全局 admin 角色，解决「没有创建知识库的权限」。"""
    uid = (ragflow_user_id or "").strip()
    if not uid:
        return False
    url = f"{_rbac_base_url()}/api/v1/rbac/users/{uid}/roles"
    try:
        with httpx.Client(timeout=10.0) as client:
            if _has_global_admin(client, uid):
                return True
            r = client.post(
                url,
                json={"role_code": "admin", "tenant_id": "default"},
            )
            if r.status_code != 200:
                logger.warning(
                    "授予 RAGFlow admin 失败: %s %s", r.status_code, r.text[:300]
                )
                return False
            if _has_global_admin(client, uid):
                logger.info("已为 RAGFlow 用户 %s 授予全局 admin 角色", uid)
                return True
            logger.warning(
                "RAGFlow 用户 %s 授予 admin 后仍未通过权限校验", uid
            )
            return False
    except Exception as e:
        logger.warning("KnowFlow RBAC 不可用: %s", e)
        return False


def revoke_ragflow_global_admin(ragflow_user_id: str | None) -> bool:
    """撤销全局 admin（普通用户不应看到全部知识库）。"""
    uid = (ragflow_user_id or "").strip()
    if not uid:
        return False
    url = f"{_rbac_base_url()}/api/v1/rbac/users/{uid}/roles"
    try:
        with httpx.Client(timeout=10.0) as client:
            if not _has_global_admin(client, uid):
                return True
            revoke_url = f"{url}/admin"
            r = client.delete(revoke_url, params={"tenant_id": "default"})
            if r.status_code not in (200, 204, 404):
                logger.warning(
                    "撤销 RAGFlow admin 失败: %s %s", r.status_code, r.text[:300]
                )
                return False
            if not _has_global_admin(client, uid):
                logger.info("已撤销 RAGFlow 用户 %s 的全局 admin 角色", uid)
                return True
            logger.warning("RAGFlow 用户 %s 撤销 admin 后仍具全局权限", uid)
            return False
    except Exception as e:
        logger.warning("KnowFlow RBAC 撤销 admin 不可用: %s", e)
        return False


def sync_ragflow_global_admin_role(
    ragflow_user_id: str | None, *, grant: bool
) -> None:
    if grant:
        ensure_ragflow_global_admin(ragflow_user_id)
    else:
        revoke_ragflow_global_admin(ragflow_user_id)
