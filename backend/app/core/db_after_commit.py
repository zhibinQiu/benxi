"""在 SQLAlchemy 会话 commit 成功后再执行回调，避免 Celery 读到未提交数据。"""

from __future__ import annotations

import logging
from collections.abc import Callable

from sqlalchemy import event
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


def run_after_commit(db: Session, callback: Callable[[], None]) -> None:
    queue: list[Callable[[], None]] = db.info.setdefault("after_commit_callbacks", [])
    if not db.info.get("_after_commit_hooks_registered"):
        db.info["_after_commit_hooks_registered"] = True

        @event.listens_for(db, "after_commit")
        def _run_pending_callbacks(session: Session) -> None:
            pending = session.info.pop("after_commit_callbacks", [])
            for fn in pending:
                try:
                    fn()
                except Exception:
                    logger.exception("after_commit 回调执行失败")

        @event.listens_for(db, "after_rollback")
        def _clear_pending_callbacks(session: Session) -> None:
            session.info.pop("after_commit_callbacks", None)

    queue.append(callback)
