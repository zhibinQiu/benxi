"""面向界面的用户展示名（不暴露内部登录名规则）。"""

from __future__ import annotations

from app.models.org import User


def user_display_name(user: User | None) -> str:
    if not user:
        return "未知用户"
    for value in (user.display_name, user.username, user.phone, user.email):
        name = (value or "").strip()
        if name:
            return name
    return "未知用户"
