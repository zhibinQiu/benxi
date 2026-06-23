"""浏览器 RPA 有效配置（环境变量 + 管理后台 DB 合并）。"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.config import Settings, get_settings


def _parse_bool(raw: str | None, default: bool) -> bool:
    if raw is None or raw == "":
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _parse_int(raw: str | None, default: int, *, minimum: int = 1) -> int:
    if raw is None or raw == "":
        return default
    try:
        return max(minimum, int(float(raw)))
    except (TypeError, ValueError):
        return default


@dataclass(frozen=True)
class BrowserRpaConfig:
    enabled: bool
    headless: bool
    session_ttl_seconds: int
    max_steps_per_session: int
    allowed_domains: str
    screenshot_max_kb: int
    auto_task_max_steps: int
    auto_task_enabled: bool


def get_browser_rpa_config(db: Session | None = None) -> BrowserRpaConfig:
    settings = get_settings()
    merged: dict[str, str] = {}
    if db is not None:
        from app.services.model_settings_service import get_effective_model_config

        merged = get_effective_model_config(db)

    def _get(key: str, fallback: str = "") -> str:
        val = merged.get(key)
        return str(val).strip() if val not in (None, "") else fallback

    return BrowserRpaConfig(
        enabled=_parse_bool(_get("agent_browser_enabled"), settings.agent_browser_enabled),
        headless=_parse_bool(_get("agent_browser_headless"), settings.agent_browser_headless),
        session_ttl_seconds=_parse_int(
            _get("agent_browser_session_ttl_seconds"),
            settings.agent_browser_session_ttl_seconds,
        ),
        max_steps_per_session=_parse_int(
            _get("agent_browser_max_steps_per_session"),
            settings.agent_browser_max_steps_per_session,
        ),
        allowed_domains=_get("agent_browser_allowed_domains", settings.agent_browser_allowed_domains or ""),
        screenshot_max_kb=_parse_int(
            _get("agent_browser_screenshot_max_kb"),
            settings.agent_browser_screenshot_max_kb,
            minimum=64,
        ),
        auto_task_max_steps=_parse_int(
            _get("agent_browser_auto_task_max_steps"),
            settings.agent_browser_auto_task_max_steps,
        ),
        auto_task_enabled=_parse_bool(
            _get("agent_browser_auto_task_enabled"),
            settings.agent_browser_auto_task_enabled,
        ),
    )


def docker_launch_args(settings: Settings | None = None) -> list[str]:
    """无头 Linux/Docker 容器内 Chromium 推荐参数（无需 X11/显示服务器）。"""
    args = [
        "--no-sandbox",
        "--disable-setuid-sandbox",
        "--disable-dev-shm-usage",
        "--disable-gpu",
    ]
    s = settings or get_settings()
    if s.agent_browser_headless:
        args.append("--headless=new")
    return args
