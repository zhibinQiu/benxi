"""系统模型配置（只读，实际以环境变量为准）。"""

from __future__ import annotations

from pydantic import BaseModel, Field


class ModelEndpointOut(BaseModel):
    base_url: str = ""
    api_key_configured: bool = False
    api_key_masked: str = ""
    model_name: str | None = None


class ModelSettingsOut(BaseModel):
    effective_source: str = Field(
        default="environment",
        description="配置生效来源",
    )
    editable: bool = False
    notice: str = ""
    llm: ModelEndpointOut
    embedding: ModelEndpointOut
    rerank: ModelEndpointOut
