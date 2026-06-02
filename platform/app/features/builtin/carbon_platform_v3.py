"""智碳平台 V3 — 外链类。"""

from __future__ import annotations

from app.config import get_settings
from app.features.base import FeaturePlugin
from app.features.registry import register

_settings = get_settings()

register(
    FeaturePlugin(
        id="carbon_platform",
        title="智碳平台V3",
        description="智碳业务管理与数据平台（V3）",
        icon="leaf",
        external_url=_settings.carbon_platform_url,
        permission_code="feature.carbon_platform",
        permission_name="智碳平台V3",
        enabled=True,
        tag="外链",
        category="external",
        sort_order=60,
        grant_to_roles=("sys_admin", "member", "member"),
    )
)
