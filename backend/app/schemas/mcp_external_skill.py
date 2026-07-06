from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class McpToolOut(BaseModel):
    name: str
    description: str = ""
    inputSchema: dict = Field(default_factory=dict)


class McpExternalSkillOut(BaseModel):
    id: uuid.UUID | None = None
    name: str
    title: str = ""
    description: str = ""
    endpoint: str
    transport: str = "http"
    enabled: bool = True
    tools: list[McpToolOut] = Field(default_factory=list)
    use_when: str = ""
    dont_use_when: str = ""
    output: str = ""
    source: str = "db"
    created_at: datetime | None = None


class McpExternalSkillCreateIn(BaseModel):
    name: str = Field(..., min_length=2, max_length=64, pattern=r"^[a-z0-9][a-z0-9-]{1,62}$")
    title: str = Field(default="", max_length=256)
    description: str = ""
    endpoint: str = Field(..., min_length=8)
    transport: str = Field(default="http", pattern=r"^(http|sse)$")
    auth_token: str = ""
    enabled: bool = True
    use_when: str = ""
    dont_use_when: str = ""
    output: str = ""
    sync_tools: bool = True


class McpExternalSkillPatchIn(BaseModel):
    title: str | None = Field(default=None, max_length=256)
    description: str | None = None
    endpoint: str | None = Field(default=None, min_length=8)
    transport: str | None = Field(default=None, pattern=r"^(http|sse)$")
    auth_token: str | None = None
    enabled: bool | None = None
    use_when: str | None = None
    dont_use_when: str | None = None
    output: str | None = None


class McpServerInfoOut(BaseModel):
    enabled: bool
    endpoint: str
    protocol_version: str
    description: str = ""
