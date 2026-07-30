"""碳资产报告 — Pydantic schemas。"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class CarbonReportSubmit(BaseModel):
    subject: str = Field(..., min_length=1, max_length=128, description="报告主题")
    report_type: str = Field(
        ...,
        pattern="^(market_brief|policy_digest|compliance_analysis|strategy)$",
        description=(
            "market_brief 碳交易简报 / policy_digest 政策摘要 / "
            "compliance_analysis 履约综合分析 / strategy 已下线"
        ),
    )
    industry: str = Field("", max_length=64, description="行业（策略类）")
    region: str = Field("", max_length=64, description="地区（策略类）")
    target_year: str = Field("", max_length=16, description="目标年份，如 2030")
    ai_context: str = Field(
        "",
        max_length=8000,
        description="补充说明；compliance_analysis 为 JSON（enterprise_id 等）",
    )


class CarbonReportOut(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID | None = None
    subject: str
    report_type: str
    industry: str
    region: str
    target_year: str
    ai_context: str
    status: str
    content: str | None
    error_message: str | None
    progress: int
    view_count: int = 0
    share_token: str | None = None
    system_job_id: uuid.UUID | None
    created_at: datetime
    completed_at: datetime | None
    # 管理员查看全员报告时填充
    owner_name: str | None = None

    model_config = {"from_attributes": True}
