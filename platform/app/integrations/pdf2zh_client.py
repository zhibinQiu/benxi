"""HTTP client for pdf2zh_next --api (translation worker)."""

from __future__ import annotations

from app.config import get_settings


def pdf2zh_base_url() -> str:
    return get_settings().pdf2zh_api_url.rstrip("/")
