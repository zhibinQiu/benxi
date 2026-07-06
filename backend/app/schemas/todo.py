import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class TodoCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=512)
    note: str = ""


class TodoUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=512)
    note: str | None = None
    status: str | None = None


class TodoReorder(BaseModel):
    status: str = Field(..., pattern="^(pending|done)$")
    ordered_ids: list[uuid.UUID]


class TodoOut(BaseModel):
    id: uuid.UUID
    title: str
    note: str
    status: str
    sort_order: int
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class TodoLlmRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=8000)
    mode: str = Field(default="parse", pattern="^(parse|adjust)$")


class TodoLlmItem(BaseModel):
    title: str
    note: str = ""


class TodoLlmResponse(BaseModel):
    mode: str
    items: list[TodoLlmItem]
    message: str = ""


class TodoBatchCreate(BaseModel):
    items: list[TodoCreate] = Field(..., min_length=1)
