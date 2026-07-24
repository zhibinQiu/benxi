"""Agent 工具循环用短生命周期 DB 会话 — LLM / 外部 I/O 等待期间不占连接池。"""

from __future__ import annotations

import uuid

from sqlalchemy.orm import Session, object_session

from app.core.async_db import resolve_db_user
from app.database import SessionLocal
from app.models.org import User


def coerce_user_id(user: User | uuid.UUID) -> uuid.UUID:
    """从 User 或 UUID 提取 id；兼容 Session 已关闭的 detached User。"""
    if isinstance(user, uuid.UUID):
        return user
    from sqlalchemy import inspect as sa_inspect

    # 优先 identity，避免对 expired/detached 属性触发 refresh
    try:
        inst = sa_inspect(user)
        if inst is not None and inst.identity:
            uid = inst.identity[0]
            return uid if isinstance(uid, uuid.UUID) else uuid.UUID(str(uid))
    except Exception:
        pass
    try:
        uid = user.id
    except Exception as exc:
        raise ValueError("无效用户") from exc
    if uid is None:
        raise ValueError("无效用户")
    return uid if isinstance(uid, uuid.UUID) else uuid.UUID(str(uid))


class AgentLoopSession:
    """按轮次开/关 Session：工具执行前 open，LLM 等待前 release。

    约定：
    - release_before_io() 后不得再使用此前 open() 返回的 db/user
    - 任何 await I/O 之后若需访问 ORM，必须重新 open()
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
        """获取当前 Session + 绑定到该 Session 的 User。

        幂等：Session 已打开且 User 仍绑定本 Session 时直接返回。
        否则新建 Session 并 resolve_db_user。
        """
        if self._db is not None and self._cached_user is not None:
            if object_session(self._cached_user) is self._db:
                return self._db, self._cached_user
            # Session 仍开但 User 已游离 — 重新绑定
            self._cached_user = resolve_db_user(self._db, self.user_id)
            return self._db, self._cached_user

        self.release_before_io()
        self._db = SessionLocal()
        self._cached_user = resolve_db_user(self._db, self.user_id)
        return self._db, self._cached_user

    def release_before_io(self) -> None:
        """提交事务并归还连接；同时丢弃 User 缓存，杜绝 DetachedInstanceError。"""
        if self._db is None:
            self._cached_user = None
            return
        try:
            self._db.commit()
        except Exception:
            self._db.rollback()
            raise
        finally:
            self._db.close()
            self._db = None
            self._cached_user = None

    def close(self) -> None:
        self.release_before_io()
