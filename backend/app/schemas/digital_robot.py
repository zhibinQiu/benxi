from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class RpaStep(BaseModel):
    operation: str = Field(..., description="navigate/snapshot/click/type/fill/screenshot")
    params: dict = Field(default_factory=dict)
    description: str = Field("")


class RpaPlan(BaseModel):
    steps: list[RpaStep] = Field(...)
    summary: str = Field("")
    target_url: str = Field("")


class DigitalRobotTaskCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=256)
    description: str = Field("", max_length=2000)
    plan: RpaPlan | None = None
    schedule_mode: str = Field("immediate", pattern=r"^(immediate|scheduled|periodic)$")
    scheduled_at: datetime | None = None
    cron_expression: str | None = None
    interval_seconds: int | None = None


class DigitalRobotTaskUpdate(BaseModel):
    title: str | None = Field(None, max_length=256)
    description: str | None = Field(None, max_length=2000)
    plan: RpaPlan | None = None
    schedule_mode: str | None = Field(None, pattern=r"^(immediate|scheduled|periodic)$")
    scheduled_at: datetime | None = None
    cron_expression: str | None = None
    interval_seconds: int | None = None


class DigitalRobotTaskOut(BaseModel):
    id: str
    user_id: str
    title: str
    description: str
    plan_json: dict | None
    schedule_mode: str
    scheduled_at: datetime | None
    cron_expression: str | None
    interval_seconds: int | None
    status: str
    last_run_at: datetime | None
    next_run_at: datetime | None
    last_result_summary: str | None
    execution_count: int
    error_message: str | None
    created_at: datetime
    updated_at: datetime


class DigitalRobotChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000)
    history: list[dict] = Field(default_factory=list, max_length=20)


class DigitalRobotChatResponse(BaseModel):
    reply: str
    conversation_id: str | None = None
    plan: RpaPlan | None = None
    task_id: str | None = None


class DigitalRobotConfirmRequest(BaseModel):
    conversation_id: str
    plan: RpaPlan | None = None
    task_id: str | None = None


class DigitalRobotConfirmResponse(BaseModel):
    success: bool
    message: str
    screenshot_urls: list[str] = Field(default_factory=list)
    execution_log: list[str] = Field(default_factory=list)
