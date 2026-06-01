"""内嵌页反向代理（经平台 API 同源转发，配合前端 /api 代理或 Nginx）。"""

from __future__ import annotations

from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import FileResponse, Response as PlainResponse, StreamingResponse

from app.api.deps import get_current_user
from app.config import get_settings
from app.models.org import User
from app.services.knowflow_embed_proxy import (
    branding_asset_path,
    inject_branding_html,
    should_inject_branding,
)

router = APIRouter(
    prefix="/embed-proxy",
    tags=["embed-proxy"],
)

public_router = APIRouter(
    prefix="/embed-proxy",
    tags=["embed-proxy"],
)

_HOP_BY_HOP = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "transfer-encoding",
    "upgrade",
}


def _filter_headers(headers: httpx.Headers) -> dict[str, str]:
    skip = _HOP_BY_HOP | {
        "x-frame-options",
        "content-security-policy",
        "content-length",
    }
    return {k: v for k, v in headers.items() if k.lower() not in skip}


async def _proxy_upstream(
    *,
    upstream_base: str,
    subpath: str,
    request: Request,
    inject_knowflow_branding: bool = False,
) -> Response:
    base = upstream_base.rstrip("/")
    rel = subpath.lstrip("/")
    url = f"{base}/{rel}" if rel else base
    if request.url.query:
        url = f"{url}?{request.url.query}"

    headers = {
        k: v
        for k, v in request.headers.items()
        if k.lower() not in _HOP_BY_HOP and k.lower() != "host"
    }
    body = await request.body() if request.method not in ("GET", "HEAD") else None

    timeout = httpx.Timeout(300.0, connect=30.0)
    client = httpx.AsyncClient(timeout=timeout, follow_redirects=True)
    try:
        req = client.build_request(request.method, url, headers=headers, content=body)
        upstream = await client.send(req, stream=True)

        if inject_knowflow_branding and should_inject_branding(
            upstream.headers.get("content-type"), subpath
        ):
            raw = await upstream.aread()
            await upstream.aclose()
            await client.aclose()
            settings = get_settings()
            prefix = (settings.knowflow_ui_proxy_prefix or "/ragflow-ui").strip() or "/ragflow-ui"
            text = raw.decode(upstream.encoding or "utf-8", errors="replace")
            if text.lstrip().startswith("<"):
                text = inject_branding_html(text, proxy_prefix=prefix)
            return PlainResponse(
                content=text,
                status_code=upstream.status_code,
                headers=_filter_headers(upstream.headers),
                media_type=upstream.headers.get("content-type") or "text/html",
            )

        async def stream():
            try:
                async for chunk in upstream.aiter_bytes():
                    yield chunk
            finally:
                await upstream.aclose()
                await client.aclose()

        return StreamingResponse(
            stream(),
            status_code=upstream.status_code,
            headers=_filter_headers(upstream.headers),
            media_type=upstream.headers.get("content-type"),
        )
    except Exception:
        await client.aclose()
        raise


@public_router.get("/knowflow/platform-branding.js")
def knowflow_branding_js() -> FileResponse:
    return FileResponse(
        branding_asset_path("platform-branding.js"),
        media_type="application/javascript",
    )


@public_router.get("/knowflow/platform-branding.css")
def knowflow_branding_css() -> FileResponse:
    return FileResponse(
        branding_asset_path("platform-branding.css"),
        media_type="text/css",
    )


@public_router.api_route(
    "/knowflow/{path:path}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"],
)
async def proxy_knowflow(path: str, request: Request) -> Response:
    """KnowFlow 反代无需平台 JWT：umi 等静态资源不会带 query token，鉴权由 KnowFlow auth= 负责。"""
    settings = get_settings()
    return await _proxy_upstream(
        upstream_base=settings.knowflow_ui_url,
        subpath=path,
        request=request,
        inject_knowflow_branding=True,
    )


@router.api_route(
    "/design-system/{path:path}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"],
)
async def proxy_design_system(
    path: str,
    request: Request,
    _user: Annotated[User, Depends(get_current_user)],
) -> Response:
    settings = get_settings()
    return await _proxy_upstream(
        upstream_base=settings.design_system_upstream_url,
        subpath=path,
        request=request,
    )


@router.api_route(
    "/smart-forecast/{path:path}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"],
)
async def proxy_smart_forecast(
    path: str,
    request: Request,
    _user: Annotated[User, Depends(get_current_user)],
) -> Response:
    settings = get_settings()
    return await _proxy_upstream(
        upstream_base=settings.smart_forecast_upstream_url,
        subpath=path,
        request=request,
    )
