import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class DocumentDenialCreate(BaseModel):
    user_id: uuid.UUID
    reason: str = ""


class DocumentDenialOut(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    user_name: str | None = None
    reason: str
    created_by: uuid.UUID
    created_at: datetime

    model_config = {"from_attributes": True}


class PublishRequestCreate(BaseModel):
    note: str = ""
    target_dept_id: uuid.UUID | None = None


class PublishReviewBody(BaseModel):
    review_note: str = ""


class PublishRequestOut(BaseModel):
    id: uuid.UUID
    document_id: uuid.UUID
    requested_by: uuid.UUID
    from_scope: str
    to_scope: str
    target_dept_id: uuid.UUID | None
    status: str
    note: str
    review_note: str
    reviewed_by: uuid.UUID | None
    created_at: datetime
    reviewed_at: datetime | None
    document_title: str | None = None

    model_config = {"from_attributes": True}
