"""嵌入 UI 探活与 /rag/meta 载荷（从 API 层下沉）。"""

from __future__ import annotations

import time

import httpx

from app.config import get_settings
from app.integrations.knowflow_client import get_knowflow_client, knowflow_stack_reachable
from app.services.ragflow_identity_service import resolve_ui_embed_base
from app.services.ragflow_naming import dataset_display_label_personal
from app.core.user_messages import (
    KNOWLEDGE_NOT_ENABLED,
    KNOWLEDGE_SERVICE_UNAVAILABLE,
    KNOWLEDGE_WEB_UNAVAILABLE,
)
from app.services.ragflow_scope_service import (
    dept_suffix_labels_for_theme,
    knowflow_kb_labels_for_user,
)

_META_PROBE_TTL_SEC = 12.0
_meta_probe_cache: dict[str, tuple[float, bool]] = {}
_stack_reachable_cache: tuple[float, bool] | None = None


def _ragflow_ui_available(url: str) -> bool:
    try:
        with httpx.Client(timeout=2.0, follow_redirects=True) as client:
            r = client.get(url.rstrip("/") + "/")
            if r.status_code >= 500:
                return False
            ct = (r.headers.get("content-type") or "").lower()
            if "html" in ct or r.text.lstrip().startswith("<"):
                return True
            return False
    except Exception:
        return False


def _ragflow_ui_available_cached(url: str) -> bool:
    key = url.rstrip("/")
    now = time.monotonic()
    hit = _meta_probe_cache.get(key)
    if hit and now - hit[0] < _META_PROBE_TTL_SEC:
        return hit[1]
    ok = _ragflow_ui_available(key)
    _meta_probe_cache[key] = (now, ok)
    return ok


def _knowflow_stack_reachable_cached() -> bool:
    global _stack_reachable_cache
    now = time.monotonic()
    if _stack_reachable_cache and now - _stack_reachable_cache[0] < _META_PROBE_TTL_SEC:
        return _stack_reachable_cache[1]
    ok = knowflow_stack_reachable()
    _stack_reachable_cache = (now, ok)
    return ok


def build_rag_meta_payload(db, user) -> dict:
    """供知识问答 / 切片库嵌入页使用的 meta 字典。"""
    settings = get_settings()
    kf = get_knowflow_client(platform_user_id=user.id)
    browser_base = settings.knowflow_ui_browser_base
    embed_base = resolve_ui_embed_base()
    upstream = settings.knowflow_ui_upstream
    stack_on = settings.knowflow_enabled and _knowflow_stack_reachable_cached()
    ui_available = _ragflow_ui_available_cached(upstream)
    if not ui_available and stack_on:
        ui_available = True
    mode = (settings.knowflow_ui_embed_mode or "iframe").strip().lower()
    if mode not in ("iframe", "redirect"):
        mode = "iframe"
    ui_hint = ""
    if settings.knowflow_enabled and not stack_on:
        ui_hint = KNOWLEDGE_SERVICE_UNAVAILABLE
    elif settings.knowflow_enabled and not _ragflow_ui_available_cached(upstream):
        ui_hint = KNOWLEDGE_WEB_UNAVAILABLE
    elif not settings.knowflow_enabled:
        ui_hint = KNOWLEDGE_NOT_ENABLED
    return {
        "knowflow_enabled": stack_on,
        "knowflow_ready": kf.enabled(),
        "health": kf.health(),
        "integration_phase": 4,
        "ui_embed_url": f"{embed_base}/",
        "ui_direct_url": browser_base,
        "ui_embed_mode": mode,
        "ui_available": ui_available,
        "ui_hint": ui_hint,
        "dataset_name": dataset_display_label_personal(db, user.id),
        "knowflow_kb_labels": knowflow_kb_labels_for_user(db, user),
        "dept_suffix_labels": dept_suffix_labels_for_theme(db, user),
        "features": [
            "knowflow_native_ui",
            "citation_trace",
            "pdf_page_bbox",
            "knowflow_api",
            "per_user_dataset",
            "sso_auto_login",
            "doc_sync",
            "ui_whitelabel",
        ],
    }
