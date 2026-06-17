from __future__ import annotations

import uuid

from pydantic import BaseModel, Field

from app.services.knowledge_parser_service import default_reindex_parser_id


class KnowledgeLibraryOut(BaseModel):
    dataset_id: str
    label: str
    scope: str | None = None
    document_count: int = 0


class KnowledgeLibraryListOut(BaseModel):
    items: list[KnowledgeLibraryOut]
    knowflow_enabled: bool = False


class KnowledgeLibraryDocumentOut(BaseModel):
    document_id: str
    title: str
    scope: str | None = None
    file_name: str = ""
    ragflow_document_id: str | None = None
    knowledge_synced: bool = False
    synced_at: str | None = None
    chunk_count: int | None = None
    parse_status: str | None = None


class KnowledgeScopeTreeNodeOut(BaseModel):
    key: str
    label: str
    type: str
    scope: str | None = None
    dataset_id: str | None = None
    document_id: str | None = None
    folder_id: str | None = None
    virtual_folder_id: str | None = None
    kind: str | None = None
    document_count: int | None = None
    index_ready_count: int | None = None
    index_ready: bool | None = None
    knowledge_synced: bool | None = None
    parse_status: str | None = None
    is_leaf: bool = False
    children: list["KnowledgeScopeTreeNodeOut"] = Field(default_factory=list)


class KnowledgeScopeTreeOut(BaseModel):
    items: list[KnowledgeScopeTreeNodeOut]
    knowflow_enabled: bool = False


class KnowledgeChunkOut(BaseModel):
    id: str
    content: str
    page: int | None = None
    score: float | None = None


class KnowledgeChunksOut(BaseModel):
    document_id: str
    version_id: str | None = None
    version_no: int | None = None
    title: str
    dataset_id: str | None = None
    ragflow_document_id: str | None = None
    chunk_count: int = 0
    items: list[KnowledgeChunkOut]
    total: int
    page: int
    page_size: int


class KnowledgeQaSessionCreate(BaseModel):
    document_ids: list[str] = Field(..., min_length=1, max_length=20)
    title: str = "知识检索"


class KnowledgeQaAskRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=4000)
    session_id: str | None = None
    document_ids: list[str] | None = Field(default=None, max_length=20)
    use_agentic: bool = True


class KnowledgeQaChatStreamRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=4000)
    conversation_id: str | None = None
    document_ids: list[str] | None = Field(default=None, max_length=20)
    use_agentic: bool = True


class KnowledgeQaMindmapRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=500)
    answer: str = Field(..., min_length=1, max_length=12000)


class KnowledgeQaMindmapOut(BaseModel):
    mermaid: str
    source: str = "llm"


class KnowledgeReindexRequest(BaseModel):
    parser_id: str = Field(
        default_factory=default_reindex_parser_id,
        min_length=1,
        max_length=32,
    )
    layout_recognize: str | None = Field(
        default=None,
        description="PDF 版面识别 / OCR 引擎",
    )
    resync: bool = Field(
        default=False,
        description="索引失效时先全量重新同步再解析",
    )
    version_id: uuid.UUID | None = Field(
        default=None,
        description="指定文档版本；默认当前版本",
    )
