import uuid

from pydantic import BaseModel, Field, field_validator, model_validator

from app.core.phone import normalize_phone
from app.core.user_identity import normalize_email, normalize_username


class LoginRequest(BaseModel):
    account: str = Field(..., min_length=1, description="手机号或姓名")
    password: str
    captcha_token: str | None = Field(default=None, description="滑块验证码 token")

    @model_validator(mode="before")
    @classmethod
    def accept_legacy_phone_field(cls, data: object) -> object:
        if isinstance(data, dict) and "phone" in data and "account" not in data:
            data = {**data, "account": data["phone"]}
        return data

    @field_validator("account")
    @classmethod
    def strip_account(cls, v: str) -> str:
        s = (v or "").strip()
        if not s:
            raise ValueError("请输入手机号或姓名")
        return s


class RegisterRequest(BaseModel):
    phone: str = Field(..., description="11 位手机号")
    email: str = Field(..., description="邮箱")
    password: str = Field(..., min_length=6)
    display_name: str = Field(..., min_length=2, max_length=64, description="显示名")
    username: str | None = Field(
        default=None,
        min_length=2,
        max_length=64,
        description="用户名（登录用，默认同显示名）",
    )
    captcha_token: str | None = Field(default=None, description="滑块验证码 token")

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

    @field_validator("display_name")
    @classmethod
    def display_name_not_blank(cls, v: str) -> str:
        s = v.strip()
        if len(s) < 2:
            raise ValueError("姓名至少 2 个字符")
        return s

    @field_validator("password")
    @classmethod
    def password_not_blank(cls, v: str) -> str:
        if len(v) < 6:
            raise ValueError("密码至少 6 个字符")
        return v


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class MeResponse(BaseModel):
    id: uuid.UUID
    phone: str | None = None
    display_name: str
    username: str  # 与 display_name 相同，兼容旧前端
    email: str | None
    permissions: list[str]
    department_id: uuid.UUID | None = None
    department_ids: list[uuid.UUID] = []
    department_name: str | None = None
    role_names: list[str] = []
    is_bootstrap_admin: bool = False
    is_system_admin: bool = False


class ProfileUpdate(BaseModel):
    display_name: str | None = Field(default=None, min_length=2, max_length=64)
    email: str | None = None
    password: str | None = Field(default=None, min_length=6)


class CaptchaRequest(BaseModel):
    width: int = 280


class CaptchaResponse(BaseModel):
    token: str
    offset: int
    width: int = 280


class CaptchaVerifyRequest(BaseModel):
    token: str
    offset: int

    @field_validator("email")
    @classmethod
    def valid_email_optional(cls, v: str | None) -> str | None:
        if v is None:
            return None
        return normalize_email(str(v))

    @field_validator("display_name")
    @classmethod
    def display_name_optional(cls, v: str | None) -> str | None:
        if v is None:
            return None
        s = v.strip()
        if len(s) < 2:
            raise ValueError("姓名至少 2 个字符")
        return s

    @field_validator("password")
    @classmethod
    def password_optional(cls, v: str | None) -> str | None:
        if v is None or v == "":
            return None
        if len(v) < 6:
            raise ValueError("密码至少 6 个字符")
        return v
