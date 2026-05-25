import uuid
from datetime import datetime

from pydantic import BaseModel, Field, field_validator


class DepartmentCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    parent_id: uuid.UUID | None = None
    sort_order: int = 0


class DepartmentUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    parent_id: uuid.UUID | None = None
    sort_order: int | None = None


class DepartmentOut(BaseModel):
    id: uuid.UUID
    name: str
    parent_id: uuid.UUID | None
    sort_order: int
    created_at: datetime

    model_config = {"from_attributes": True}


class UserCreate(BaseModel):
    username: str = Field(..., min_length=2, max_length=64, description="用户名，至少 2 个字符")
    password: str = Field(..., min_length=6, description="密码，至少 6 个字符")
    display_name: str = ""
    email: str | None = None
    department_ids: list[uuid.UUID] = []
    role_ids: list[uuid.UUID] = []

    @field_validator("username")
    @classmethod
    def username_not_blank(cls, v: str) -> str:
        s = v.strip()
        if len(s) < 2:
            raise ValueError("用户名至少 2 个字符")
        return s

    @field_validator("password")
    @classmethod
    def password_not_blank(cls, v: str) -> str:
        if len(v) < 6:
            raise ValueError("密码至少 6 个字符")
        return v


class UserUpdate(BaseModel):
    username: str | None = Field(default=None, min_length=2, max_length=64)
    password: str | None = Field(default=None, min_length=6)
    display_name: str | None = None
    email: str | None = None
    status: str | None = None
    department_ids: list[uuid.UUID] | None = None
    role_ids: list[uuid.UUID] | None = None

    @field_validator("username")
    @classmethod
    def username_optional(cls, v: str | None) -> str | None:
        if v is None:
            return None
        s = v.strip()
        if len(s) < 2:
            raise ValueError("用户名至少 2 个字符")
        return s

    @field_validator("password")
    @classmethod
    def password_optional(cls, v: str | None) -> str | None:
        if v is None or v == "":
            return None
        if len(v) < 6:
            raise ValueError("密码至少 6 个字符")
        return v


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
