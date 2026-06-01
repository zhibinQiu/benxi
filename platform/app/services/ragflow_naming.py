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


def platform_email_for_user(user) -> str:
    """mapped：每平台用户固定 username@platform.local（避免多人共用同一 QQ/企业邮箱）。"""
    settings = get_settings()
    if (settings.ragflow_account_mode or "").strip().lower() == "shared":
        shared = (settings.ragflow_shared_email or "").strip().lower()
        if shared and is_ragflow_valid_email(shared):
            return shared
    uname = re.sub(r"[^\w._-]+", "_", (user.username or "user").strip().lower())
    uname = re.sub(r"_+", "_", uname).strip("_")[:40] or "user"
    uid_suffix = str(getattr(user, "id", "") or "").replace("-", "")[:8] or "user"
    return f"{uname}-{uid_suffix}@platform.local"


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


def dataset_name_for_personal(user_id: uuid.UUID, db: Session | None = None) -> str:
    settings = get_settings()
    prefix = (settings.ragflow_personal_dataset_prefix or "zt-personal").strip()
    if db is not None:
        from app.models.org import User

        user = db.get(User, user_id)
        login = _slug_token(user.username if user else "")
        return f"{prefix}-{login}-{_id_suffix(user_id)}"
    short = str(user_id).replace("-", "")[:12]
    return f"{prefix}-{short}"


def dataset_display_label_personal(db: Session, user_id: uuid.UUID) -> str:
    from app.models.org import User

    user = db.get(User, user_id)
    login = (user.username if user else "").strip()
    return f"个人·{login}" if login else "个人"


def dataset_name_for_company() -> str:
    settings = get_settings()
    return (settings.ragflow_company_dataset_name or "zt-company").strip()


def dataset_display_label_company() -> str:
    return "公司级"


def dataset_name_for_user(user_id: uuid.UUID, db: Session | None = None) -> str:
    """兼容旧名：等同个人库。"""
    return dataset_name_for_personal(user_id, db)


def dataset_name_for_dept(dept_id: uuid.UUID, db: Session | None = None) -> str:
    settings = get_settings()
    prefix = (settings.ragflow_dept_dataset_prefix or "zt-dept").strip()
    if db is not None:
        from app.models.org import Department

        dept = db.get(Department, dept_id)
        slug = _slug_token(dept.name if dept else "dept")
        return f"{prefix}-{slug}-{_id_suffix(dept_id)}"
    short = str(dept_id).replace("-", "")[:12]
    return f"{prefix}-{short}"


def dataset_display_label_dept(db: Session, dept_id: uuid.UUID) -> str:
    from app.models.org import Department

    dept = db.get(Department, dept_id)
    name = (dept.name if dept else "").strip()
    return f"部门·{name}" if name else "部门"
