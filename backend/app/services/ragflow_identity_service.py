"""RAGFlow 用户级知识库命名与嵌入会话（阶段 1–4）。"""

from __future__ import annotations

import logging

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.integrations.ragflow_provision import RagflowProvisionError, provision_and_login
from app.models.org import User
from app.models.ragflow_link import RagflowAccountLink
from app.services.ragflow_naming import (
    is_ragflow_valid_email,
    platform_email_for_user,
)

logger = logging.getLogger(__name__)


def _sync_link_email(db: Session, link: RagflowAccountLink, user: User) -> None:
    """修正邮箱（含 shared 模式），邮箱变更时清空凭据以便重新开户。"""
    expected = platform_email_for_user(user)
    current = (link.ragflow_email or "").strip().lower()
    settings = get_settings()
    shared = (settings.ragflow_account_mode or "").strip().lower() == "shared"
    shared_pwd = (settings.ragflow_shared_password or "").strip()
    if not shared and shared_pwd and link.ragflow_password == shared_pwd:
        link.ragflow_password = None
        link.ragflow_access_token = None
        link.ragflow_user_id = None
    email_changed = current != expected
    if (
        not email_changed
        and is_ragflow_valid_email(current)
        and (not shared or link.ragflow_password == shared_pwd)
        and (shared or link.ragflow_password)
    ):
        return
    if email_changed:
        link.ragflow_access_token = None
        link.ragflow_user_id = None
        if not shared:
            link.ragflow_password = None
        if current:
            from app.integrations.ragflow_provision import (
                _purge_ragflow_user_by_email,
                _purge_ragflow_user_by_uid_suffix,
                _uid_suffix_from_platform_email,
            )

            _purge_ragflow_user_by_email(current)
            suffix = _uid_suffix_from_platform_email(current) or _uid_suffix_from_platform_email(
                expected
            )
            if suffix:
                _purge_ragflow_user_by_uid_suffix(suffix)
    link.ragflow_email = expected
    if shared and shared_pwd:
        link.ragflow_password = shared_pwd


def get_or_create_link(db: Session, user: User) -> RagflowAccountLink:
    link = db.scalar(
        select(RagflowAccountLink).where(
            RagflowAccountLink.platform_user_id == user.id
        )
    )
    if link:
        _sync_link_email(db, link, user)
        db.flush()
        return link
    link = RagflowAccountLink(
        platform_user_id=user.id,
        ragflow_email=platform_email_for_user(user),
    )
    db.add(link)
    db.flush()
    return link


def get_user_ragflow_auth(db: Session, user: User) -> str | None:
    """确保平台用户已在 RAGFlow 开户并返回 Web 登录 JWT。"""
    settings = get_settings()
    if not settings.knowflow_enabled:
        return None
    from app.database import release_db_connection
    from app.integrations.ragflow_http import (
        mark_ragflow_http_failure,
        mark_ragflow_http_success,
        should_attempt_ragflow_http,
    )

    link = get_or_create_link(db, user)
    cached = (link.ragflow_access_token or "").strip()
    if cached:
        release_db_connection(db)
        if not should_attempt_ragflow_http():
            return cached
        if _ragflow_auth_valid(cached):
            mark_ragflow_http_success()
            from app.integrations.ragflow_provision import finalize_ragflow_link

            finalize_ragflow_link(link, cached, user, db=db)
            db.flush()
            return cached
        link.ragflow_access_token = None
        db.flush()
        release_db_connection(db)

    if not should_attempt_ragflow_http():
        logger.warning("RAGFlow 处于冷却期，跳过开户/登录 %s", user.username)
        return None

    release_db_connection(db)
    try:
        token = provision_and_login(link, user, db=db)
        mark_ragflow_http_success()
        db.flush()
        return token
    except RagflowProvisionError as e:
        mark_ragflow_http_failure()
        logger.warning("RAGFlow 开户/登录失败 %s: %s", user.username, e)
        return None
    except httpx.HTTPError as e:
        mark_ragflow_http_failure()
        logger.warning("RAGFlow 不可达，跳过开户/登录 %s: %s", user.username, e)
        return None


def warm_ragflow_on_login(db: Session, user: User) -> RagflowAccountLink:
    """登录时后台预热 RAGFlow SSO，并回收越权知识库授权。"""
    settings = get_settings()
    link = get_or_create_link(db, user)
    if not settings.knowflow_enabled:
        return link
    get_user_ragflow_auth(db, user)
    db.flush()
    if link.ragflow_user_id:
        try:
            from app.services.ragflow_scope_service import ensure_user_kb_create_permission

            ensure_user_kb_create_permission(db, user)
        except Exception as e:
            logger.warning("登录后 KnowFlow 建库权限授予跳过: %s", e)
    if link.ragflow_user_id:
        try:
            from app.database import release_db_connection
            from app.integrations.ragflow_llm_template import ensure_shared_llm_config

            release_db_connection(db)
            ensure_shared_llm_config(link.ragflow_user_id, db=db)
        except Exception as e:
            logger.warning("登录后 KnowFlow 模型配置同步跳过: %s", e)
    try:
        from app.services.knowflow_catalog_service import reconcile_user_knowflow_kb_acl

        reconcile_user_knowflow_kb_acl(db, user)
    except Exception as e:
        logger.warning("登录后 KnowFlow ACL 对齐跳过: %s", e)
    try:
        from app.domains.knowledge.background_sync import enqueue_catalog_reconcile_after_login

        enqueue_catalog_reconcile_after_login(user.id)
    except Exception as e:
        logger.warning("登录后 KnowFlow 目录后台同步调度跳过: %s", e)
    return link


def ensure_ragflow_account(db: Session, user: User) -> RagflowAccountLink:
    """平台登录后对齐 KnowFlow 账号；重同步仅在配置开启时执行。"""
    settings = get_settings()
    link = get_or_create_link(db, user)
    if settings.knowflow_enabled and settings.ragflow_sync_on_login:
        from app.services.knowflow_catalog_service import reconcile_user_knowflow_catalog

        try:
            reconcile_user_knowflow_catalog(
                db,
                user,
                sync_limit=settings.ragflow_sync_on_login_limit,
            )
        except Exception as e:
            logger.warning("登录后 KnowFlow 目录同步跳过: %s", e)
        from app.services.ragflow_sync_service import purge_stale_knowflow_links

        try:
            purge_stale_knowflow_links(db)
        except Exception as e:
            logger.warning("KnowFlow 残留索引清理跳过: %s", e)
    return link


def _ragflow_user_info(authorization: str | None) -> tuple[bool, dict | None]:
    """校验 RAGFlow 会话并返回 user/info data（避免重复请求）。"""
    token = (authorization or "").strip()
    if not token:
        return False, None
    from app.integrations.ragflow_http import ragflow_http_client, should_attempt_ragflow_http

    if not should_attempt_ragflow_http():
        return True, None
    settings = get_settings()
    try:
        with ragflow_http_client(timeout=5.0) as client:
            r = client.get(
                f"{settings.ragflow_api_url.rstrip('/')}/v1/user/info",
                headers={"Authorization": token},
            )
        if r.status_code != 200:
            return False, None
        body = r.json()
        if not (isinstance(body, dict) and body.get("code") == 0):
            return False, None
        data = body.get("data")
        return True, data if isinstance(data, dict) else None
    except Exception:
        return False, None


def _ragflow_auth_valid(authorization: str | None) -> bool:
    valid, _ = _ragflow_user_info(authorization)
    return valid
