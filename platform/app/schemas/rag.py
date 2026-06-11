from pydantic import BaseModel


class RagMessageOut(BaseModel):
    id: str
    role: str
    content: str
    citations: list[dict] = []
    created_at: str | None = None


class RagSessionOut(BaseModel):
    id: str
    title: str
    document_ids: list[str]
    document_titles: dict[str, str] = {}
    messages: list[RagMessageOut] = []
    knowflow: dict = {}
    created_at: str | None = None
