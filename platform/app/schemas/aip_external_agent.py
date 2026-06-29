from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class AipExternalAgentOut(BaseModel):
    id: uuid.UUID | None = None
    aid: str
    name: str
    description: str = ""
    service_endpoint: str
    enabled: bool = True
    source: str = "db"
    created_at: datetime | None = None


class AipExternalAgentCreateIn(BaseModel):
    aid: str = Field(..., min_length=3, max_length=256)
    name: str = Field(..., min_length=1, max_length=256)
    description: str = ""
    service_endpoint: str = Field(..., min_length=8)
    enabled: bool = True


class AipExternalAgentPatchIn(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=256)
    description: str | None = None
    service_endpoint: str | None = Field(default=None, min_length=8)
    enabled: bool | None = None
