from collections.abc import Generator
from contextlib import contextmanager
import logging
import time

from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import QueuePool

from app.config import get_settings

_logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    pass


def _uses_local_database(database_url: str) -> bool:
    return "@127.0.0.1:" in database_url or "@localhost:" in database_url


def _postgres_connect_args(settings, database_url: str) -> dict:
    connect_timeout = settings.db_connect_timeout
    if settings.remote_deps and not _uses_local_database(database_url):
        connect_timeout = max(connect_timeout, 25)
    connect_args: dict = {"connect_timeout": connect_timeout}
    timeout_ms = int(getattr(settings, "db_statement_timeout_ms", 0) or 0)
    if timeout_ms > 0 and database_url.startswith("postgresql"):
        connect_args["options"] = f"-c statement_timeout={timeout_ms}"
    return connect_args


def _engine_kwargs(settings, database_url: str) -> dict:
    """连接池统一走 settings（DB_POOL_SIZE / DB_MAX_OVERFLOW）；远程 PG 仅加长 connect_timeout。"""
    return {
        "poolclass": QueuePool,
        "pool_size": settings.db_pool_size,
        "max_overflow": settings.db_max_overflow,
        "pool_timeout": settings.db_pool_timeout,
        "pool_recycle": settings.db_pool_recycle,
        "pool_pre_ping": True,
        "connect_args": _postgres_connect_args(settings, database_url),
        "echo": settings.debug_sql,
    }


def _attach_slow_query_logging(engine: Engine) -> None:
    threshold_ms = int(get_settings().db_slow_query_log_ms or 0)
    if threshold_ms <= 0:
        return

    @event.listens_for(engine, "before_cursor_execute")
    def _before_cursor_execute(
        conn, cursor, statement, parameters, context, executemany
    ):
        context._query_start_time = time.monotonic()  # type: ignore[attr-defined]

    @event.listens_for(engine, "after_cursor_execute")
    def _after_cursor_execute(
        conn, cursor, statement, parameters, context, executemany
    ):
        started = getattr(context, "_query_start_time", None)
        if started is None:
            return
        elapsed_ms = (time.monotonic() - started) * 1000
        if elapsed_ms >= threshold_ms:
            preview = " ".join(str(statement).split())
            if len(preview) > 500:
                preview = preview[:500] + "…"
            _logger.warning("慢查询 %.0fms: %s", elapsed_ms, preview)


def _engine():
    settings = get_settings()
    eng = create_engine(settings.database_url, **_engine_kwargs(settings, settings.database_url))
    _attach_slow_query_logging(eng)
    return eng


engine = _engine()
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)

_read_engine: Engine | None = None
ReadSessionLocal: sessionmaker | None = None

_health_engine: Engine | None = None


def _read_engine_instance() -> Engine | None:
    """只读副本引擎；未配置 DATABASE_READ_URL 时返回 None（回退主库）。"""
    global _read_engine, ReadSessionLocal
    settings = get_settings()
    read_url = (getattr(settings, "database_read_url", None) or "").strip()
    if not read_url:
        return None
    if _read_engine is None:
        _read_engine = create_engine(read_url, **_engine_kwargs(settings, read_url))
        _attach_slow_query_logging(_read_engine)
        ReadSessionLocal = sessionmaker(
            bind=_read_engine, autocommit=False, autoflush=False
        )
    return _read_engine


def read_session_factory() -> sessionmaker:
    """读路径 Session 工厂：有只读副本则用副本，否则用主库。"""
    _read_engine_instance()
    if ReadSessionLocal is not None:
        return ReadSessionLocal
    return SessionLocal


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


def _db_session(factory: sessionmaker) -> Generator[Session, None, None]:
    from app.core.db_circuit import guard_db_circuit, record_db_outcome

    guard_db_circuit()
    db = factory()
    try:
        yield db
        record_db_outcome(None)
    except Exception as exc:
        record_db_outcome(exc)
        raise
    finally:
        db.close()


def get_db() -> Generator[Session, None, None]:
    yield from _db_session(SessionLocal)


def get_read_db() -> Generator[Session, None, None]:
    """只读 API 优先走 DATABASE_READ_URL（未配置则与 get_db 相同）。"""
    yield from _db_session(read_session_factory())


@contextmanager
def session_scope():
    """后台任务短生命周期会话：自动 commit/rollback 并归还连接。"""
    from app.core.db_circuit import guard_db_circuit, record_db_outcome

    guard_db_circuit()
    db = SessionLocal()
    try:
        yield db
        db.commit()
        record_db_outcome(None)
    except Exception as exc:
        db.rollback()
        record_db_outcome(exc)
        raise
    finally:
        db.close()
