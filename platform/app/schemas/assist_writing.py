from pydantic import BaseModel, Field


class AssistWritingRequest(BaseModel):
    markdown: str = ""
    instruction: str = ""
    preset_id: str | None = None


class AssistWritingResponse(BaseModel):
    markdown: str
    model: str
    preset_id: str | None = None


class AssistPresetOut(BaseModel):
    id: str
    label: str
    description: str = ""
