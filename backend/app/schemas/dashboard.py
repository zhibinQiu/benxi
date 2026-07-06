from __future__ import annotations

from pydantic import BaseModel, Field


class PlatformDashboardStatsOut(BaseModel):
    documents_total: int = Field(description="文档总数（不含多版本重复计数）")
    documents_indexed: int = Field(description="已成功完成索引的文档总数（不含解析失败/未完成）")
    features_total: int = Field(description="功能总数")
    features_pending: int = Field(description="待开发/未启用功能数")
    users_registered: int = Field(description="已注册用户数")
    users_online: int = Field(description="当前在线用户数")
    users_online_names: list[str] = Field(
        default_factory=list,
        description="当前在线用户展示名",
    )
    collected_at: float = Field(description="统计采集时间（Unix 秒）")
