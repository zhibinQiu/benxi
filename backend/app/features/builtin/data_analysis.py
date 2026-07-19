"""表格分析 — 左侧对话 + 右侧 Notebook 代码执行。"""

from __future__ import annotations

from app.api import data_analysis as data_analysis_api
from app.features.base import FeaturePlugin
from app.features.registry import register

register(
    FeaturePlugin(
        id="data_analysis",
        title="表格分析",
        description="上传 Excel / CSV，用自然语言对表格进行清洗、转换、统计、可视化等处理，Notebook 式逐步运行",
        icon="stats-chart",
        route="/system/data-analysis",
        router=data_analysis_api.router,
        permission_code="feature.data_analysis",
        permission_name="表格分析",
        enabled=True,
        category="tools",
        sort_order=46,
        grant_to_roles=("sys_admin", "member"),
    )
)
