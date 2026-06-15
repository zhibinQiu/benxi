from collections.abc import Generator
from contextlib import contextmanager

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import QueuePool

from app.config import get_settings


class Base(DeclarativeBase):
    pass


def _uses_local_database(database_url: str) -> bool:
    return "@127.0.0.1:" in database_url or "@localhost:" in database_url


def _engine_kwargs(settings) -> dict:
    """连接池统一走 settings（DB_POOL_SIZE / DB_MAX_OVERFLOW）；远程 PG 仅加长 connect_timeout。"""
    connect_timeout = settings.db_connect_timeout
    pool_size = settings.db_pool_size
    max_overflow = settings.db_max_overflow
    if settings.remote_deps and not _uses_local_database(settings.database_url):
        connect_timeout = max(connect_timeout, 25)
        # 远程共享 Postgres max_connections 有限，避免单进程占满连接
        pool_size = min(pool_size, 6)
        max_overflow = min(max_overflow, 4)
    return {
        "poolclass": QueuePool,
        "pool_size": pool_size,
        "max_overflow": max_overflow,
        "pool_timeout": settings.db_pool_timeout,
        "pool_recycle": settings.db_pool_recycle,
        "pool_pre_ping": True,
        "connect_args": {"connect_timeout": connect_timeout},
        "echo": settings.debug_sql,
    }


def _engine():
    settings = get_settings()
    return create_engine(settings.database_url, **_engine_kwargs(settings))


engine = _engine()
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)

_health_engine: Engine | None = None


def _health_engine_instance() -> Engine:
    """独立小池供 /health 使用，主池被占满时仍能快速探活。"""
    global _health_engine
    if _health_engine is None:
        settings = get_settings()
        _health_engine = create_engine(
            settings.database_url,
            pool_size=1,
            max_overflow=0,
            pool_timeout=2,
            pool_pre_ping=True,
            connect_args={"connect_timeout": 2},
        )
    return _health_engine


def release_db_connection(db: Session) -> None:
    """长耗时外部 I/O 前归还连接，避免占满连接池。"""
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise


def check_database_health() -> bool:
    try:
        with _health_engine_instance().connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def session_scope():
    """后台任务短生命周期会话：自动 commit/rollback 并归还连接。"""
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
