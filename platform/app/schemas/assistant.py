from pydantic import BaseModel, Field


class AssistantChatMessage(BaseModel):
    role: str = Field(..., pattern="^(user|assistant)$")
    content: str = Field(..., min_length=1, max_length=8000)


class AssistantChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000)
    history: list[AssistantChatMessage] = Field(default_factory=list, max_length=20)
    page_hint: str | None = Field(None, max_length=200)
    conversation_id: str | None = Field(None, max_length=128)


class AssistantChatResponse(BaseModel):
    reply: str
    model: str
    conversation_id: str | None = None
