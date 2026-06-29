"""当前会话窗口内的对话历史 — 不混入其他 session 的记录。"""

from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from app.core.chat_context import trim_chat_history
from app.schemas.ai_chat import AiChatMessage
from app.services import platform_chat_store

_AI_HOME_SCOPE = "ai-home"


def resolve_session_chat_history(
    db: Session,
    *,
    user_id: uuid.UUID,
    scope: str,
    conversation_id: str | None,
    client_history: list[AiChatMessage] | None,
) -> list[AiChatMessage]:
    """解析本轮可用 history：有 conversation_id 时以服务端该会话为准。"""
    client_rows = list(client_history or [])

    if (
        conversation_id
        and str(conversation_id).strip()
        and scope in platform_chat_store._VALID_SCOPES
    ):
        try:
            payload = platform_chat_store.list_messages(
                db,
                user_id=user_id,
                scope=scope,
                conversation_id=str(conversation_id).strip(),
                limit=40,
            )
            rows = payload.get("messages") or []
            server_history = [
                AiChatMessage(role=str(row["role"]), content=str(row["content"]))
                for row in rows
                if row.get("role") in ("user", "assistant") and str(row.get("content") or "").strip()
            ]
            return trim_chat_history(server_history)
        except Exception:
            pass

    # 新会话或未持久化：仅用客户端当前窗口（不含其他 session 的服务端记录）
    return trim_chat_history(client_rows)


SESSION_CONTEXT_RULE = (
    "上下文：仅依据【当前会话窗口】内的上文作答；"
    "多轮对话中当前输入常是对前文的追问或补充，须结合会话内全部上文理解真实诉求，"
    "勿将短句孤立解读；"
    "勿引用、推测或延续其他对话 session 的内容；"
    "用户未在本会话提及的信息不得当作已知事实。"
)
