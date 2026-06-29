"""Agent 工具循环用短生命周期 DB 会话 — LLM / 外部 I/O 等待期间不占连接池。"""

from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from app.core.async_db import resolve_db_user
from app.database import SessionLocal
from app.models.org import User


def coerce_user_id(user: User | uuid.UUID) -> uuid.UUID:
    """从 User 或 UUID 提取 id；勿在 Session 关闭后访问 User 其它字段。"""
    if isinstance(user, uuid.UUID):
        return user
    uid = getattr(user, "id", None)
    if uid is None:
        raise ValueError("无效用户")
    return uid if isinstance(uid, uuid.UUID) else uuid.UUID(str(uid))


class AgentLoopSession:
    """按轮次开/关 Session：工具执行前 open，LLM 等待前 release。"""

    __slots__ = ("user_id", "_db")

    def __init__(self, user_id: uuid.UUID) -> None:
        self.user_id = user_id
        self._db: Session | None = None

    @property
    def is_open(self) -> bool:
        return self._db is not None

    def open(self) -> tuple[Session, User]:
        if self._db is None:
            self._db = SessionLocal()
        return self._db, resolve_db_user(self._db, self.user_id)

    def release_before_io(self) -> None:
        if self._db is None:
            return
        try:
            self._db.commit()
        except Exception:
            self._db.rollback()
            raise
        finally:
            self._db.close()
            self._db = None

    def close(self) -> None:
        self.release_before_io()
