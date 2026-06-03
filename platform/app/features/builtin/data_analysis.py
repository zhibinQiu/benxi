"""数据分析 — 左侧对话 + 右侧 Notebook 代码执行。"""

from __future__ import annotations

from app.api import data_analysis as data_analysis_api
from app.features.base import FeaturePlugin
from app.features.registry import register

register(
    FeaturePlugin(
        id="data_analysis",
        title="数据分析",
        description="上传 Excel / CSV，多轮对话生成 pandas 统计与可视化代码，Notebook 式逐步运行",
        icon="stats-chart",
        route="/system/data-analysis",
        router=data_analysis_api.router,
        permission_code="feature.data_analysis",
        permission_name="数据分析",
        enabled=True,
        category="tools",
        sort_order=46,
        grant_to_roles=("sys_admin", "member"),
    )
)
