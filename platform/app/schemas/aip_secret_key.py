"""AIP Secret Key 管理 API schemas。"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class AipSecretKeyCreateIn(BaseModel):
    purpose: str = Field(..., min_length=1, max_length=500, description="密钥用途说明")


class AipSecretKeyOut(BaseModel):
    id: uuid.UUID
    key_prefix: str
    purpose: str
    created_by_id: uuid.UUID
    created_by_name: str = ""
    created_at: datetime


class AipSecretKeyCreatedOut(AipSecretKeyOut):
    secret_key: str = Field(description="完整密钥，仅创建时返回一次")
