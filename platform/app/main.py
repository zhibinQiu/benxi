from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.api import audit as audit_api
from app.api import (
    auth,
    departments,
    documents,
    jobs,
    notifications,
    roles,
    system,
    users,
)
from app.features.registry import ensure_plugins_loaded, mount_routers
from app.bootstrap import bootstrap_db
from app.config import get_settings
from app.database import Base, SessionLocal, engine
from app.models import (  # noqa: F401 — register ORM models
    audit,
    document,
    job,
    notification,
    org,
)
from app.schemas.common import ApiResponse


@asynccontextmanager
async def lifespan(_app: FastAPI):
    Base.metadata.create_all(bind=engine)
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

    prefix = settings.api_prefix

    @app.get("/health")
    def health() -> dict:
        return {"ok": True, "version": __version__}

    @app.get("/")
    def root() -> ApiResponse[dict]:
        return ApiResponse(data={"name": settings.app_name, "version": __version__})

    app.include_router(auth.router, prefix=prefix)
    app.include_router(departments.router, prefix=prefix)
    app.include_router(users.router, prefix=prefix)
    app.include_router(roles.router, prefix=prefix)
    app.include_router(documents.router, prefix=prefix)
    app.include_router(system.router, prefix=prefix)
    mount_routers(app, prefix)
    app.include_router(jobs.router, prefix=prefix)
    app.include_router(notifications.router, prefix=prefix)
    app.include_router(audit_api.router, prefix=prefix)

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
