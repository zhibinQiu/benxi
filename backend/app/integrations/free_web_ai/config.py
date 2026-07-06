"""Free Web AI 配置 — 从平台 Settings 读取。"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

from app.config import get_settings


def _parse_bool(raw: str | None, default: bool) -> bool:
    if raw is None or raw == "":
        return default
    return raw.strip().lower() in {"1", "true", "yes"}


def _parse_int(raw: str | None, default: int) -> int:
    if raw is None or raw == "":
        return default
    try:
        return max(0, int(float(raw)))
    except (TypeError, ValueError):
        return default


@dataclass(frozen=True)
class FreeWebAiConfig:
    """免费网页 AI 配置。"""

    enabled: bool = False
    headless: bool = False
    cdp_port: int = 0
    chrome_path: str = ""
    profile_dir: str = ""
    proxy_server: str = ""
    default_timeout_ms: int = 120000
    per_provider_timeout_ms: int = 180000
    default_provider: str = "qwen"
    chat_providers: tuple[str, ...] = ("doubao", "qwen", "deepseek")
    image_gen_providers: tuple[str, ...] = ("doubao", "qwen")
    image_ask_providers: tuple[str, ...] = ("doubao", "qwen", "deepseek")


def get_free_web_ai_config() -> FreeWebAiConfig:
    """从平台 Settings 读取配置。os.environ 可临时覆盖。"""
    s = get_settings()

    def _get(key: str) -> str | None:
        v = os.environ.get(key)
        if v is not None and v != "":
            return v
        # Settings 属性名 = env 变量名小写
        attr = key.lower()
        sv = getattr(s, attr, None)
        if sv is not None and sv != "":
            return str(sv)
        return None

    return FreeWebAiConfig(
        enabled=_parse_bool(_get("FREE_WEB_AI_ENABLED"), False),
        headless=_parse_bool(_get("FREE_WEB_AI_HEADLESS"), False),
        cdp_port=_parse_int(_get("FREE_WEB_AI_CDP_PORT"), 0),
        chrome_path=_get("FREE_WEB_AI_CHROME_PATH") or "",
        profile_dir=_get("FREE_WEB_AI_PROFILE_DIR") or os.path.expanduser("~/.free-web-ai-profile"),
        proxy_server=_get("FREE_WEB_AI_PROXY_SERVER") or "",
        default_timeout_ms=_parse_int(_get("FREE_WEB_AI_TIMEOUT_MS"), 120000),
        per_provider_timeout_ms=_parse_int(_get("FREE_WEB_AI_PROVIDER_TIMEOUT_MS"), 180000),
        default_provider=_get("FREE_WEB_AI_DEFAULT_PROVIDER") or "qwen",
    )
