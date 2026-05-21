import uuid
from datetime import datetime

from pydantic import BaseModel


class JobOut(BaseModel):
    id: uuid.UUID
    type: str
    status: str
    document_id: uuid.UUID | None
    progress: int
    error_message: str | None
    payload: dict | None = None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None

    model_config = {"from_attributes": True}


class NotificationOut(BaseModel):
    id: uuid.UUID
    title: str
    body: str
    link: str | None
    read_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


class AuditLogOut(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID | None
    action: str
    resource_type: str
    resource_id: str | None
    ip_address: str | None
    detail: dict | None
    created_at: datetime

    model_config = {"from_attributes": True}
