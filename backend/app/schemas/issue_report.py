import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class IssueReportCreate(BaseModel):
    description: str = Field(..., min_length=1, max_length=8000)


class IssueReportUpdate(BaseModel):
    status: str = Field(..., pattern="^(open|fixed)$")


class IssueReportOut(BaseModel):
    id: uuid.UUID
    description: str
    status: str
    reporter_id: uuid.UUID
    reporter_name: str
    fixed_at: datetime | None
    fixed_by_id: uuid.UUID | None
    fixed_by_name: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
