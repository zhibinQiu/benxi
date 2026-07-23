"""本析智能 OpenAI 兼容 API 设置与协议模型。"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class AiHomeOpenAiSettingsOut(BaseModel):
    enabled: bool
    base_path: str
    model: str
    auth_hint: str


class AiHomeOpenAiSettingsUpdate(BaseModel):
    enabled: bool


class OpenAiChatMessage(BaseModel):
    role: str
    content: str | list[Any] | None = None
    name: str | None = None


class OpenAiChatCompletionRequest(BaseModel):
    model: str = "benxi"
    messages: list[OpenAiChatMessage] = Field(default_factory=list, min_length=1)
    stream: bool = False
    temperature: float | None = None
    max_tokens: int | None = None
