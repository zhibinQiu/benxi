"""自动化任务 API schema。"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

Frequency = Literal["once", "hourly", "daily", "weekly", "monthly"]


class AutomationCreate(BaseModel):
    name: str = Field(min_length=1, max_length=256)
    prompt: str = Field(min_length=1, max_length=8000)
    frequency: Frequency = "daily"
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    enabled: bool = True


class AutomationUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=256)
    prompt: str | None = Field(default=None, min_length=1, max_length=8000)
    frequency: Frequency | None = None
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    enabled: bool | None = None


class AutomationOut(BaseModel):
    id: uuid.UUID
    name: str
    prompt: str
    frequency: str
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    next_run_at: datetime | None = None
    last_run_at: datetime | None = None
    enabled: bool
    cancelled_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class AutomationRunOut(BaseModel):
    id: uuid.UUID
    automation_id: uuid.UUID
    automation_name: str = ""
    status: str
    result_summary: str | None = None
    error: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    created_at: datetime | None = None


class ScheduledReminderOut(BaseModel):
    """来自 schedule_notification 的一次性提醒（汇总展示）。"""

    id: uuid.UUID
    title: str
    body: str = ""
    scheduled_at: datetime | None = None
    sent_at: datetime | None = None
    cancelled_at: datetime | None = None
    created_at: datetime | None = None
    kind: str = "reminder"


class AutomationOverviewOut(BaseModel):
    automations: list[AutomationOut]
    runs: list[AutomationRunOut]
    reminders: list[ScheduledReminderOut]
