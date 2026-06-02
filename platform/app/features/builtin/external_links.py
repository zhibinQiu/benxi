"""系统功能 — 外链类（含待集成占位）。"""

from __future__ import annotations

from app.features.base import FeaturePlugin
from app.features.registry import register

register(
    FeaturePlugin(
        id="ai_digital_robot",
        title="AI数字机器人",
        description="AI 数字人交互与播报服务",
        icon="hardware-chip",
        permission_code="feature.ai_digital_robot",
        permission_name="AI数字机器人",
        enabled=False,
        tag="待集成",
        category="external",
        sort_order=62,
        grant_to_roles=("sys_admin", "member"),
    )
)
