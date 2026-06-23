"""AI 智能体运行时注入 — 每轮动态元数据，不进常驻层。"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from app.models.org import User

_DEFAULT_TZ = ZoneInfo("Asia/Shanghai")


def build_runtime_context(
    *,
    channel: str,
    user: User | None = None,
    conversation_id: str | None = None,
    locale: str = "zh-CN",
) -> str:
    """拼装当前轮次运行时信息（时间、渠道、用户偏好等）。"""
    now = datetime.now(timezone.utc).astimezone(_DEFAULT_TZ)
    lines = [
        "【运行时】",
        f"- 当前时间：{now.strftime('%Y-%m-%d %H:%M')} CST",
        f"- 渠道：{channel}",
        f"- 语言：{locale}",
    ]
    if user is not None:
        display = (user.display_name or user.username or "").strip()
        if display:
            lines.append(f"- 用户：{display}")
    if conversation_id:
        lines.append(f"- 会话：{conversation_id}")
    return "\n".join(lines)


def normalize_channel(channel: str | None) -> str:
    text = (channel or "").strip() or "ai-home"
    return text[:64]
