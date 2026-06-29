"""认证会话：单账号单会话（token version）。"""

from __future__ import annotations

import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

from sqlalchemy import update
from sqlalchemy.orm import Session

from app.core.security import create_access_token, create_refresh_token
from app.database import SessionLocal
from app.models.org import User
from app.schemas.auth import TokenResponse

_LAST_SEEN_TOUCH_INTERVAL = timedelta(seconds=60)
_last_seen_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="last_seen")


def bump_auth_token_version(db: Session, user: User) -> int:
    user.auth_token_version = (user.auth_token_version or 0) + 1
    db.flush()
    return user.auth_token_version


def build_token_response(user_id: uuid.UUID, token_version: int) -> TokenResponse:
    subject = str(user_id)
    extra = {"ver": token_version}
    return TokenResponse(
        access_token=create_access_token(subject, extra),
        refresh_token=create_refresh_token(subject, extra),
    )


def validate_token_version(user: User, payload: dict) -> None:
    from app.core.exceptions import unauthorized

    token_ver = payload.get("ver")
    user_ver = user.auth_token_version or 0
    if user_ver > 0:
        if token_ver != user_ver:
            raise unauthorized(
                "账号已在其他设备登录，请重新登录",
                reason="session_replaced",
            )
    elif token_ver is not None and token_ver != 0:
        raise unauthorized("登录已失效，请重新登录", reason="session_expired")


def touch_user_last_seen_async(user_id: uuid.UUID) -> None:
    """异步更新活跃时间，避免每个请求在鉴权路径里 commit。"""
    from app.services.online_presence_service import mark_user_online

    mark_user_online(user_id)

    def _run() -> None:
        db = SessionLocal()
        try:
            now = datetime.now(timezone.utc)
            threshold = now - _LAST_SEEN_TOUCH_INTERVAL
            result = db.execute(
                update(User)
                .where(
                    User.id == user_id,
                    (User.last_seen_at.is_(None)) | (User.last_seen_at < threshold),
                )
                .values(last_seen_at=now)
            )
            if result.rowcount:
                db.commit()
        except Exception:
            db.rollback()
        finally:
            db.close()

    _last_seen_executor.submit(_run)


def shutdown_last_seen_executor() -> None:
    """进程退出时释放 last_seen 线程池。"""
    _last_seen_executor.shutdown(wait=False)
