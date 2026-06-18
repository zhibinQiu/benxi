import uuid
from datetime import datetime

from pydantic import BaseModel


class CpuMetrics(BaseModel):
    percent: float
    count_logical: int | None
    count_physical: int | None
    load_avg: list[float] | None = None


class MemoryMetrics(BaseModel):
    total_bytes: int
    used_bytes: int
    available_bytes: int
    percent: float


class SwapMetrics(BaseModel):
    total_bytes: int
    used_bytes: int
    percent: float


class DiskMetrics(BaseModel):
    path: str
    total_bytes: int
    used_bytes: int
    free_bytes: int
    percent: float


class GpuMetrics(BaseModel):
    index: int
    name: str
    memory_total_mb: float
    memory_used_mb: float
    memory_free_mb: float
    utilization_percent: float | None = None


class KnowflowQueueMetrics(BaseModel):
    enabled: bool = False
    available: bool = False
    pending_tasks: int = 0
    running_tasks: int = 0
    failed_tasks: int = 0
    parsing_documents: int = 0
    unstarted_documents: int = 0
    queue_lag: int = 0
    executor_active: bool = False
    duplicate_document_groups: int = 0
    duplicate_documents_extra: int = 0
    top_backlog_documents: list[dict[str, str | int]] = []
    error: str | None = None


class SystemMetricsOut(BaseModel):
    collected_at: float
    app_version: str
    hostname: str
    platform: str
    python_version: str
    uptime_seconds: int
    cpu: CpuMetrics
    memory: MemoryMetrics
    swap: SwapMetrics
    disk: DiskMetrics
    gpus: list[GpuMetrics] = []
    knowflow_queue: KnowflowQueueMetrics | None = None


class AuditLogItemOut(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID | None
    username: str | None = None
    action: str
    resource_type: str
    resource_id: str | None
    ip_address: str | None
    detail: dict | None
    created_at: datetime
