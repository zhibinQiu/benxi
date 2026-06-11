"""SearXNG 联网搜索代理。"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING
from urllib.parse import urljoin

import httpx

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


class SearxngNotConfiguredError(RuntimeError):
    pass


class SearxngSearchError(RuntimeError):
    pass


def is_enabled(db: Session | None = None) -> bool:
    from app.services.model_settings_service import get_searxng_url

    return bool(get_searxng_url(db))


def search_web(
    query: str,
    *,
    page: int = 1,
    page_size: int = 20,
    db: Session | None = None,
) -> tuple[list[dict], bool]:
    """调用 SearXNG JSON API，返回 (items, has_more)。"""
    from app.services.model_settings_service import (
        get_searxng_timeout_seconds,
        get_searxng_url,
    )

    base = get_searxng_url(db).rstrip("/")
    if not base:
        raise SearxngNotConfiguredError("未配置 SearXNG 服务地址")

    q = (query or "").strip()
    if not q:
        return [], False

    url = urljoin(f"{base}/", "search")
    params = {
        "q": q,
        "format": "json",
        "pageno": max(1, page),
    }
    timeout = get_searxng_timeout_seconds(db)

    try:
        with httpx.Client(timeout=timeout, follow_redirects=True) as client:
            resp = client.get(
                url,
                params=params,
                headers={
                    "Accept": "application/json",
                    "User-Agent": "pdf-trans-platform/1.0",
                },
            )
            resp.raise_for_status()
            payload = resp.json()
    except httpx.HTTPError as exc:
        logger.warning("searxng search failed q=%r page=%s: %s", q, page, exc)
        raise SearxngSearchError("联网搜索服务暂不可用") from exc
    except ValueError as exc:
        logger.warning("searxng invalid json q=%r: %s", q, exc)
        raise SearxngSearchError("联网搜索返回格式异常") from exc

    raw_items = payload.get("results") or []
    items: list[dict] = []
    for row in raw_items:
        if not isinstance(row, dict):
            continue
        link = (row.get("url") or "").strip()
        title = (row.get("title") or link or "未命名").strip()
        if not link:
            continue
        items.append(
            {
                "title": title,
                "url": link,
                "snippet": (row.get("content") or "").strip(),
                "engine": (row.get("engine") or "").strip(),
            }
        )
        if len(items) >= page_size:
            break

    has_more = len(raw_items) > len(items) or len(raw_items) >= page_size
    return items, has_more
