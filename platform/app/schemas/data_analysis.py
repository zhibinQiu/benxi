"""数据分析 — Excel 上传、对话生成代码、Notebook 单元格执行。"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class ColumnProfileOut(BaseModel):
    name: str
    dtype: str
    null_count: int | None = None
    non_null_count: int | None = None
    sample_values: list[str] = Field(default_factory=list)
    min_value: str | None = None
    max_value: str | None = None
    mean_value: str | None = None


class SheetProfileOut(BaseModel):
    name: str
    rows: int
    columns: int
    column_profiles: list[ColumnProfileOut] = Field(default_factory=list)
    sample_rows: list[list[str]] = Field(default_factory=list)


class DatasetProfileOut(BaseModel):
    filename: str
    file_type: str = "excel"
    sheets: list[SheetProfileOut] = Field(default_factory=list)
    active_sheet: str
    file_size_bytes: int


class DatasetUploadOut(BaseModel):
    dataset_id: str
    profile: DatasetProfileOut


class DataAnalysisMetaOut(BaseModel):
    configured: bool
    llm_model: str | None = None
    max_file_mb: int
    accepted_extensions: list[str] = Field(
        default_factory=lambda: [".xlsx", ".xls", ".csv"]
    )
    exec_timeout_seconds: int
    service_hint: str | None = None


class ChatMessageOut(BaseModel):
    role: Literal["user", "assistant", "system"]
    content: str


class NotebookCellOut(BaseModel):
    id: str
    title: str
    code: str
    status: Literal["idle", "running", "success", "error"] = "idle"
    stdout: str = ""
    stderr: str = ""
    images: list[str] = Field(default_factory=list)


class SessionOut(BaseModel):
    session_id: str
    dataset_id: str | None = None
    profile: DatasetProfileOut | None = None
    active_sheet: str | None = None
    messages: list[ChatMessageOut] = Field(default_factory=list)
    cells: list[NotebookCellOut] = Field(default_factory=list)


class SessionCreateIn(BaseModel):
    dataset_id: str | None = None


class ChatIn(BaseModel):
    message: str = Field(min_length=1, max_length=8000)
    dataset_id: str | None = None


class ChatOut(BaseModel):
    reply: str
    cells_added: list[NotebookCellOut] = Field(default_factory=list)
    session: SessionOut


class CellUpdateIn(BaseModel):
    code: str = Field(min_length=1, max_length=32000)
    title: str | None = Field(default=None, max_length=200)


class CellRunOut(BaseModel):
    cell: NotebookCellOut


class LlmCellDraft(BaseModel):
    title: str = "分析单元"
    code: str
