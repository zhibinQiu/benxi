"""数据库启动引导：全量 schema 迁移 vs 轻量种子同步。"""

from __future__ import annotations

import logging

from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.bootstrap import bootstrap_db
from app.config import get_settings
from app.core.bootstrap_user import enforce_unique_bootstrap_admin
from app.database import SessionLocal, engine
from app.schema_migrate import (
    backfill_user_phones,
    is_platform_schema_current,
    run_all_schema_migrations,
)

_logger = logging.getLogger(__name__)

BootstrapMode = str  # auto | full | light | off


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
    bootstrap_db(db)
    enforce_unique_bootstrap_admin(db)
    db.commit()


def bootstrap_database(db_engine: Engine | None = None) -> BootstrapMode:
    db_engine = db_engine or engine
    mode = resolve_bootstrap_mode(db_engine)
    if mode == "off":
        _logger.info("跳过数据库启动引导（DB_STARTUP_BOOTSTRAP=off）")
        return mode
    if mode == "full":
        _logger.info("执行全量 schema 迁移与种子数据同步")
        run_all_schema_migrations(db_engine)
    else:
        _logger.info("schema 已是最新，仅同步权限/管理员种子数据")
    db = SessionLocal()
    try:
        run_seed_bootstrap(db)
    finally:
        db.close()
    return mode
