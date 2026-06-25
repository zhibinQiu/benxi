from __future__ import annotations

import asyncio
import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app import __version__
from app.api import (
    agent_profiles,
    agent_skills,
    assistant,
    auth,
    chat_history,
    departments,
    documents,
    issue_reports,
    jobs,
    knowledge_embed,
    model_settings,
    menu_settings,
    monitor,
    notifications,
    roles,
    system,
    todos,
    users,
)
from app.api import embed_proxy as embed_proxy_api
from app.config import get_settings
from app.core.exceptions import AppError, service_unavailable
from app.database import SessionLocal, engine
from app.db_bootstrap import bootstrap_database
from app.features.registry import ensure_plugins_loaded, mount_routers
from app.models import (  # noqa: F401 — register ORM models
    agent_skill,
    agent_skill_binding,
    agent_profile_binding,
    audit,
    carbon_market,
    compare,
    document,
    document_version_compare,
    document_workflow,
    feed_subscription,
    job,
    kg,
    meeting_record,
    notification,
    org,
    platform_chat,
    platform_model_settings,
    rag,
    ragflow_document_link,
    ragflow_document_mirror_link,
    ragflow_link,
    ragflow_scope_dataset,
    scheduled_notification,
    todo,
    wechat_mp,
)
from app.schemas.common import ApiResponse
from app.services.carbon_market_sync_scheduler import start_cea_history_scheduler
from app.services.knowflow_queue_watchdog_service import start_knowflow_queue_watchdog
from app.services.job_watchdog_service import start_background_job_watchdog

_logger = logging.getLogger(__name__)


def _bootstrap_database_with_retry() -> None:
    import time

    from sqlalchemy.exc import OperationalError

    settings = get_settings()
    attempts = 5 if settings.remote_deps else 2
    delay = 4.0 if settings.remote_deps else 2.0
    last_exc: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            bootstrap_database(engine)
            return
        except OperationalError as exc:
            last_exc = exc
            _logger.warning(
                "数据库启动第 %s/%s 次失败（remote=%s）: %s",
                attempt,
                attempts,
                settings.remote_deps,
                exc,
            )
            if attempt < attempts:
                time.sleep(delay)
    assert last_exc is not None
    raise last_exc


def _check_database() -> bool:
    from app.database import check_database_health

    return check_database_health()


_db_health_cache: tuple[float, bool] | None = None
_DB_HEALTH_CACHE_TTL_SEC = 5.0


def _check_database_cached() -> bool:
    global _db_health_cache
    now = time.monotonic()
    if _db_health_cache is not None:
        cached_at, ok = _db_health_cache
        if now - cached_at < _DB_HEALTH_CACHE_TTL_SEC:
            return ok
    ok = _check_database()
    _db_health_cache = (now, ok)
    return ok


@asynccontextmanager
async def lifespan(_app: FastAPI):
    _bootstrap_database_with_retry()
    from app.services.data_analysis_profile import warn_if_data_analysis_deps_missing

    warn_if_data_analysis_deps_missing()
    # 启动时探测 Redis，避免首个用户请求在 cache 层等待连接超时
    from app.core.redis_client import get_redis_client

    await asyncio.to_thread(get_redis_client)

    def _recover_index_jobs_background() -> None:
        try:
            from app.services.job_watchdog_service import cancel_stale_background_jobs
            from app.services.knowledge_sync_job_service import (
                recover_interrupted_document_index_jobs,
            )

            cancel_stale_background_jobs()
            recover_interrupted_document_index_jobs()
        except Exception:
            _logger.exception("后台恢复文档索引任务失败")

    from app.core.background_executor import submit_background

    submit_background("recover-index-jobs", _recover_index_jobs_background)

    def _recover_scheduled_notifications_background() -> None:
        try:
            from app.services.notification_service import (
                recover_pending_scheduled_notifications,
            )

            recover_pending_scheduled_notifications()
        except Exception:
            _logger.exception("后台恢复定时通知失败")

    submit_background(
        "recover-scheduled-notifications", _recover_scheduled_notifications_background
    )
    sync_task = start_cea_history_scheduler()
    watchdog_task = start_knowflow_queue_watchdog()
    job_watchdog_task = start_background_job_watchdog()
    try:
        yield
    finally:
        job_watchdog_task.cancel()
        try:
            await job_watchdog_task
        except asyncio.CancelledError:
            pass
        watchdog_task.cancel()
        try:
            await watchdog_task
        except asyncio.CancelledError:
            pass
        sync_task.cancel()
        try:
            await sync_task
        except asyncio.CancelledError:
            pass
        from app.core.background_executor import shutdown_background_executor

        shutdown_background_executor(wait=False)


def create_app() -> FastAPI:
    ensure_plugins_loaded()
    from app.skills.registry import ensure_skills_loaded

    ensure_skills_loaded()
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        version=__version__,
        lifespan=lifespan,
    )
    origins = (
        ["*"]
        if settings.cors_origins.strip() == "*"
        else [o.strip() for o in settings.cors_origins.split(",") if o.strip()]
    )
    allow_all_origins = settings.cors_origins.strip() == "*"
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=not allow_all_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def clear_user_request_cache(request: Request, call_next):
        from app.core.request_user_cache import clear_request_user_cache

        clear_request_user_cache()
        return await call_next(request)

    @app.exception_handler(AppError)
    async def handle_app_error(_request: Request, exc: AppError) -> JSONResponse:
        detail = exc.detail if isinstance(exc.detail, dict) else {}
        body = {
            "code": detail.get("code", exc.status_code),
            "message": detail.get("message", "请求失败"),
        }
        for key in ("reason",):
            if key in detail:
                body[key] = detail[key]
        return JSONResponse(status_code=exc.status_code, content=body)

    try:
        from sqlalchemy.exc import TimeoutError as SATimeoutError

        from app.core.db_circuit import DbCircuitOpenError, is_db_failure, mark_db_failure

        @app.exception_handler(DbCircuitOpenError)
        async def handle_db_circuit_open(
            _request: Request, exc: DbCircuitOpenError
        ) -> JSONResponse:
            logging.getLogger(__name__).warning("数据库熔断已打开: %s", exc)
            err = service_unavailable(str(exc) or "系统繁忙，请稍后重试")
            detail = err.detail if isinstance(err.detail, dict) else {}
            return JSONResponse(
                status_code=503,
                content={
                    "code": detail.get("code", 503),
                    "message": detail.get("message", "系统繁忙，请稍后重试"),
                },
            )

        @app.exception_handler(SATimeoutError)
        async def handle_pool_timeout(_request: Request, exc: Exception) -> JSONResponse:
            logging.getLogger(__name__).warning("数据库连接池已耗尽，请求排队超时")
            mark_db_failure()
            err = service_unavailable("系统繁忙，请稍后重试")
            detail = err.detail if isinstance(err.detail, dict) else {}
            return JSONResponse(
                status_code=503,
                content={
                    "code": detail.get("code", 503),
                    "message": detail.get("message", "系统繁忙，请稍后重试"),
                },
            )
    except ImportError:
        pass

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(
        _request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        parts: list[str] = []
        for err in exc.errors():
            loc = ".".join(str(x) for x in err.get("loc", []) if x != "body")
            msg = err.get("msg", "")
            parts.append(f"{loc or '参数'}：{msg}" if loc else msg)
        return JSONResponse(
            status_code=422,
            content={
                "code": 422,
                "message": "；".join(parts) or "请求参数无效",
            },
        )

    @app.exception_handler(Exception)
    async def handle_unexpected_error(
        _request: Request, exc: Exception
    ) -> JSONResponse:
        msg = str(exc)
        if "QueuePool limit" in msg or "connection timed out" in msg.lower():
            logging.getLogger(__name__).warning("数据库连接异常: %s", msg)
            try:
                from app.core.db_circuit import is_db_failure, mark_db_failure

                if is_db_failure(exc):
                    mark_db_failure()
            except ImportError:
                pass
            err = service_unavailable("系统繁忙，请稍后重试")
            detail = err.detail if isinstance(err.detail, dict) else {}
            return JSONResponse(
                status_code=503,
                content={
                    "code": detail.get("code", 503),
                    "message": detail.get("message", "系统繁忙，请稍后重试"),
                },
            )
        logging.getLogger(__name__).exception("未处理异常: %s", exc)
        return JSONResponse(
            status_code=500,
            content={"code": 500, "message": "服务器内部错误，请稍后重试"},
        )

    prefix = settings.api_prefix

    @app.get("/health")
    def health():
        """轻量存活探针，不每次打 DB。"""
        return {"ok": True, "version": __version__}

    @app.get("/health/ready")
    def health_ready():
        db_ok = _check_database_cached()
        body = {"ok": db_ok, "db": db_ok, "version": __version__}
        if not db_ok:
            return JSONResponse(status_code=503, content=body)
        return body

    @app.get("/")
    def root() -> ApiResponse[dict]:
        return ApiResponse(data={"name": settings.app_name, "version": __version__})

    app.include_router(assistant.router, prefix=prefix)
    app.include_router(chat_history.router, prefix=prefix)
    app.include_router(auth.router, prefix=prefix)
    app.include_router(departments.router, prefix=prefix)
    app.include_router(users.router, prefix=prefix)
    app.include_router(roles.router, prefix=prefix)
    app.include_router(documents.router, prefix=prefix)
    app.include_router(knowledge_embed.router, prefix=prefix)
    app.include_router(system.router, prefix=prefix)
    app.include_router(embed_proxy_api.public_router, prefix=prefix)
    app.include_router(embed_proxy_api.router, prefix=prefix)
    mount_routers(app, prefix)
    app.include_router(jobs.router, prefix=prefix)
    app.include_router(notifications.router, prefix=prefix)
    app.include_router(todos.router, prefix=prefix)
    app.include_router(issue_reports.router, prefix=prefix)
    app.include_router(monitor.router, prefix=prefix)
    app.include_router(model_settings.router, prefix=prefix)
    app.include_router(menu_settings.router, prefix=prefix)
    app.include_router(agent_skills.router, prefix=prefix)
    app.include_router(agent_profiles.router, prefix=prefix)
    from app.api import browser_rpa

    app.include_router(browser_rpa.router, prefix=prefix)

    return app


app = create_app()


def run() -> None:
    import uvicorn

    settings = get_settings()
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.debug,
    )


if __name__ == "__main__":
    run()
