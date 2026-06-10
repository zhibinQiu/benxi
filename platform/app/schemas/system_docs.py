from pydantic import BaseModel, Field


class SystemDocItemOut(BaseModel):
    key: str
    title: str
    path: str
    available: bool = True


class SystemDocGroupOut(BaseModel):
    key: str
    title: str
    children: list[SystemDocItemOut] = Field(default_factory=list)


class SystemDocContentOut(BaseModel):
    path: str
    title: str
    content: str
