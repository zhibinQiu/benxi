"""RAGFlow 知识库命名（无循环依赖）。"""

from __future__ import annotations

import re
import uuid
from typing import TYPE_CHECKING

from app.config import get_settings

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

# 与 KnowFlow api/apps/user_app.py 注册校验一致（需域名含点，如 x@y.z）
RAGFLOW_EMAIL_RE = re.compile(r"^[\w\._-]+@([\w_-]+\.)+[\w-]{2,}$")


def is_ragflow_valid_email(email: str) -> bool:
    return bool(email and RAGFLOW_EMAIL_RE.match(email.strip()))


def _ascii_local_slug(text: str, *, max_len: int = 24) -> str:
    """RAGFlow 登录邮箱 local 段仅 ASCII，避免 MySQL 字符集导致开户/清理失败。"""
    slug = re.sub(
        r"[^a-z0-9._-]+", "_", (text or "").strip().lower(), flags=re.ASCII
    )
    slug = re.sub(r"_+", "_", slug).strip("_")
    return slug[:max_len]


def platform_email_for_user(user) -> str:
    """mapped：每平台用户固定 username@platform.local（避免多人共用同一 QQ/企业邮箱）。"""
    settings = get_settings()
    if (settings.ragflow_account_mode or "").strip().lower() == "shared":
        shared = (settings.ragflow_shared_email or "").strip().lower()
        if shared and is_ragflow_valid_email(shared):
            return shared
    uid_suffix = str(getattr(user, "id", "") or "").replace("-", "")[:8] or "user"
    uname = _ascii_local_slug(user.username or "user")
    local = f"{uname}-{uid_suffix}" if uname else f"u-{uid_suffix}"
    return f"{local}@platform.local"


def _slug_token(text: str, *, max_len: int = 24) -> str:
    """RAGFlow 知识库名可用片段（保留中文、字母数字）。"""
    raw = (text or "").strip()
    if not raw:
        return "unknown"
    s = re.sub(r"[^\w\u4e00-\u9fff\-]+", "-", raw, flags=re.UNICODE)
    s = re.sub(r"-+", "-", s).strip("-")
    return (s[:max_len] or "unknown")


def _id_suffix(value: uuid.UUID, *, length: int = 6) -> str:
    return str(value).replace("-", "")[:length]


_LEGACY_DEPT_RE = re.compile(r"^zt-dept-([a-f0-9]{6})$", re.I)
_NAME_SUFFIX_RE = re.compile(r"-([a-f0-9]{6})$")


def dept_id_from_name_suffix(db: Session, suffix: str) -> uuid.UUID | None:
    """由知识库名中的 6 位 id 后缀反查部门 UUID。"""
    from sqlalchemy import select

    from app.models.org import Department

    s = (suffix or "").strip().lower()
    if len(s) != 6:
        return None
    for dept in db.scalars(select(Department)).all():
        if str(dept.id).replace("-", "")[:6].lower() == s:
            return dept.id
    return None


def dept_id_from_dataset_name(db: Session, name: str) -> uuid.UUID | None:
    """从 zt-dept-xxxxxx 或 部门名-xxxxxx 解析部门 id。"""
    raw = (name or "").strip()
    if not raw:
        return None
    m = _LEGACY_DEPT_RE.match(raw)
    if m:
        return dept_id_from_name_suffix(db, m.group(1))
    m2 = _NAME_SUFFIX_RE.search(raw)
    if m2:
        return dept_id_from_name_suffix(db, m2.group(1))
    return None


def _user_visible_name(user) -> str:
    if not user:
        return "我的"
    name = (getattr(user, "display_name", None) or "").strip()
    if name:
        return name
    login = (getattr(user, "username", None) or "").strip()
    return login or "我的"


def _needs_global_unique_dataset_name() -> bool:
    """管理员 API Key 建库时，库名需带短后缀避免跨用户冲突。"""
    return bool((get_settings().ragflow_api_key or "").strip())


def dataset_display_label_personal(db: Session, user_id: uuid.UUID) -> str:
    from app.models.org import User

    return _user_visible_name(db.get(User, user_id))


def dataset_name_for_personal(user_id: uuid.UUID, db: Session | None = None) -> str:
    if db is not None:
        from app.models.org import User

        base = _slug_token(_user_visible_name(db.get(User, user_id)), max_len=40)
        if _needs_global_unique_dataset_name():
            return f"{base}-{_id_suffix(user_id)}"
        return base
    settings = get_settings()
    prefix = (settings.ragflow_personal_dataset_prefix or "zt-personal").strip()
    return f"{prefix}-{_id_suffix(user_id)}"


def dataset_display_label_company() -> str:
    return "公司"


def dataset_name_for_company() -> str:
    return dataset_display_label_company()


def dataset_name_for_user(user_id: uuid.UUID, db: Session | None = None) -> str:
    """兼容旧名：等同个人库。"""
    return dataset_name_for_personal(user_id, db)


def dataset_display_label_dept(db: Session, dept_id: uuid.UUID) -> str:
    from app.models.org import Department

    dept = db.get(Department, dept_id)
    name = (dept.name if dept else "").strip()
    return name or "部门"


def dataset_name_for_dept(dept_id: uuid.UUID, db: Session | None = None) -> str:
    if db is not None:

        base = _slug_token(dataset_display_label_dept(db, dept_id), max_len=40)
        if _needs_global_unique_dataset_name():
            return f"{base}-{_id_suffix(dept_id)}"
        return base
    settings = get_settings()
    prefix = (settings.ragflow_dept_dataset_prefix or "zt-dept").strip()
    return f"{prefix}-{_id_suffix(dept_id)}"


def legacy_dataset_name_for_personal(user_id: uuid.UUID) -> str:
    prefix = (get_settings().ragflow_personal_dataset_prefix or "zt-personal").strip()
    return f"{prefix}-{_id_suffix(user_id)}"


def legacy_dataset_name_for_dept(dept_id: uuid.UUID) -> str:
    prefix = (get_settings().ragflow_dept_dataset_prefix or "zt-dept").strip()
    return f"{prefix}-{_id_suffix(dept_id)}"


def legacy_dataset_name_for_company() -> str:
    return (get_settings().ragflow_company_dataset_name or "zt-company").strip()


def legacy_dataset_name_for_platform_user(user_id: uuid.UUID) -> str:
    """更早期每用户单库命名 zt-platform-{id 前 8 位}。"""
    prefix = (get_settings().ragflow_dataset_prefix or "zt-platform").strip()
    return f"{prefix}-{_id_suffix(user_id, length=8)}"


def legacy_scope_dataset_names(scope: str, scope_key: str) -> list[str]:
    """历史技术库名（用于展示映射与复用旧 dataset）。"""
    names: list[str] = []
    if scope == "company":
        names.append(legacy_dataset_name_for_company())
        return names
    try:
        key_uuid = uuid.UUID(scope_key)
    except ValueError:
        return names
    if scope == "department":
        names.append(legacy_dataset_name_for_dept(key_uuid))
    else:
        names.append(legacy_dataset_name_for_personal(key_uuid))
        names.append(legacy_dataset_name_for_platform_user(key_uuid))
    return names
