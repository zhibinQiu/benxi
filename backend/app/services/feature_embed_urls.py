"""各功能 iframe 同源代理地址（API 反向代理 / Vite / Nginx）。"""

from __future__ import annotations

from collections.abc import Callable

from app.config import get_settings
from app.services.embed_proxy import resolve_proxy_embed_url

_API_DS_PREFIX = "/api/v1/embed-proxy/design-system"


def _design_system_embed(path: str) -> str:
    """设计系统内嵌地址。

    - path（推荐）：/ai/... 由前端 Vite 或 Nginx 将 /ai 反代到上游，静态资源路径一致。
    - api：/api/v1/embed-proxy/design-system/... 仅适合无绝对 /ai 资源路径的上游。
    - vite：/design-system-ui/... 需上游资源不以 /ai 为根，否则仍会白屏。
    """
    s = get_settings()
    rel = (path or "/").strip()
    if not rel.startswith("/"):
        rel = f"/{rel}"
    mode = (s.embed_proxy_mode or "path").strip().lower()
    if mode == "path":
        return rel
    if mode == "api":
        if rel == "/":
            return _API_DS_PREFIX
        return f"{_API_DS_PREFIX}/{rel.lstrip('/')}"
    return resolve_proxy_embed_url(
        proxy_prefix=s.design_system_proxy_prefix,
        upstream_url=s.design_system_upstream_url,
        path=path,
    )


def _smart_forecast_embed() -> str:
    """智能预测服务无需登录，默认直连 8501（已允许跨域）。"""
    s = get_settings()
    mode = (s.smart_forecast_embed_mode or "direct").strip().lower()
    if mode == "direct":
        return s.smart_forecast_upstream_url.rstrip("/") + "/"
    if mode == "vite":
        return resolve_proxy_embed_url(
            proxy_prefix=s.smart_forecast_proxy_prefix,
            upstream_url=s.smart_forecast_upstream_url,
            path="/",
        )
    return s.smart_forecast_upstream_url.rstrip("/") + "/"


def resolve_smart_data_query_embed_url() -> str:
    return _design_system_embed(get_settings().smart_data_query_path)


def resolve_carbon_qa_embed_url() -> str:
    return _design_system_embed(get_settings().carbon_qa_path)


def resolve_smart_forecast_embed_url() -> str:
    return _smart_forecast_embed()


FEATURE_EMBED_RESOLVERS: dict[str, Callable[[], str]] = {
    "smart_data_query": resolve_smart_data_query_embed_url,
    "carbon_qa": resolve_carbon_qa_embed_url,
    "smart_forecast": resolve_smart_forecast_embed_url,
}


def resolve_feature_embed_url(feature_id: str) -> str:
    fn = FEATURE_EMBED_RESOLVERS.get(feature_id)
    if fn:
        return fn()
    return ""
