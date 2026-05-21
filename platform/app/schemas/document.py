import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class DocumentCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=512)
    description: str = ""
    dept_id: uuid.UUID | None = None


class DocumentVersionOut(BaseModel):
    id: uuid.UUID
    version_no: int
    file_name: str
    file_size: int
    mime_type: str
    created_at: datetime

    model_config = {"from_attributes": True}


class DocumentListItem(BaseModel):
    id: uuid.UUID
    title: str
    status: str
    owner_id: uuid.UUID
    dept_id: uuid.UUID | None
    current_version_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class DocumentDetail(DocumentListItem):
    description: str
    versions: list[DocumentVersionOut] = []


class UploadPrepareResponse(BaseModel):
    document_id: uuid.UUID
    version_id: uuid.UUID
    upload_url: str
    file_key: str
    expires_in: int = 3600


class UploadCompleteRequest(BaseModel):
    version_id: uuid.UUID
    file_size: int = Field(..., ge=0)
    checksum: str | None = None


class DocumentGrant(BaseModel):
    subject_type: str = Field(..., pattern="^(user|dept|role)$")
    subject_id: uuid.UUID
    level: str = Field(..., pattern="^(read|use|delete)$")
    expires_at: datetime | None = None


class DocumentPermissionOut(BaseModel):
    id: uuid.UUID
    subject_type: str
    subject_id: uuid.UUID
    level: str
    expires_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}
