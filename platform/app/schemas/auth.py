import uuid

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class MeResponse(BaseModel):
    id: uuid.UUID
    username: str
    display_name: str
    email: str | None
    permissions: list[str]
    department_ids: list[uuid.UUID]
