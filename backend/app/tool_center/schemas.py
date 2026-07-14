"""ToolCenter 标准结构体 — 注册描述、Skill 请求、Tool 响应。"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class RateLimitSpec(BaseModel):
    qps: int = Field(default=20, ge=1, le=1000)


class ToolDescriptor(BaseModel):
    """全局 ToolCenter 注册项 — Skill 读取能力元数据。"""

    model_config = ConfigDict(extra="forbid")

    tool_id: str = Field(min_length=1, max_length=120)
    tool_type: str = Field(min_length=1, max_length=64)
    description: str = Field(default="", max_length=2000)
    doc_text: str = Field(default="", max_length=8000)
    input_schema: dict[str, Any] = Field(default_factory=dict)
    output_schema: dict[str, Any] = Field(default_factory=dict)
    rate_limit: RateLimitSpec = Field(default_factory=RateLimitSpec)
    tool_version: str = Field(default="v1.0")


class SkillMeta(BaseModel):
    skill_id: str = Field(min_length=1, max_length=120)
    belong_agent: str = Field(default="", max_length=64)


class ToolCallRequest(BaseModel):
    """Skill → ToolCenter 标准调用（Tool 不感知 LLM / Prompt / 记忆）。"""

    model_config = ConfigDict(extra="forbid")

    call_id: str = Field(min_length=1, max_length=128)
    tool_id: str = Field(min_length=1, max_length=120)
    params: dict[str, Any] = Field(default_factory=dict)
    trace_id: str = Field(default="", max_length=128)
    skill_meta: SkillMeta


class ToolResponse(BaseModel):
    """Tool → Skill 统一响应。"""

    model_config = ConfigDict(extra="forbid")

    success: bool
    code: int = 0
    msg: str = ""
    data: dict[str, Any] | None = None
    detail: str | None = None
    meta: dict[str, Any] = Field(default_factory=dict)

    @property
    def retryable(self) -> bool:
        if "retryable" in self.meta:
            return bool(self.meta["retryable"])
        from app.tool_center.errors import is_retryable

        return is_retryable(self.code)

    def model_dump_public(self) -> dict[str, Any]:
        """Skill 层缓存/日志用；禁止透传给 Agent LLM。"""
        return self.model_dump(exclude={"detail"})
