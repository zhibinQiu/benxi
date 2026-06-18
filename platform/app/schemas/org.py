import uuid
from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from app.core.phone import normalize_phone
from app.core.user_department import validate_department_id_list
from app.core.user_identity import normalize_email, normalize_username


class DepartmentCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    parent_id: uuid.UUID | None = None


class DepartmentUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    parent_id: uuid.UUID | None = None


class DepartmentOut(BaseModel):
    id: uuid.UUID
    name: str
    parent_id: uuid.UUID | None
    created_at: datetime

    model_config = {"from_attributes": True}


class UserCreate(BaseModel):
    phone: str = Field(..., description="11 位手机号，用于登录")
    email: str = Field(..., description="邮箱")
    display_name: str = Field(..., min_length=2, max_length=64, description="显示名")
    username: str | None = Field(
        default=None, min_length=2, max_length=64, description="用户名（登录用）"
    )
    password: str = Field(..., min_length=6, description="密码，至少 6 个字符")
    status: str = Field(default="active", description="active | disabled")
    department_ids: list[uuid.UUID] = []
    role_ids: list[uuid.UUID] = []

    @field_validator("phone")
    @classmethod
    def valid_phone(cls, v: str) -> str:
        return normalize_phone(v)

    @field_validator("email")
    @classmethod
    def valid_email(cls, v: str) -> str:
        return normalize_email(v)

    @field_validator("username")
    @classmethod
    def valid_username_optional(cls, v: str | None) -> str | None:
        if v is None or not str(v).strip():
            return None
        return normalize_username(v)

    @field_validator("department_ids")
    @classmethod
    def at_most_one_department(cls, v: list[uuid.UUID]) -> list[uuid.UUID]:
        return validate_department_id_list(v)

    @field_validator("display_name")
    @classmethod
    def display_name_not_blank(cls, v: str) -> str:
        s = v.strip()
        if len(s) < 2:
            raise ValueError("显示名至少 2 个字符")
        return s

    @field_validator("password")
    @classmethod
    def password_not_blank(cls, v: str) -> str:
        if len(v) < 6:
            raise ValueError("密码至少 6 个字符")
        return v

    @field_validator("status")
    @classmethod
    def valid_status(cls, v: str) -> str:
        if v not in ("active", "disabled"):
            raise ValueError("Invalid status")
        return v


class UserUpdate(BaseModel):
    phone: str | None = Field(default=None, description="11 位手机号")
    username: str | None = Field(default=None, min_length=2, max_length=64)
    display_name: str | None = Field(default=None, min_length=2, max_length=64)
    password: str | None = Field(default=None, min_length=6)
    email: str | None = None
    status: str | None = None
    department_ids: list[uuid.UUID] | None = None
    role_ids: list[uuid.UUID] | None = None

    @field_validator("phone")
    @classmethod
    def valid_phone_optional(cls, v: str | None) -> str | None:
        if v is None or v == "":
            return None
        return normalize_phone(v)

    @field_validator("email")
    @classmethod
    def valid_email_optional(cls, v: str | None) -> str | None:
        if v is None:
            return None
        return normalize_email(str(v))

    @field_validator("username")
    @classmethod
    def valid_username_optional(cls, v: str | None) -> str | None:
        if v is None:
            return None
        return normalize_username(v)

    @field_validator("department_ids")
    @classmethod
    def at_most_one_department(
        cls, v: list[uuid.UUID] | None
    ) -> list[uuid.UUID] | None:
        if v is None:
            return None
        return validate_department_id_list(v)

    @field_validator("display_name")
    @classmethod
    def display_name_optional(cls, v: str | None) -> str | None:
        if v is None:
            return None
        s = v.strip()
        if len(s) < 2:
            raise ValueError("显示名至少 2 个字符")
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
    phone: str | None = None
    display_name: str
    username: str
    email: str | None
    status: str
    created_at: datetime
    department_id: uuid.UUID | None = None
    department_ids: list[uuid.UUID] = []
    role_ids: list[uuid.UUID] = []
    role_names: list[str] = []

    @field_validator("department_ids")
    @classmethod
    def at_most_one_department_out(cls, v: list[uuid.UUID]) -> list[uuid.UUID]:
        return validate_department_id_list(v)

    model_config = {"from_attributes": True}


class RoleOut(BaseModel):
    id: uuid.UUID
    code: str
    name: str
    description: str
    permission_codes: list[str] = []

    model_config = {"from_attributes": True}
