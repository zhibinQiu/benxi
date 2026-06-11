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


def _knowflow_catalog_ready(db: Session, user: User, link: RagflowAccountLink) -> bool:
    """分级知识库已在平台登记时，embed-session 可走 SSO 快路径（跳过全量 reconcile）。"""
    from app.services.ragflow_scope_service import (
        _dept_ids_for_kb_access,
        _get_registry,
        _registry_scope_for_dept,
        _user_has_personal_kb,
    )

    if not (link.ragflow_user_id or "").strip():
        return False
    if _user_has_personal_kb(db, user):
        return True
    for dept_id in _dept_ids_for_kb_access(db, user):
        reg = _get_registry(db, _registry_scope_for_dept(db, dept_id), str(dept_id))
        if reg and (reg.ragflow_dataset_id or "").strip():
            return True
    return False


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


def _embed_catalog_empty(user_auth: str | None) -> bool:
    if not user_auth:
        return True
    try:
        from app.integrations.ragflow_client import RagflowClient

        return len(RagflowClient(session_auth=user_auth).list_datasets()) == 0
    except Exception:
        return True


def _bootstrap_embed_auth(db: Session) -> tuple[str | None, dict | None]:
    from app.core.phone import bootstrap_login_id

    bootstrap = db.scalar(select(User).where(User.phone == bootstrap_login_id()))
    if not bootstrap:
        return None, None
    boot_auth = get_user_ragflow_auth(db, bootstrap)
    if not boot_auth or not _ragflow_auth_valid(boot_auth):
        return None, None
    valid, boot_profile = _ragflow_user_info(boot_auth)
    if not valid:
        return None, None
    return boot_auth, boot_profile


def resolve_embed_ragflow_authorization(
    db: Session,
    user: User,
    *,
    user_auth: str | None,
    user_profile: dict | None,
) -> tuple[str | None, dict | None]:
    """iframe SSO：管理员/普通用户在 mapped 模式下共用 bootstrap 租户列举库，主题脚本过滤可见范围。"""
    from app.core.permissions import user_is_system_admin
    from app.core.platform_admin import is_bootstrap_admin

    if is_bootstrap_admin(user):
        return user_auth, user_profile

    boot_auth, boot_profile = _bootstrap_embed_auth(db)

    if user_is_system_admin(db, user):
        if boot_auth:
            logger.info(
                "系统管理员 %s 切片管理使用 bootstrap KnowFlow 会话浏览全员知识库",
                user.username,
            )
            return boot_auth, boot_profile
        return user_auth, user_profile

    return user_auth, user_profile


def build_embed_session(
    db: Session, user: User, *, sync_catalog: bool | None = None
) -> dict:
    """开通账号、返回 SSO token；目录同步由 sync_catalog / 配置控制。"""
    from app.core.permissions import user_is_system_admin
    from app.services.ragflow_scope_service import (
        dept_suffix_labels_for_theme,
        knowflow_kb_labels_for_user,
    )
    settings = get_settings()
    is_system_admin = user_is_system_admin(db, user)
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
        from app.integrations.ragflow_http import should_attempt_ragflow_http

        try:
            cached = (link.ragflow_access_token or "").strip()
            valid, profile = _ragflow_user_info(cached)
            if valid and cached:
                authorization = cached
                sso_message = "知识服务已就绪"
            elif should_attempt_ragflow_http():
                link.ragflow_access_token = None
                db.flush()
                from app.database import release_db_connection

                release_db_connection(db)
                authorization = provision_and_login(link, user)
                sso_message = "知识服务已就绪"
                if authorization:
                    _, profile = _ragflow_user_info(authorization)
            else:
                sso_message = KNOWLEDGE_SERVICE_UNAVAILABLE
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
                provision_knowflow_catalog_for_admin,
                reconcile_user_knowflow_catalog,
                reconcile_user_knowflow_kb_acl,
            )

            try:
                if link.ragflow_user_id:
                    from app.core.platform_admin import is_bootstrap_admin
                    from app.integrations.ragflow_llm_template import (
                        ensure_shared_llm_config,
                        sync_all_tenant_llm_configs,
                    )
                    from app.integrations.ragflow_rbac import ensure_ragflow_global_admin

                    try:
                        ensure_shared_llm_config(link.ragflow_user_id, db=db)
                    except Exception as e:
                        logger.warning("RAGFlow 模型配置同步跳过: %s", e)
                    if is_bootstrap_admin(user):
                        try:
                            pushed = sync_all_tenant_llm_configs(db)
                            if pushed:
                                logger.info(
                                    "bootstrap 已将模型配置同步到 %s 个 KnowFlow 租户",
                                    pushed,
                                )
                        except Exception as e:
                            logger.warning("全员 KnowFlow 模型配置推送跳过: %s", e)
                    if is_system_admin:
                        try:
                            ensure_ragflow_global_admin(link.ragflow_user_id)
                        except Exception as e:
                            logger.warning("RAGFlow 全局 admin 授予跳过: %s", e)

                if is_system_admin:
                    try:
                        provision_knowflow_catalog_for_admin(db, user)
                    except Exception as e:
                        logger.warning("系统管理员 KnowFlow 目录预登记跳过: %s", e)

                if do_sync:
                    result = reconcile_user_knowflow_catalog(
                        db,
                        user,
                        sync_limit=settings.ragflow_sync_doc_limit,
                        sync_documents=settings.ragflow_sync_on_embed,
                    )
                    synced_count = int(result.get("synced_documents") or 0)
                    if settings.ragflow_sync_on_embed:
                        from app.services.ragflow_sync_service import (
                            purge_stale_knowflow_links,
                        )

                        purge_stale_knowflow_links(db)
                else:
                    acl_result = reconcile_user_knowflow_kb_acl(db, user)
                    synced_count = int(acl_result.get("synced_documents") or 0)
            except Exception as e:
                logger.warning("RAGFlow 知识库目录同步跳过: %s", e)
        elif authorization and "自动登录" not in sso_message:
            sso_message = "知识服务已就绪，文档正在后台同步"

    embed_auth, embed_profile = resolve_embed_ragflow_authorization(
        db,
        user,
        user_auth=authorization,
        user_profile=profile,
    )

    display_name = (user.display_name or user.username or "用户").strip()
    if embed_profile and not user_is_system_admin(db, user):
        embed_profile = {
            **embed_profile,
            "nickname": display_name,
        }

    kb_labels = knowflow_kb_labels_for_user(db, user)
    dept_suffix_labels = dept_suffix_labels_for_theme(db, user)

    return {
        "integration_phase": 4,
        "embed_url": embed_url,
        "ui_direct_url": settings.knowflow_ui_browser_base,
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
            "is_system_admin": is_system_admin,
            "kb_visibility_strict": not is_system_admin,
        },
        "sso": {
            "ready": bool(embed_auth),
            "authorization": embed_auth,
            "access_token": (embed_profile or {}).get("access_token")
            if embed_profile
            else None,
            "user_info": (
                {
                    "nickname": embed_profile.get("nickname"),
                    "email": embed_profile.get("email"),
                    "avatar": embed_profile.get("avatar"),
                }
                if embed_profile
                else None
            ),
            "message": sso_message,
        },
    }
