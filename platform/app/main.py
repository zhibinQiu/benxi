from __future__ import annotations

from contextlib import asynccontextmanager

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.exceptions import AppError

from app import __version__
from app.api import embed_proxy as embed_proxy_api
from app.api import (
    assistant,
    auth,
    departments,
    documents,
    jobs,
    model_settings,
    monitor,
    notifications,
    roles,
    system,
    todos,
    users,
)
from app.features.registry import ensure_plugins_loaded, mount_routers
from app.bootstrap import bootstrap_db
from app.schema_migrate import (
    ensure_document_schema,
    ensure_meeting_record_schema,
    ensure_permission_level_migration,
    ensure_ragflow_schema,
    ensure_todo_schema,
)
from app.config import get_settings
from app.database import Base, SessionLocal, engine
from app.models import (  # noqa: F401 — register ORM models
    audit,
    compare,
    document,
    job,
    notification,
    org,
    rag,
    ragflow_link,
    ragflow_document_link,
    ragflow_scope_dataset,
    document_workflow,
    meeting_record,
    todo,
)
from app.schemas.common import ApiResponse


@asynccontextmanager
async def lifespan(_app: FastAPI):
    Base.metadata.create_all(bind=engine)
    ensure_document_schema(engine)
    ensure_ragflow_schema(engine)
    ensure_meeting_record_schema(engine)
    ensure_todo_schema(engine)
    ensure_permission_level_migration(engine)
    db = SessionLocal()
    try:
        bootstrap_db(db)
    finally:
        db.close()
    yield


def create_app() -> FastAPI:
    ensure_plugins_loaded()
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
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(AppError)
    async def handle_app_error(_request: Request, exc: AppError) -> JSONResponse:
        detail = exc.detail if isinstance(exc.detail, dict) else {}
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "code": detail.get("code", exc.status_code),
                "message": detail.get("message", "请求失败"),
            },
        )

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
        logging.getLogger(__name__).exception("未处理异常: %s", exc)
        return JSONResponse(
            status_code=500,
            content={"code": 500, "message": "服务器内部错误，请稍后重试"},
        )

    prefix = settings.api_prefix

    @app.get("/health")
    def health() -> dict:
        return {"ok": True, "version": __version__}

    @app.get("/")
    def root() -> ApiResponse[dict]:
        return ApiResponse(data={"name": settings.app_name, "version": __version__})

    app.include_router(assistant.router, prefix=prefix)
    app.include_router(auth.router, prefix=prefix)
    app.include_router(departments.router, prefix=prefix)
    app.include_router(users.router, prefix=prefix)
    app.include_router(roles.router, prefix=prefix)
    app.include_router(documents.router, prefix=prefix)
    app.include_router(system.router, prefix=prefix)
    app.include_router(embed_proxy_api.router, prefix=prefix)
    mount_routers(app, prefix)
    app.include_router(jobs.router, prefix=prefix)
    app.include_router(notifications.router, prefix=prefix)
    app.include_router(todos.router, prefix=prefix)
    app.include_router(monitor.router, prefix=prefix)
    app.include_router(model_settings.router, prefix=prefix)

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
