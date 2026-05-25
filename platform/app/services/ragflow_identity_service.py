"""RAGFlow 用户级知识库命名与嵌入会话（阶段 1–4）。"""

from __future__ import annotations

import logging
import uuid

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.integrations.ragflow_provision import RagflowProvisionError, provision_and_login
from app.models.org import User
from app.models.ragflow_link import RagflowAccountLink
from app.services.ragflow_naming import (
    dataset_name_for_personal,
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


def _sync_link_email(link: RagflowAccountLink, user: User) -> None:
    """修正邮箱（含 shared 模式与无效 admin@local），并清除失效会话。"""
    expected = platform_email_for_user(user)
    current = (link.ragflow_email or "").strip().lower()
    settings = get_settings()
    shared = (settings.ragflow_account_mode or "").strip().lower() == "shared"
    shared_pwd = (settings.ragflow_shared_password or "").strip()
    if not shared and shared_pwd and link.ragflow_password == shared_pwd:
        link.ragflow_password = None
        link.ragflow_access_token = None
        link.ragflow_user_id = None
    if (
        current == expected
        and is_ragflow_valid_email(current)
        and (not shared or link.ragflow_password == shared_pwd)
        and (shared or link.ragflow_password)
    ):
        return
    link.ragflow_email = expected
    link.ragflow_access_token = None
    link.ragflow_user_id = None
    if shared and shared_pwd:
        link.ragflow_password = shared_pwd
    elif not shared:
        link.ragflow_password = None


def get_or_create_link(db: Session, user: User) -> RagflowAccountLink:
    link = db.scalar(
        select(RagflowAccountLink).where(
            RagflowAccountLink.platform_user_id == user.id
        )
    )
    if link:
        _sync_link_email(link, user)
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
    if link.ragflow_access_token:
        return link.ragflow_access_token
    try:
        return provision_and_login(link, user)
    except RagflowProvisionError as e:
        logger.warning("RAGFlow 开户/登录失败 %s: %s", user.username, e)
        return None


def ensure_ragflow_account(db: Session, user: User) -> RagflowAccountLink:
    """平台登录后对齐 KnowFlow 账号（邮箱/昵称一致），并预热可访问文档索引。"""
    settings = get_settings()
    link = get_or_create_link(db, user)
    if settings.knowflow_enabled:
        get_user_ragflow_auth(db, user)
        from app.services.ragflow_scope_service import (
            ensure_user_scope_datasets,
            sync_user_kb_grants,
        )

        kf = get_knowflow_client_for_user(db, user)
        if kf.enabled():
            try:
                ensure_user_scope_datasets(db, user, kf)
                sync_user_kb_grants(db, user)
                from app.services.ragflow_sync_service import purge_stale_knowflow_links

                purge_stale_knowflow_links(db)
            except Exception as e:
                logger.warning("登录后知识库授权同步跳过: %s", e)
        if settings.ragflow_sync_on_login:
            from app.services.ragflow_sync_service import sync_accessible_documents

            try:
                sync_accessible_documents(
                    db, user, limit=settings.ragflow_sync_on_login_limit
                )
            except Exception as e:
                logger.warning("登录后文档索引同步跳过: %s", e)
    return link


def _ragflow_auth_valid(authorization: str | None) -> bool:
    """校验平台侧已缓存的 RAGFlow 会话是否仍有效。"""
    token = (authorization or "").strip()
    if not token:
        return False
    settings = get_settings()
    try:
        with httpx.Client(timeout=8.0) as client:
            r = client.get(
                f"{settings.ragflow_api_url.rstrip('/')}/v1/user/info",
                headers={"Authorization": token},
            )
        if r.status_code != 200:
            return False
        body = r.json()
        return isinstance(body, dict) and body.get("code") == 0
    except Exception:
        return False


def _fetch_ragflow_profile(authorization: str) -> dict | None:
    settings = get_settings()
    try:
        with httpx.Client(timeout=10.0) as client:
            r = client.get(
                f"{settings.ragflow_api_url.rstrip('/')}/v1/user/info",
                headers={"Authorization": authorization},
            )
        if r.status_code != 200:
            return None
        body = r.json()
        data = body.get("data") if isinstance(body, dict) else None
        return data if isinstance(data, dict) else None
    except Exception as e:
        logger.debug("fetch ragflow profile: %s", e)
        return None


def build_embed_session(db: Session, user: User) -> dict:
    """开通账号、同步文档、返回 SSO token（无需管理员 API Key）。"""
    from app.integrations.knowflow_client import get_knowflow_client_for_user
    from app.services.ragflow_sync_service import sync_accessible_documents

    settings = get_settings()
    link = get_or_create_link(db, user)
    base = resolve_ui_embed_base()
    embed_url = f"{base}/"

    authorization: str | None = None
    sso_message = "未启用 KnowFlow"
    synced_count = 0

    profile: dict | None = None
    if settings.knowflow_enabled:
        try:
            cached = (link.ragflow_access_token or "").strip()
            if _ragflow_auth_valid(cached):
                authorization = cached
                sso_message = "已使用平台会话自动登录 KnowFlow"
                if link.ragflow_user_id:
                    from app.integrations.ragflow_llm_template import ensure_shared_llm_config

                    ensure_shared_llm_config(link.ragflow_user_id)
            else:
                link.ragflow_access_token = None
                db.flush()
                authorization = provision_and_login(link, user)
                sso_message = "已自动登录 KnowFlow（与平台同一账号）"
            if authorization:
                profile = _fetch_ragflow_profile(authorization)
        except RagflowProvisionError as e:
            logger.warning("RAGFlow SSO 失败: %s", e)
            sso_message = f"自动登录失败: {e}"

        kf = get_knowflow_client_for_user(db, user)
        if authorization and kf.enabled():
            from app.services.ragflow_scope_service import (
                ensure_user_scope_datasets,
                sync_user_kb_grants,
            )

            try:
                ensure_user_scope_datasets(db, user, kf)
                sync_user_kb_grants(db, user)
                from app.services.ragflow_sync_service import purge_stale_knowflow_links

                purge_stale_knowflow_links(db)
            except Exception as e:
                logger.warning("RAGFlow 知识库授权同步跳过: %s", e)
            if settings.ragflow_sync_on_embed:
                try:
                    synced = sync_accessible_documents(
                        db, user, limit=settings.ragflow_sync_doc_limit
                    )
                    synced_count = len(synced)
                except Exception as e:
                    logger.warning("RAGFlow 文档同步跳过: %s", e)
        elif authorization and "自动登录" not in sso_message:
            sso_message = "已登录；知识库同步待 RAGFlow 就绪后自动重试"

    return {
        "integration_phase": 4,
        "embed_url": embed_url,
        "ui_direct_url": settings.knowflow_ui_url.rstrip("/"),
        "dataset_name": dataset_name_for_personal(user.id),
        "platform_user_id": str(user.id),
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
