from collections.abc import Generator

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
    """本机 PG + 远程依赖（hybrid remote-dev）仍用正常连接池，避免 RAGFlow 阻塞时耗尽 8 条连接。"""
    if settings.remote_deps and not _uses_local_database(settings.database_url):
        pool_size = 3
        max_overflow = 5
        connect_timeout = max(settings.db_connect_timeout, 25)
    else:
        pool_size = settings.db_pool_size
        max_overflow = settings.db_max_overflow
        connect_timeout = settings.db_connect_timeout
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
