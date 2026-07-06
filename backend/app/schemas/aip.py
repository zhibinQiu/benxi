"""AIP（GB/Z 185）对外发现与调用 — schemas。"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from app.core.aip.types import AipAgentDescription, AipInteractEnvelope, AipMessage


class AipDiscoverItemOut(BaseModel):
    aid: str
    name: str
    description: str
    capability_ids: list[str] = Field(default_factory=list)
    service_endpoint: str | None = None


class AipDiscoverOut(BaseModel):
    total: int
    items: list[AipDiscoverItemOut]


class AipAgentDetailOut(AipAgentDescription):
    enabled: bool = True


class AipInteractIn(AipInteractEnvelope):
    pass


class AipInteractOut(BaseModel):
    message: AipMessage
    reply_text: str = ""
    satisfied: bool = False
    meta: dict[str, Any] = Field(default_factory=dict)
