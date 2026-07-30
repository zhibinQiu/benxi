"""自动化机器学习 — PyCaret 3.0 向导式训练。"""

from __future__ import annotations

from app.api import automl as automl_api
from app.features.base import FeaturePlugin
from app.features.registry import register

register(
    FeaturePlugin(
        id="auto_ml",
        title="自动化机器学习",
        description="上传 CSV，选择分类/回归/聚类/异常检测/时间序列任务与模型，基于 PyCaret 自动训练并输出结果",
        icon="analytics",
        route="/system/auto-ml",
        router=automl_api.router,
        permission_code="feature.auto_ml",
        permission_name="自动化机器学习",
        enabled=True,
        category="tools",
        sort_order=47,
        grant_to_roles=("sys_admin", "member"),
    )
)
