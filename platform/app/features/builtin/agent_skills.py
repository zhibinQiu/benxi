"""Agent Skills — 内置能力与上传技能包管理。"""

from __future__ import annotations

from app.features.base import FeaturePlugin
from app.features.registry import register

register(
    FeaturePlugin(
        id="agent_skills",
        title="多智能体",
        description="管理系统智能体、技能、工具与记忆，供本析智能按需调度",
        icon="extension-puzzle",
        route="/system/agent-skills",
        permission_code="feature.agent_skills",
        permission_name="多智能体",
        enabled=True,
        category="tools",
        sort_order=5,
        grant_to_roles=("sys_admin", "member"),
    )
)
