"""Agent Skills — 内置能力与上传技能包管理。"""

from __future__ import annotations

from app.features.base import FeaturePlugin
from app.features.registry import register

register(
    FeaturePlugin(
        id="agent_skills",
        title="Agent Skills",
        description="管理平台内置能力与上传 SKILL.md 技能包，统一供智能体发现与调用",
        icon="extension-puzzle",
        route="/system/agent-skills",
        permission_code="feature.agent_skills",
        permission_name="Agent Skills",
        enabled=True,
        category="tools",
        sort_order=5,
        grant_to_roles=("sys_admin",),
    )
)
