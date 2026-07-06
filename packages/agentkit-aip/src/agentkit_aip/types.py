"""GB/Z 185.6 智能体交互内容元素（消息 / 任务 / 数据）。"""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field

SenderRole = Literal["request", "service"]


class AipMessageType(str, Enum):
    """AIP 交互消息类型。"""

    TASK_REQUEST = "task_request"
    TASK_RESPONSE = "task_response"
    TASK_ERROR = "task_error"
    WORK_ARTIFACT = "work_artifact"


class AipDataItem(BaseModel):
    """GB/Z 185.6 表2 数据元素（精简实现）。"""

    dataType: str = "text/plain"
    content: Any = None
    label: str | None = None
    encoding: str | None = None


class AipMessage(BaseModel):
    """GB/Z 185.6 表3 消息结构 + 对外信封字段。"""

    id: str
    senderRole: SenderRole
    senderId: str
    sessionId: str
    taskId: str
    artifact: bool = False
    final: bool = False
    lastChunk: bool = True
    Chunkindex: int | None = None
    dataItems: list[AipDataItem] = Field(default_factory=list)
    message_type: AipMessageType | None = None
    targetId: str | None = None
    timestamp: str | None = None
    payload: dict[str, Any] | None = None


class AipTaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


class AipTask(BaseModel):
    """GB/Z 185.6 任务元素（精简）。"""

    id: str
    sessionId: str
    status: AipTaskStatus
    requestAgentId: str
    serviceAgentId: str
    title: str = ""
    summary: str = ""


class AipCapability(BaseModel):
    """GB/Z 185.4 ACDL 能力项（精简）。"""

    id: str
    name: str
    description: str = ""
    input: dict[str, Any] = Field(default_factory=dict)
    output: dict[str, Any] = Field(default_factory=dict)
    constraints: dict[str, Any] = Field(default_factory=dict)


class AipAgentDescription(BaseModel):
    """GB/Z 185.4 智能体描述（ACDL 精简）。"""

    aid: str
    name: str
    version: str = "1.0.0"
    description: str = ""
    capabilities: list[AipCapability] = Field(default_factory=list)
    service_endpoint: str | None = None


class AipInteractEnvelope(BaseModel):
    """对外 AIP 调用信封（兼容 GB/Z 185.6 + 常见 JSON 封装）。"""

    message_id: str | None = None
    source_aid: str | None = None
    target_aid: str | None = None
    conversation_id: str | None = None
    message_type: AipMessageType = AipMessageType.TASK_REQUEST
    payload: dict[str, Any] = Field(default_factory=dict)
    message: AipMessage | None = None
    timestamp: str | None = None
    ttl_seconds: int | None = None
    auth_token: str | None = None
