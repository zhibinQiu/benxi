import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class TranslatableDocumentOut(BaseModel):
    id: uuid.UUID
    title: str
    file_name: str
    file_size: int
    updated_at: datetime


class TranslateImportLibraryRequest(BaseModel):
    variant: str = Field(
        default="mono",
        description="mono=单语译文 PDF，dual=双语对照 PDF",
    )
    sync_knowflow: bool = Field(
        default=True,
        description="入库后自动同步至知识库索引",
    )


class TranslateImportLibraryOut(BaseModel):
    document_id: uuid.UUID
    title: str
    knowflow_synced: bool = False
    variant: str = "mono"
    message: str = ""
    already_imported: bool = False
