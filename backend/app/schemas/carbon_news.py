"""碳新闻：实时爬取条目与一问一答。"""

from __future__ import annotations

from pydantic import BaseModel, Field


class CarbonNewsItem(BaseModel):
    title: str = ""
    url: str = ""
    doc_type: str = ""
    published_at: str = ""
    source: str = ""
    body: str = ""


class CarbonNewsCrawlIn(BaseModel):
    keyword: str = Field(default="碳", description="搜索关键词")
    limit: int = Field(default=100, ge=1, le=100, description="一次爬取条数上限")


class CarbonNewsCrawlOut(BaseModel):
    keyword: str
    total_hits: int = 0
    count: int = 0
    items: list[CarbonNewsItem] = Field(default_factory=list)


class CarbonNewsAskIn(BaseModel):
    question: str = Field(..., min_length=1, description="用户问题")
    items: list[CarbonNewsItem] = Field(
        default_factory=list,
        description="当次爬取的政策/新闻条目（含正文）",
    )


class CarbonNewsSourceOut(BaseModel):
    index: int
    title: str = ""
    url: str = ""
    doc_type: str = ""
    published_at: str = ""
    source: str = ""


class CarbonNewsAskOut(BaseModel):
    answer_md: str
    sources: list[CarbonNewsSourceOut] = Field(default_factory=list)
