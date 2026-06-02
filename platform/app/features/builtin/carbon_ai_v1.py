"""智碳 AI平台 v1 — 外链类。"""

from __future__ import annotations

from app.config import get_settings
from app.features.base import FeaturePlugin
from app.features.registry import register

_settings = get_settings()
_upstream = _settings.design_system_upstream_url.rstrip("/")
_path = _settings.carbon_ai_v1_path.strip() or "/ai"
_external_url = f"{_upstream}{_path}" if _path.startswith("/") else f"{_upstream}/{_path}"

register(
    FeaturePlugin(
        id="carbon_ai_v1",
        title="智碳 AI平台v1",
        description="智碳 AI 平台 v1（设计系统）",
        icon="sparkles",
        external_url=_external_url,
        permission_code="feature.carbon_ai_v1",
        permission_name="智碳 AI平台v1",
        enabled=True,
        tag="外链",
        category="external",
        sort_order=61,
        grant_to_roles=("sys_admin", "member", "member"),
    )
)
