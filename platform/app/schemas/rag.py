from pydantic import BaseModel, Field


class RagDocumentOut(BaseModel):
    id: str
    title: str
    file_name: str
    file_size: int
    updated_at: str | None = None


class RagSessionCreate(BaseModel):
    document_ids: list[str] = Field(..., min_length=1, max_length=20)
    title: str = "知识问答"


class RagAskRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=4000)


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
