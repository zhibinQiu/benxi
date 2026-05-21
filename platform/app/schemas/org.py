import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class DepartmentCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    parent_id: uuid.UUID | None = None
    sort_order: int = 0


class DepartmentOut(BaseModel):
    id: uuid.UUID
    name: str
    parent_id: uuid.UUID | None
    sort_order: int
    created_at: datetime

    model_config = {"from_attributes": True}


class UserCreate(BaseModel):
    username: str = Field(..., min_length=2, max_length=64)
    password: str = Field(..., min_length=6)
    display_name: str = ""
    email: str | None = None
    department_ids: list[uuid.UUID] = []
    role_ids: list[uuid.UUID] = []


class UserUpdate(BaseModel):
    display_name: str | None = None
    email: str | None = None
    status: str | None = None
    department_ids: list[uuid.UUID] | None = None
    role_ids: list[uuid.UUID] | None = None


class UserOut(BaseModel):
    id: uuid.UUID
    username: str
    display_name: str
    email: str | None
    status: str
    created_at: datetime
    department_ids: list[uuid.UUID] = []
    role_ids: list[uuid.UUID] = []

    model_config = {"from_attributes": True}


class RoleOut(BaseModel):
    id: uuid.UUID
    code: str
    name: str
    description: str
    permission_codes: list[str] = []

    model_config = {"from_attributes": True}
