"""内嵌页同源代理 URL 解析（配合 Nginx / Vite 反向代理）。"""

from __future__ import annotations


def resolve_proxy_embed_url(
    *,
    proxy_prefix: str,
    upstream_url: str,
    path: str = "/",
) -> str:
    """优先返回前端同源代理路径，避免 iframe 跨域。"""
    prefix = (proxy_prefix or "").strip()
    rel = (path or "/").strip()
    if prefix:
        base = prefix.rstrip("/")
        if not rel or rel == "/":
            return base
        return f"{base}/{rel.lstrip('/')}"
    up = (upstream_url or "").strip().rstrip("/")
    if not up:
        return ""
    if not rel or rel == "/":
        return up
    return f"{up}/{rel.lstrip('/')}"
