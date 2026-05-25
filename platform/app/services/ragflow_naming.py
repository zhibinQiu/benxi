"""RAGFlow 知识库命名（无循环依赖）。"""

from __future__ import annotations

import re
import uuid

from app.config import get_settings

# 与 KnowFlow api/apps/user_app.py 注册校验一致（需域名含点，如 x@y.z）
RAGFLOW_EMAIL_RE = re.compile(r"^[\w\._-]+@([\w_-]+\.)+[\w-]{2,}$")


def is_ragflow_valid_email(email: str) -> bool:
    return bool(email and RAGFLOW_EMAIL_RE.match(email.strip()))


def platform_email_for_user(user) -> str:
    """生成可在 RAGFlow 注册/登录的邮箱（无效平台邮箱会回退为 username@platform.local）。"""
    settings = get_settings()
    if (settings.ragflow_account_mode or "").strip().lower() == "shared":
        shared = (settings.ragflow_shared_email or "").strip().lower()
        if shared and is_ragflow_valid_email(shared):
            return shared
    if user.email and "@" in user.email:
        candidate = user.email.strip().lower()
        if is_ragflow_valid_email(candidate):
            return candidate
    uname = re.sub(r"[^\w._-]", "_", (user.username or "user").strip().lower())[:64]
    return f"{uname}@platform.local"


def dataset_name_for_personal(user_id: uuid.UUID) -> str:
    settings = get_settings()
    prefix = (settings.ragflow_personal_dataset_prefix or "zt-personal").strip()
    short = str(user_id).replace("-", "")[:12]
    return f"{prefix}-{short}"


def dataset_name_for_company() -> str:
    settings = get_settings()
    return (settings.ragflow_company_dataset_name or "zt-company").strip()


def dataset_name_for_user(user_id: uuid.UUID) -> str:
    """兼容旧名：等同个人库。"""
    return dataset_name_for_personal(user_id)


def dataset_name_for_dept(dept_id: uuid.UUID) -> str:
    settings = get_settings()
    prefix = (settings.ragflow_dept_dataset_prefix or "zt-dept").strip()
    short = str(dept_id).replace("-", "")[:12]
    return f"{prefix}-{short}"
