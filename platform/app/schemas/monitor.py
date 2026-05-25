import uuid
from datetime import datetime
from typing import Any

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
