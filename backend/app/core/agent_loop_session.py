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
    """按轮次开/关 Session：工具执行前 open，LLM 等待前 release。

    open() 是幂等的——Session 已打开时直接返回，避免重复 resolve_db_user
    （远程 DB 每次 ~500-900ms 轮询开销）。
    """

    __slots__ = ("user_id", "_db", "_cached_user")

    def __init__(self, user_id: uuid.UUID) -> None:
        self.user_id = user_id
        self._db: Session | None = None
        self._cached_user: User | None = None

    @property
    def is_open(self) -> bool:
        return self._db is not None

    def open(self) -> tuple[Session, User]:
        """获取当前 Session + User。

        幂等：Session 已打开时直接返回缓存的 db/user，不再关闭重建。
        Session 关闭后重新 open() 始终重新 resolve_db_user，因为 User
        是 ORM 对象，跨越 session 访问字段会触发 DetachedInstanceError。
        """
        if self._db is not None:
            return self._db, self._cached_user
        self.release_before_io()
        self._db = SessionLocal()
        self._cached_user = resolve_db_user(self._db, self.user_id)
        return self._db, self._cached_user

    def release_before_io(self) -> None:
        """提交事务并归还连接；User 缓存保留供下次 open() 复用。"""
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
        self._cached_user = None
