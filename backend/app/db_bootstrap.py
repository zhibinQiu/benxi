"""数据库启动引导：全量 schema 迁移 vs 轻量种子同步。"""

from __future__ import annotations

import logging

from sqlalchemy import text
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.orm import Session

from app.bootstrap import bootstrap_db
from app.config import get_settings
from app.core.bootstrap_user import enforce_unique_bootstrap_admin
from app.database import SessionLocal, engine
from app.schema_migrate import (
    backfill_user_phones,
    is_platform_schema_current,
    migrate_legacy_platform_branding,
    run_all_schema_migrations,
    run_light_schema_patches,
)

_logger = logging.getLogger(__name__)

BootstrapMode = str  # auto | full | light | off

# 多 worker 启动时仅一个进程执行 bootstrap（PostgreSQL advisory lock）
_BOOTSTRAP_ADVISORY_LOCK_KEY = 0x5A746974


def resolve_bootstrap_mode(db_engine: Engine | None = None) -> BootstrapMode:
    settings = get_settings()
    raw = (settings.db_startup_bootstrap or "auto").strip().lower()
    if raw in {"full", "light", "off"}:
        return raw
    db_engine = db_engine or engine
    if is_platform_schema_current(db_engine):
        return "light"
    return "full"


def run_seed_bootstrap(db: Session) -> None:
    backfill_user_phones(db)
    migrate_legacy_platform_branding(db)
    bootstrap_db(db)
    from app.services.agent_skill_bootstrap import ensure_example_agent_skills

    ensure_example_agent_skills(db)
    enforce_unique_bootstrap_admin(db)
    db.commit()


def _run_bootstrap(db_engine: Engine, mode: BootstrapMode) -> BootstrapMode:
    if mode == "full":
        _logger.info("执行全量 schema 迁移与种子数据同步")
        run_all_schema_migrations(db_engine)
    else:
        _logger.info("schema 已是最新，仅同步权限/管理员种子数据")
    run_light_schema_patches(db_engine)
    db = SessionLocal()
    try:
        run_seed_bootstrap(db)
    finally:
        db.close()
    return mode


def _supports_advisory_lock(db_engine: Engine) -> bool:
    return db_engine.dialect.name == "postgresql"


def _try_advisory_lock(conn: Connection) -> bool:
    return bool(
        conn.execute(
            text("SELECT pg_try_advisory_lock(:key)"),
            {"key": _BOOTSTRAP_ADVISORY_LOCK_KEY},
        ).scalar()
    )


def _advisory_unlock(conn: Connection) -> None:
    conn.execute(
        text("SELECT pg_advisory_unlock(:key)"),
        {"key": _BOOTSTRAP_ADVISORY_LOCK_KEY},
    )


def _wait_for_bootstrap_lock(db_engine: Engine) -> None:
    with db_engine.connect() as conn:
        conn.execute(
            text("SELECT pg_advisory_lock(:key)"),
            {"key": _BOOTSTRAP_ADVISORY_LOCK_KEY},
        )
        _advisory_unlock(conn)
        conn.commit()


def bootstrap_database(db_engine: Engine | None = None) -> BootstrapMode:
    db_engine = db_engine or engine
    mode = resolve_bootstrap_mode(db_engine)
    if mode == "off":
        _logger.info("跳过数据库启动引导（DB_STARTUP_BOOTSTRAP=off）")
        return mode

    if not _supports_advisory_lock(db_engine):
        return _run_bootstrap(db_engine, mode)

    conn = db_engine.connect()
    try:
        if _try_advisory_lock(conn):
            try:
                return _run_bootstrap(db_engine, mode)
            finally:
                _advisory_unlock(conn)
                conn.commit()
    finally:
        conn.close()

    _logger.info("等待其他 worker 完成数据库启动引导…")
    _wait_for_bootstrap_lock(db_engine)
    _logger.info("数据库启动引导已由其他 worker 完成")
    return resolve_bootstrap_mode(db_engine)
