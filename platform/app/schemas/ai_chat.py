from pydantic import BaseModel, Field


class AiChatMessage(BaseModel):
    role: str = Field(..., pattern="^(user|assistant)$")
    content: str = Field(..., min_length=1, max_length=16000)


class AiChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=8000)
    history: list[AiChatMessage] = Field(default_factory=list, max_length=40)
    conversation_id: str | None = Field(None, max_length=128)


class ChatCitation(BaseModel):
    index: int
    title: str
    snippet: str = ""
    score: float | None = None
    document_id: str | None = None
    dataset_id: str | None = None
    segment_id: str | None = None
    source: str | None = None
    entity_id: str | None = None
    type_label: str | None = None


class AiChatResponse(BaseModel):
    reply: str
    model: str
    conversation_id: str | None = None
    citations: list[ChatCitation] = Field(default_factory=list)
