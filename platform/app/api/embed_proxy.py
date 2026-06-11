"""内嵌页反向代理（经平台 API 同源转发，配合前端 /api 代理或 Nginx）。"""

from __future__ import annotations

from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.responses import Response as PlainResponse

from app.api.deps import get_current_user
from app.config import get_settings
from app.models.org import User
from app.services.knowflow_embed_proxy import (
    branding_asset_path,
    inject_branding_html,
    rewrite_umi_runtime_public_path,
    should_inject_branding,
    should_rewrite_umi_public_path,
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
    # httpx 读取 body 时会自动解压；若仍转发 content-encoding 会导致浏览器 ERR_CONTENT_DECODING_FAILED
    skip = _HOP_BY_HOP | {
        "x-frame-options",
        "content-security-policy",
        "content-length",
        "content-encoding",
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
            prefix = settings.knowflow_ui_asset_prefix
            text = raw.decode(upstream.encoding or "utf-8", errors="replace")
            if text.lstrip().startswith("<"):
                text = inject_branding_html(text, proxy_prefix=prefix)
            return PlainResponse(
                content=text,
                status_code=upstream.status_code,
                headers=_filter_headers(upstream.headers),
                media_type=upstream.headers.get("content-type") or "text/html",
            )

        settings = get_settings()
        prefix = settings.knowflow_ui_asset_prefix if inject_knowflow_branding else ""
        if prefix and should_rewrite_umi_public_path(
            upstream.headers.get("content-type"), subpath
        ):
            raw = await upstream.aread()
            await upstream.aclose()
            await client.aclose()
            text = raw.decode(upstream.encoding or "utf-8", errors="replace")
            text = rewrite_umi_runtime_public_path(text, proxy_prefix=prefix)
            return PlainResponse(
                content=text,
                status_code=upstream.status_code,
                headers=_filter_headers(upstream.headers),
                media_type=upstream.headers.get("content-type") or "application/javascript",
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
        upstream_base=settings.knowflow_ui_upstream,
        subpath=path,
        request=request,
        inject_knowflow_branding=True,
    )


# iframe 浏览器直链 /knowledge、/search（umi 根路由）；静态资源仍走 /ragflow-ui/
knowflow_browser_router = APIRouter(tags=["knowflow-browser"])

_KNOWFLOW_SPA_ROUTE_PREFIXES = (
    "knowledge",
    "search",
    "chunk",
    "login",
    "login-next",
    "home",
    "datasets",
    "dataset",
    "flow",
    "chat",
    "agents",
    "agent-list",
    "agent-templates",
    "data-flows",
    "next-chats",
    "next-searches",
    "profile-setting",
    "user-setting",
    "files",
    "file",
)


async def _proxy_knowflow_spa_page(prefix: str, path: str, request: Request) -> Response:
    settings = get_settings()
    subpath = prefix if not path else f"{prefix}/{path}"
    return await _proxy_upstream(
        upstream_base=settings.knowflow_ui_upstream,
        subpath=subpath,
        request=request,
        inject_knowflow_branding=True,
    )


def _register_knowflow_spa_routes(router: APIRouter) -> None:
    for spa_prefix in _KNOWFLOW_SPA_ROUTE_PREFIXES:

        async def spa_root(
            request: Request,
            *,
            _prefix: str = spa_prefix,
        ) -> Response:
            return await _proxy_knowflow_spa_page(_prefix, "", request)

        async def spa_nested(
            path: str,
            request: Request,
            *,
            _prefix: str = spa_prefix,
        ) -> Response:
            return await _proxy_knowflow_spa_page(_prefix, path, request)

        router.add_api_route(
            f"/{spa_prefix}",
            spa_root,
            methods=["GET", "HEAD"],
        )
        router.add_api_route(
            f"/{spa_prefix}/{{path:path}}",
            spa_nested,
            methods=["GET", "HEAD"],
        )


def _is_knowflow_root_static_asset(asset: str) -> bool:
    """umi publicPath=/ 时的根路径静态资源（含 lazy chunk）。"""
    if asset in {"iconfont.js", "logo.svg", "favicon.svg"}:
        return True
    if asset.startswith("p__") and (asset.endswith(".js") or asset.endswith(".chunk.css")):
        return True
    if asset.endswith(".async.js") or asset.endswith(".chunk.css"):
        return True
    return False


_register_knowflow_spa_routes(knowflow_browser_router)


@knowflow_browser_router.get("/platform-branding.js")
def knowflow_branding_js_root() -> FileResponse:
    return FileResponse(
        branding_asset_path("platform-branding.js"),
        media_type="application/javascript",
    )


@knowflow_browser_router.get("/platform-branding.css")
def knowflow_branding_css_root() -> FileResponse:
    return FileResponse(
        branding_asset_path("platform-branding.css"),
        media_type="text/css",
    )


@knowflow_browser_router.api_route(
    "/umi.{path:path}",
    methods=["GET", "HEAD"],
)
async def proxy_knowflow_umi_root(path: str, request: Request) -> Response:
    settings = get_settings()
    return await _proxy_upstream(
        upstream_base=settings.knowflow_ui_upstream,
        subpath=f"umi.{path}",
        request=request,
        inject_knowflow_branding=False,
    )


@knowflow_browser_router.api_route(
    "/static/{path:path}",
    methods=["GET", "HEAD"],
)
async def proxy_knowflow_static_dir(path: str, request: Request) -> Response:
    settings = get_settings()
    return await _proxy_upstream(
        upstream_base=settings.knowflow_ui_upstream,
        subpath=f"static/{path}",
        request=request,
        inject_knowflow_branding=False,
    )


@knowflow_browser_router.api_route(
    "/{asset}",
    methods=["GET", "HEAD"],
)
async def proxy_knowflow_root_static(asset: str, request: Request) -> Response:
    """KnowFlow 根路径静态资源（iconfont、umi lazy chunk 等），与 umi publicPath=/ 一致。"""
    if not _is_knowflow_root_static_asset(asset):
        raise HTTPException(status_code=404, detail="Not Found")
    settings = get_settings()
    return await _proxy_upstream(
        upstream_base=settings.knowflow_ui_upstream,
        subpath=asset,
        request=request,
        inject_knowflow_branding=False,
    )


@knowflow_browser_router.get("/ragflow-ui/platform-branding.js")
def knowflow_branding_js_browser() -> FileResponse:
    return FileResponse(
        branding_asset_path("platform-branding.js"),
        media_type="application/javascript",
    )


@knowflow_browser_router.get("/ragflow-ui/platform-branding.css")
def knowflow_branding_css_browser() -> FileResponse:
    return FileResponse(
        branding_asset_path("platform-branding.css"),
        media_type="text/css",
    )


@knowflow_browser_router.api_route(
    "/ragflow-ui/{path:path}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"],
)
async def proxy_knowflow_ragflow_ui_browser(path: str, request: Request) -> Response:
    """开发 :18000 与生产 :40005/ragflow-ui 同路径，避免 iframe 落在 /api/.../knowflow/knowledge 导致 SPA 空白。"""
    settings = get_settings()
    return await _proxy_upstream(
        upstream_base=settings.knowflow_ui_upstream,
        subpath=path,
        request=request,
        inject_knowflow_branding=True,
    )


@knowflow_browser_router.api_route(
    "/v1/{path:path}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"],
)
async def proxy_knowflow_v1_browser(path: str, request: Request) -> Response:
    settings = get_settings()
    return await _proxy_upstream(
        upstream_base=settings.knowflow_ui_upstream,
        subpath=f"v1/{path}",
        request=request,
        inject_knowflow_branding=False,
    )


@knowflow_browser_router.api_route(
    "/api/knowflow/{path:path}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"],
)
async def proxy_knowflow_mgmt_browser(path: str, request: Request) -> Response:
    settings = get_settings()
    return await _proxy_upstream(
        upstream_base=settings.knowflow_ui_upstream,
        subpath=f"api/knowflow/{path}",
        request=request,
        inject_knowflow_branding=False,
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
