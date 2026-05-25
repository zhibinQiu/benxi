from __future__ import annotations

from app.features.base import FeaturePlugin
from app.features.registry import register

register(
    FeaturePlugin(
        id="carbon_qa",
        title="双碳问答",
        description="双碳政策、标准与业务知识智能问答",
        icon="chatbubbles",
        route="/system/carbon-qa",
        permission_code="feature.carbon_qa",
        permission_name="双碳问答",
        enabled=True,
        category="carbon",
        sort_order=46,
        grant_to_roles=("sys_admin", "dept_admin", "member"),
    )
)
