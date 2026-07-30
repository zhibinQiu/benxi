"""自动化机器学习 — 上传 CSV、任务配置、训练结果。"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

AutoMlTaskType = Literal[
    "classification",
    "regression",
    "clustering",
    "anomaly",
    "time_series",
]

RunStatus = Literal["pending", "running", "done", "failed", "cancelled"]


class AutoMlColumnProfileOut(BaseModel):
    name: str
    dtype: str
    null_count: int | None = None
    non_null_count: int | None = None
    sample_values: list[str] = Field(default_factory=list)


class AutoMlDatasetProfileOut(BaseModel):
    filename: str
    rows: int
    columns: int
    column_profiles: list[AutoMlColumnProfileOut] = Field(default_factory=list)
    sample_rows: list[list[str]] = Field(default_factory=list)
    file_size_bytes: int


class AutoMlDatasetUploadOut(BaseModel):
    dataset_id: str
    profile: AutoMlDatasetProfileOut


class AutoMlTaskTypeOut(BaseModel):
    id: AutoMlTaskType
    label: str
    needs_target: bool
    supports_compare: bool
    default_model: str | None = None


class AutoMlMetaOut(BaseModel):
    configured: bool
    max_file_mb: int
    accepted_extensions: list[str] = Field(default_factory=lambda: [".csv"])
    job_timeout_seconds: int
    service_hint: str | None = None
    task_types: list[AutoMlTaskTypeOut] = Field(default_factory=list)


class AutoMlModelInfoOut(BaseModel):
    id: str
    name: str
    reference: str | None = None


class AutoMlModelsOut(BaseModel):
    task: AutoMlTaskType
    models: list[AutoMlModelInfoOut] = Field(default_factory=list)
    hint: str | None = None


class AutoMlRunCreateIn(BaseModel):
    dataset_id: str
    task: AutoMlTaskType
    target: str | None = None
    feature_columns: list[str] | None = None
    ignore_features: list[str] | None = None
    compare: bool = True
    model_ids: list[str] | None = None
    normalize: bool = True
    date_column: str | None = None
    fh: int = Field(default=3, ge=1, le=365)
    session_id: int = 123


class AutoMlRunSummaryOut(BaseModel):
    run_id: str
    job_id: str | None = None
    dataset_id: str
    task: AutoMlTaskType
    status: RunStatus
    progress: int = 0
    created_at: str | None = None
    error_message: str | None = None
    compare: bool = False
    model_ids: list[str] = Field(default_factory=list)
    target: str | None = None


class AutoMlRunOut(BaseModel):
    run_id: str
    job_id: str | None = None
    dataset_id: str
    task: AutoMlTaskType
    status: RunStatus
    progress: int = 0
    created_at: str | None = None
    started_at: str | None = None
    finished_at: str | None = None
    error_message: str | None = None
    config: dict[str, Any] = Field(default_factory=dict)
    metrics: list[dict[str, Any]] = Field(default_factory=list)
    best_model: str | None = None
    prediction_preview: list[dict[str, Any]] = Field(default_factory=list)
    prediction_columns: list[str] = Field(default_factory=list)
    has_predictions: bool = False
    has_model: bool = False
    message: str | None = None
