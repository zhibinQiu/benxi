from __future__ import annotations

from app.features.base import FeaturePlugin
from app.features.registry import register

todos_plugin = FeaturePlugin(
    id="todos",
    title="待办事项",
    description="个人待办清单，支持拖拽排序、设定截止时间与 AI 智能拆解。",
    icon="list",
    route="/system/todos",
    permission_code="feature.todos",
    permission_name="待办事项",
    enabled=True,
    category="tools",
    sort_order=50,
    grant_to_roles=("sys_admin", "member"),
)

register(todos_plugin)
