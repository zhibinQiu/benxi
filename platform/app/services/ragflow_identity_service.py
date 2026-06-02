"""RAGFlow 用户级知识库命名与嵌入会话（阶段 1–4）。"""

from __future__ import annotations

import logging
import re
import uuid

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.integrations.ragflow_provision import RagflowProvisionError, provision_and_login
from app.models.org import User
from app.models.ragflow_link import RagflowAccountLink
from app.services.ragflow_naming import (
    dataset_display_label_personal,
    is_ragflow_valid_email,
    platform_email_for_user,
)

logger = logging.getLogger(__name__)


def resolve_ui_embed_base() -> str:
    """前端 iframe 基址：优先同源代理前缀（阶段 2 SSO）。"""
    settings = get_settings()
    proxy = (settings.knowflow_ui_proxy_prefix or "").strip()
    if proxy:
        return proxy.rstrip("/")
    return settings.knowflow_ui_url.rstrip("/")


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
    link = get_or_create_link(db, user)
    cached = (link.ragflow_access_token or "").strip()
    if cached:
        if _ragflow_auth_valid(cached):
            from app.integrations.ragflow_provision import finalize_ragflow_link

            finalize_ragflow_link(link, cached, user)
            db.flush()
            return cached
        link.ragflow_access_token = None
        db.flush()
    try:
        return provision_and_login(link, user)
    except RagflowProvisionError as e:
        logger.warning("RAGFlow 开户/登录失败 %s: %s", user.username, e)
        return None
    except httpx.HTTPError as e:
        logger.warning("RAGFlow 不可达，跳过开户/登录 %s: %s", user.username, e)
        return None


def warm_ragflow_on_login(db: Session, user: User) -> RagflowAccountLink:
    """登录时轻量预热：开户/会话、模型配置、KnowFlow 建库权限（不阻塞同步文档）。"""
    settings = get_settings()
    link = get_or_create_link(db, user)
    if not settings.knowflow_enabled:
        return link
    get_user_ragflow_auth(db, user)
    db.flush()
    if link.ragflow_user_id:
        from app.integrations.ragflow_rbac import ensure_ragflow_global_admin

        ensure_ragflow_global_admin(link.ragflow_user_id)
    return link


def ensure_ragflow_account(db: Session, user: User) -> RagflowAccountLink:
    """平台登录后对齐 KnowFlow 账号；重同步仅在配置开启时执行。"""
    settings = get_settings()
    link = warm_ragflow_on_login(db, user)
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
    settings = get_settings()
    try:
        with httpx.Client(timeout=5.0) as client:
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


def build_embed_session(
    db: Session, user: User, *, sync_catalog: bool | None = None
) -> dict:
    """开通账号、返回 SSO token；目录同步由 sync_catalog / 配置控制。"""
    from app.integrations.knowflow_client import get_knowflow_client_for_user
    from app.services.ragflow_scope_service import (
        dept_suffix_labels_for_theme,
        knowflow_kb_labels_for_user,
    )
    settings = get_settings()
    kb_labels = knowflow_kb_labels_for_user(db, user)
    dept_suffix_labels = dept_suffix_labels_for_theme(db, user)
    link = get_or_create_link(db, user)
    base = resolve_ui_embed_base()
    embed_url = f"{base}/"

    authorization: str | None = None
    from app.core.user_messages import (
        KNOWLEDGE_NOT_ENABLED,
        KNOWLEDGE_SERVICE_UNAVAILABLE,
        sanitize_user_message,
    )

    sso_message = KNOWLEDGE_NOT_ENABLED
    synced_count = 0

    profile: dict | None = None
    do_sync = (
        settings.ragflow_sync_on_embed
        if sync_catalog is None
        else sync_catalog
    )
    if settings.knowflow_enabled:
        try:
            cached = (link.ragflow_access_token or "").strip()
            valid, profile = _ragflow_user_info(cached)
            if valid:
                authorization = cached
                sso_message = "知识服务已就绪"
                if link.ragflow_user_id:
                    from app.integrations.ragflow_llm_template import ensure_shared_llm_config

                    ensure_shared_llm_config(link.ragflow_user_id)
            else:
                link.ragflow_access_token = None
                db.flush()
                authorization = provision_and_login(link, user)
                sso_message = "知识服务已就绪"
                if authorization:
                    _, profile = _ragflow_user_info(authorization)
        except (RagflowProvisionError, httpx.HTTPError) as e:
            logger.warning("RAGFlow SSO 失败 %s: %s", user.username, e)
            try:
                from app.integrations.ragflow_provision import recover_ragflow_account

                link.ragflow_access_token = None
                db.flush()
                authorization = recover_ragflow_account(link, user)
                sso_message = "知识服务已就绪"
                db.flush()
                if authorization:
                    _, profile = _ragflow_user_info(authorization)
            except (RagflowProvisionError, httpx.HTTPError) as e2:
                sso_message = sanitize_user_message(
                    str(e2),
                    fallback=KNOWLEDGE_SERVICE_UNAVAILABLE,
                )

        if authorization:
            from app.services.knowflow_catalog_service import (
                reconcile_user_knowflow_catalog,
            )

            try:
                result = reconcile_user_knowflow_catalog(
                    db,
                    user,
                    sync_limit=settings.ragflow_sync_doc_limit if do_sync else 0,
                    sync_documents=do_sync,
                )
                synced_count = int(result.get("synced_documents") or 0)
                if do_sync:
                    from app.services.ragflow_sync_service import purge_stale_knowflow_links

                    purge_stale_knowflow_links(db)
                elif int(result.get("visible_datasets") or 0) > 0:
                    sso_message = "已登录；知识库已就绪，文档正在后台同步"
            except Exception as e:
                logger.warning("RAGFlow 知识库目录同步跳过: %s", e)
        elif authorization and "自动登录" not in sso_message:
            sso_message = "知识服务已就绪，文档正在后台同步"

    return {
        "integration_phase": 4,
        "embed_url": embed_url,
        "ui_direct_url": settings.knowflow_ui_url.rstrip("/"),
        "dataset_name": dataset_display_label_personal(db, user.id),
        "platform_user_id": str(user.id),
        "knowflow_kb_labels": kb_labels,
        "dept_suffix_labels": dept_suffix_labels,
        "ragflow_email": link.ragflow_email,
        "synced_documents": synced_count,
        "theme": {
            "app_name": settings.knowflow_theme_app_name or settings.app_name,
            "primary_color": settings.knowflow_theme_primary,
            "primary_hover": settings.knowflow_theme_primary_hover,
            "primary_pressed": settings.knowflow_theme_primary_pressed,
            "hide_file_manager": settings.knowflow_hide_file_manager,
            "logo_url": settings.knowflow_theme_logo_url,
            "favicon_url": settings.knowflow_theme_favicon_url,
            "display_name": (user.display_name or user.username or "用户").strip(),
            "username": user.username,
            "knowflow_kb_labels": kb_labels,
            "dept_suffix_labels": dept_suffix_labels,
        },
        "sso": {
            "ready": bool(authorization),
            "authorization": authorization,
            "access_token": (profile or {}).get("access_token") if profile else None,
            "user_info": (
                {
                    "nickname": profile.get("nickname"),
                    "email": profile.get("email"),
                    "avatar": profile.get("avatar"),
                }
                if profile
                else None
            ),
            "message": sso_message,
        },
    }
