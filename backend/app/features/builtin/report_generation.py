"""报告生成 — 联网 + 本地知识库 + 多轮修订。"""

from __future__ import annotations

from app.api import report_generation as report_generation_api
from app.features.base import FeaturePlugin
from app.features.registry import register

register(
    FeaturePlugin(
        id="report_generation",
        title="报告生成",
        description="综合 Agent 撰写长报告：多路大量召回本地片段并扩写整合，区别于知识检索的归纳式短答",
        icon="create",
        route="/knowledge/report",
        router=report_generation_api.router,
        permission_code="feature.report_generation",
        permission_name="报告生成",
        enabled=True,
        category="document",
        sort_order=18,
        grant_to_roles=("sys_admin", "member"),
    )
)
