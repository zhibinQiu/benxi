"""RAGFlow 账号开通与登录（阶段 2 SSO）。"""

from __future__ import annotations

import logging
import re
import secrets
import subprocess

import httpx

from app.config import get_settings
from app.integrations.ragflow_crypto import rsa_encrypt_password
from app.models.org import User
from app.models.ragflow_link import RagflowAccountLink
from app.integrations.ragflow_llm_template import ensure_shared_llm_config
from app.services.ragflow_naming import platform_email_for_user

logger = logging.getLogger(__name__)


class RagflowProvisionError(RuntimeError):
    pass


def _base_url() -> str:
    return get_settings().ragflow_api_url.rstrip("/")


def _register_user(email: str, nickname: str, password: str) -> str | None:
    """注册并返回 Authorization（code=0 时注册接口常直接返回 token）。"""
    enc = rsa_encrypt_password(password)
    with httpx.Client(timeout=30.0) as client:
        r = client.post(
            f"{_base_url()}/v1/user/register",
            json={"email": email, "nickname": nickname, "password": enc},
        )
    if r.status_code >= 400:
        raise RagflowProvisionError(f"register HTTP {r.status_code}: {r.text[:300]}")
    body = r.json()
    code = body.get("code")
    if code == 0:
        data = body.get("data") if isinstance(body, dict) else None
        if isinstance(data, dict) and data.get("access_token"):
            return str(data["access_token"])
        return None
    if code not in (0, None):
        msg = body.get("message", "") or str(body)
        lower = msg.lower()
        if "registered" in lower or "已注册" in lower or "already registered" in lower:
            return None
        if "registration is disabled" in lower or "注册" in lower and "禁用" in lower:
            raise RagflowProvisionError(
                "RAGFlow 未开放用户注册，请在服务配置中启用 REGISTER_ENABLED"
            )
        raise RagflowProvisionError(msg)
    return None


def _login_user(email: str, password: str) -> str:
    enc = rsa_encrypt_password(password)
    with httpx.Client(timeout=30.0) as client:
        r = client.post(
            f"{_base_url()}/v1/user/login",
            json={"email": email, "password": enc},
        )
    if r.status_code >= 400:
        raise RagflowProvisionError(f"login HTTP {r.status_code}: {r.text[:300]}")
    auth = r.headers.get("Authorization") or r.headers.get("authorization")
    if auth:
        return auth.strip()
    body = r.json()
    if isinstance(body, dict) and body.get("code") == 0:
        data = body.get("data") or {}
        if isinstance(data, dict) and data.get("access_token"):
            return str(data["access_token"])
    raise RagflowProvisionError(body.get("message") or "login 未返回 Authorization")


def ensure_ragflow_password(link: RagflowAccountLink) -> str:
    if link.ragflow_password:
        return link.ragflow_password
    link.ragflow_password = secrets.token_urlsafe(24)
    return link.ragflow_password


def _password_mismatch_message(msg: str) -> bool:
    lower = (msg or "").lower()
    return "password" in lower and ("match" in lower or "不匹配" in lower or "密码" in msg)


def _not_registered_message(msg: str) -> bool:
    lower = (msg or "").lower()
    return "not registered" in lower or "未注册" in lower


def finalize_ragflow_link(
    link: RagflowAccountLink,
    authorization: str,
    user: User | None = None,
    db=None,
) -> None:
    """持久化 RAGFlow 会话，并同步租户 ID / 共享模型配置。"""
    token = (authorization or "").strip()
    if not token:
        return
    link.ragflow_access_token = token
    uid = _fetch_ragflow_user_id(token) or (link.ragflow_user_id or "").strip()
    if not uid:
        return
    if link.ragflow_user_id and link.ragflow_user_id != uid:
        logger.info(
            "RAGFlow 用户 id 已更新: %s → %s",
            link.ragflow_user_id,
            uid,
        )
    link.ragflow_user_id = uid
    ensure_shared_llm_config(uid, db=db)


def recover_ragflow_account(link: RagflowAccountLink, user: User) -> str:
    """密码不一致或账号异常时：清理 RAGFlow 侧旧账号并用新密码重新注册。"""
    email = (link.ragflow_email or platform_email_for_user(user)).strip().lower()
    nickname = (user.display_name or user.username or "用户")[:100]
    if user.username and user.username not in nickname:
        nickname = f"{nickname}({user.username})"[:100]

    link.ragflow_access_token = None
    link.ragflow_user_id = None
    link.ragflow_password = None
    password = ensure_ragflow_password(link)

    _purge_ragflow_user_by_email(email)
    authorization: str | None = None
    try:
        authorization = _register_user(email, nickname, password)
    except RagflowProvisionError as e:
        if not _not_registered_message(str(e)):
            logger.info("RAGFlow recover register: %s", e)
    if not authorization:
        authorization = _login_user(email, password)
    finalize_ragflow_link(link, authorization, user)
    return authorization


def resolve_ragflow_password(link: RagflowAccountLink) -> str:
    settings = get_settings()
    if (settings.ragflow_account_mode or "").strip().lower() == "shared":
        pwd = (settings.ragflow_shared_password or "").strip()
        if pwd:
            link.ragflow_password = pwd
            return pwd
    shared_pwd = (settings.ragflow_shared_password or "").strip()
    if shared_pwd and link.ragflow_password == shared_pwd:
        link.ragflow_password = None
    return ensure_ragflow_password(link)


def _uid_suffix_from_platform_email(email: str) -> str | None:
    m = re.search(r"-([a-f0-9]{8})@platform\.local$", (email or "").strip().lower())
    return m.group(1) if m else None


def _run_ragflow_mysql(sql: str) -> tuple[bool, str]:
    from app.integrations.ragflow_llm_template import _mysql_exec, _mysql_settings

    _, _, _, host, _ = _mysql_settings()
    if host:
        if _mysql_exec(sql):
            return True, ""
    settings = get_settings()
    container = (settings.ragflow_mysql_container or "ragflow-mysql").strip()
    mysql_pwd = (settings.ragflow_mysql_password or "infini_rag_flow").strip()
    db = (settings.ragflow_mysql_db or "rag_flow").strip()
    try:
        proc = subprocess.run(
            [
                "docker",
                "exec",
                container,
                "mysql",
                f"-uroot",
                f"-p{mysql_pwd}",
                db,
                "--default-character-set=utf8mb4",
                "-e",
                sql,
            ],
            capture_output=True,
            text=True,
            timeout=20,
        )
        if proc.returncode != 0:
            err = (proc.stderr or proc.stdout or "").strip()
            return False, err[:300]
        return True, ""
    except Exception as e:
        return False, str(e)


def _purge_ragflow_user_by_email(email: str) -> bool:
    """清理 RAGFlow 中邮箱冲突的旧账号（密码与平台 link 不一致时）。"""
    raw = (email or "").strip().lower()
    if not raw:
        return False
    safe_email = raw.replace("'", "''")
    sql = (
        f"SET @e='{safe_email}'; "
        "SET @uid=(SELECT id FROM user WHERE email=@e LIMIT 1); "
        "DELETE FROM knowledgebase WHERE tenant_id=@uid; "
        "DELETE FROM user_tenant WHERE user_id=@uid OR tenant_id=@uid; "
        "DELETE FROM tenant_llm WHERE tenant_id=@uid; "
        "DELETE FROM tenant WHERE id=@uid; "
        "DELETE FROM user WHERE id=@uid;"
    )
    ok, err = _run_ragflow_mysql(sql)
    if not ok:
        logger.warning("purge RAGFlow user %s failed: %s", raw, err)
    suffix = _uid_suffix_from_platform_email(raw)
    if suffix:
        suffix_ok = _purge_ragflow_user_by_uid_suffix(suffix)
        return ok or suffix_ok
    return ok


def _purge_ragflow_user_by_uid_suffix(suffix: str) -> bool:
    """按平台用户 id 后缀清理历史脏账号（中文邮箱在 MySQL 中可能乱码）。"""
    token = (suffix or "").strip().lower()
    if not re.fullmatch(r"[a-f0-9]{8}", token):
        return False
    pattern = f"%-{token}@platform.local".replace("'", "''")
    sql = (
        f"SET @pat='{pattern}'; "
        "DELETE kb FROM knowledgebase kb "
        "JOIN user u ON kb.tenant_id=u.id "
        "WHERE u.email LIKE @pat; "
        "DELETE ut FROM user_tenant ut "
        "JOIN user u ON ut.user_id=u.id OR ut.tenant_id=u.id "
        "WHERE u.email LIKE @pat; "
        "DELETE tl FROM tenant_llm tl "
        "JOIN user u ON tl.tenant_id=u.id "
        "WHERE u.email LIKE @pat; "
        "DELETE t FROM tenant t "
        "JOIN user u ON t.id=u.id "
        "WHERE u.email LIKE @pat; "
        "DELETE FROM user WHERE email LIKE @pat;"
    )
    ok, err = _run_ragflow_mysql(sql)
    if not ok:
        logger.warning("purge RAGFlow suffix %s failed: %s", token, err)
    return ok


def provision_and_login(link: RagflowAccountLink, user: User, db=None) -> str:
    """创建 RAGFlow 账号（如需）并返回 Web UI 用的 Authorization。"""
    email = link.ragflow_email or platform_email_for_user(user)
    nickname = (user.display_name or user.username or "用户")[:100]
    if user.username and user.username not in nickname:
        nickname = f"{nickname}({user.username})"[:100]
    password = resolve_ragflow_password(link)
    authorization: str | None = None

    if link.ragflow_password:
        try:
            authorization = _login_user(email, password)
        except RagflowProvisionError as e:
            msg = str(e)
            if _password_mismatch_message(msg):
                authorization = recover_ragflow_account(link, user)
            elif not _not_registered_message(msg):
                raise

    if not authorization:
        try:
            authorization = _register_user(email, nickname, password)
        except RagflowProvisionError as e:
            logger.info("RAGFlow register: %s", e)

    if not authorization:
        try:
            authorization = _login_user(email, password)
        except RagflowProvisionError as e:
            msg = str(e)
            if _not_registered_message(msg):
                authorization = _register_user(email, nickname, password)
                if not authorization:
                    authorization = _login_user(email, password)
            elif _password_mismatch_message(msg):
                authorization = recover_ragflow_account(link, user)
            else:
                raise

    if not authorization:
        raise RagflowProvisionError("无法完成 RAGFlow 登录")
    finalize_ragflow_link(link, authorization, user, db=db)
    return authorization


def _fetch_ragflow_user_id(authorization: str) -> str | None:
    try:
        with httpx.Client(timeout=10.0) as client:
            r = client.get(
                f"{_base_url()}/v1/user/info",
                headers={"Authorization": authorization},
            )
        if r.status_code != 200:
            return None
        body = r.json()
        data = body.get("data") if isinstance(body, dict) else None
        if isinstance(data, dict) and data.get("id"):
            return str(data["id"])
    except Exception as e:
        logger.debug("fetch user info: %s", e)
    return None
