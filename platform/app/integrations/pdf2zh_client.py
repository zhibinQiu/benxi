"""pdf2zh_next --api 翻译 Worker 的 HTTP 客户端工厂。

所有访问 ``PDF2ZH_API_URL`` 的代码应使用 ``pdf2zh_async_client`` / ``pdf2zh_sync_client``，
勿在各 service 重复 ``httpx.Client(base_url=pdf2zh_base_url(), ...)``。
"""

from __future__ import annotations

import httpx

from app.config import get_settings


def pdf2zh_base_url() -> str:
    return get_settings().pdf2zh_api_url.rstrip("/")


def pdf2zh_async_client(*, timeout_sec: float = 60.0) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        base_url=pdf2zh_base_url(),
        timeout=httpx.Timeout(timeout_sec),
    )


def pdf2zh_sync_client(*, timeout_sec: float = 60.0) -> httpx.Client:
    return httpx.Client(base_url=pdf2zh_base_url(), timeout=timeout_sec)
