"""用户登录标识：手机号 / 用户名解析与唯一性校验。"""

from __future__ import annotations

import re
import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.phone import bootstrap_login_id, is_bootstrap_login_id, normalize_phone
from app.models.org import User

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_USERNAME_MIN = 2
_USERNAME_MAX = 64


def normalize_email(value: str) -> str:
    email = (value or "").strip().lower()
    if not email or not _EMAIL_RE.match(email):
        raise ValueError("请输入有效的邮箱地址")
    if len(email) > 255:
        raise ValueError("邮箱过长")
    return email


def normalize_username(value: str) -> str:
    name = (value or "").strip()
    if len(name) < _USERNAME_MIN:
        raise ValueError(f"用户名至少 {_USERNAME_MIN} 个字符")
    if len(name) > _USERNAME_MAX:
        raise ValueError(f"用户名不超过 {_USERNAME_MAX} 个字符")
    if is_bootstrap_login_id(name):
        raise ValueError("该用户名不可使用")
    return name


def find_user_by_login_account(db: Session, account: str) -> User | None:
    """按手机号（含系统管理员号）或用户名查找用户（用户名不区分大小写）。"""
    raw = (account or "").strip()
    if not raw:
        return None
    if is_bootstrap_login_id(raw):
        return db.scalar(select(User).where(User.phone == bootstrap_login_id()))
    try:
        phone = normalize_phone(raw)
        user = db.scalar(select(User).where(User.phone == phone))
        if user:
            return user
    except ValueError:
        pass
    return db.scalar(
        select(User).where(func.lower(User.username) == raw.lower())
    )


def email_taken(db: Session, email: str, *, exclude_user_id: uuid.UUID | None = None) -> bool:
    norm = normalize_email(email)
    stmt = select(User.id).where(func.lower(User.email) == norm)
    if exclude_user_id:
        stmt = stmt.where(User.id != exclude_user_id)
    return db.scalar(stmt) is not None


def username_taken(
    db: Session, username: str, *, exclude_user_id: uuid.UUID | None = None
) -> bool:
    norm = normalize_username(username)
    stmt = select(User.id).where(func.lower(User.username) == norm.lower())
    if exclude_user_id:
        stmt = stmt.where(User.id != exclude_user_id)
    return db.scalar(stmt) is not None


def phone_taken(
    db: Session, phone: str, *, exclude_user_id: uuid.UUID | None = None
) -> bool:
    norm = normalize_phone(phone)
    stmt = select(User.id).where(User.phone == norm)
    if exclude_user_id:
        stmt = stmt.where(User.id != exclude_user_id)
    return db.scalar(stmt) is not None
