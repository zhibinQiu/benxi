import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class DocumentCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=512)
    description: str = ""
    scope: str = Field(
        "personal",
        pattern="^(company|department|team|personal)$",
    )
    dept_id: uuid.UUID | None = None
    folder_id: uuid.UUID | None = None


class DocumentUpdate(BaseModel):
    title: str | None = Field(None, min_length=1, max_length=512)
    description: str | None = None
    scope: str | None = Field(
        None,
        pattern="^(company|department|team|personal)$",
    )
    dept_id: uuid.UUID | None = None


class DocumentMoveIn(BaseModel):
    """移动到同分级下的知识库文件夹；folder_id 为空表示归入「未分类」。"""

    folder_id: uuid.UUID | None = None


class DocumentBatchDeleteIn(BaseModel):
    document_ids: list[uuid.UUID] = Field(..., min_length=1, max_length=100)
    permanent: bool = True


class DocumentBatchDeleteOut(BaseModel):
    deleted: list[str] = Field(default_factory=list)
    failed: list[dict[str, str]] = Field(default_factory=list)
    deleted_count: int = 0


class DocumentVersionOut(BaseModel):
    id: uuid.UUID
    version_no: int
    file_name: str
    file_size: int
    mime_type: str
    created_at: datetime
    uploaded: bool = False
    is_current: bool = False
    knowledge_synced: bool = False
    parse_status: str | None = None
    parse_progress: int | None = None
    parse_message: str | None = None
    chunk_count: int | None = None
    ragflow_document_id: str | None = None
    index_engine: str | None = None
    change_description: str = ""

    model_config = {"from_attributes": True}


class DeleteDocumentVersionResult(BaseModel):
    ok: bool = True
    document_deleted: bool = False
    message: str = ""


class DocumentFolderOut(BaseModel):
    scope: str
    label: str
    can_create: bool
    can_edit: bool
    can_delete: bool
    can_manage_folders: bool = False


class KbFolderOut(BaseModel):
    id: uuid.UUID | None = None
    virtual_id: str | None = None
    name: str
    description: str = ""
    scope: str
    dept_id: uuid.UUID | None = None
    kind: str = "normal"
    is_system: bool = False
    system_hint: str | None = None
    document_count: int = 0
    can_manage: bool = False


class KbFolderListOut(BaseModel):
    scope: str
    dept_id: uuid.UUID | None = None
    can_manage_folders: bool = False
    items: list[KbFolderOut] = []


class KbFolderCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=256)
    description: str = Field(default="", max_length=2000)
    scope: str = Field(..., pattern="^(company|department|team|personal)$")
    dept_id: uuid.UUID | None = None


class KbFolderUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=256)
    description: str | None = Field(default=None, max_length=2000)


class DocumentLibraryOut(BaseModel):
    folders: list[DocumentFolderOut]
    companies: list[dict] = []
    departments: list[dict] = []
    teams: list[dict] = []
    personal_owners: list[dict] = []


class DocumentFormatOverviewItem(BaseModel):
    format: str = Field(description="格式标签（如 pdf、word）")
    label: str = Field(description="格式展示名")
    total: int = Field(description="该格式文档总数")
    parsed: int = Field(description="该格式已解析/已索引文档数")


class DocumentFormatOverviewOut(BaseModel):
    items: list[DocumentFormatOverviewItem] = Field(default_factory=list)
    total: int = Field(description="可修改权限文档总数")
    parsed_total: int = Field(description="已解析/已索引文档总数")


class DocumentListItem(BaseModel):
    id: uuid.UUID
    title: str
    status: str
    scope: str
    folder_id: uuid.UUID | None = None
    folder_name: str | None = None
    owner_id: uuid.UUID
    owner_name: str | None = None
    dept_id: uuid.UUID | None
    dept_name: str | None = None
    current_version_id: uuid.UUID | None
    file_format: str | None = None
    created_at: datetime
    updated_at: datetime
    uploaded_at: datetime | None = None
    deleted_at: datetime | None = None
    shared_level: str | None = None
    granted_by_name: str | None = None
    share_to_summary: str | None = None
    share_count: int | None = None
    effective_level: str | None = None
    can_modify: bool = False
    can_edit: bool = False
    can_delete: bool = False
    knowledge_synced: bool = False
    parse_status: str | None = None
    parse_progress: int | None = None
    parse_message: str | None = None
    chunk_count: int | None = None
    ragflow_document_id: str | None = None
    indexed_version_id: uuid.UUID | None = None
    indexed_version_no: int | None = None

    model_config = {"from_attributes": True}


class DocumentDetail(DocumentListItem):
    description: str
    versions: list[DocumentVersionOut] = []


class UploadPrepareResponse(BaseModel):
    document_id: uuid.UUID
    version_id: uuid.UUID
    upload_url: str
    file_key: str
    expires_in: int = 3600


class UploadCompleteRequest(BaseModel):
    version_id: uuid.UUID
    file_size: int = Field(..., ge=0)
    checksum: str | None = None
    change_description: str = ""


class DocumentUploadCompleteOut(BaseModel):
    document: DocumentDetail
    knowledge_job_id: str | None = None


class DocumentKnowflowSyncOut(BaseModel):
    knowflow_synced: bool = False
    ragflow_document_id: str | None = None
    dataset_id: str | None = None
    message: str = ""


class DocumentGrant(BaseModel):
    subject_type: str = Field(..., pattern="^user$")
    subject_id: uuid.UUID
    level: str = Field(
        ...,
        pattern="^(visible|query|edit|full|read|use|delete)$",
    )
    expires_at: datetime | None = None


class DocumentPermissionOut(BaseModel):
    id: uuid.UUID
    subject_type: str
    subject_id: uuid.UUID
    subject_label: str | None = None
    level: str
    expires_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


class DocumentShareOut(BaseModel):
    """文档当前分享状态：每人一条，仅表示对该用户的授权级别。"""

    user_id: uuid.UUID
    user_name: str | None = None
    level: str


class DocumentShareBatchIn(BaseModel):
    user_ids: list[uuid.UUID] = Field(..., min_length=1, max_length=200)
    level: str = Field(
        ...,
        pattern="^(visible|query|edit|full|read|use|delete)$",
    )


class DocumentStatusUpdate(BaseModel):
    status: str = Field(..., pattern="^(active|disabled)$")


class DocumentAccessControlOut(BaseModel):
    can_grant: bool
    can_deny: bool
    is_owner: bool
    can_view: bool = False
    can_query: bool = False
    can_modify: bool = False
    can_edit: bool = False
    can_delete: bool = False
    can_manage: bool = False
    can_restore: bool = False
    effective_level: str | None = None


class AclUserCandidateOut(BaseModel):
    id: uuid.UUID
    username: str
    display_name: str
    department_id: uuid.UUID | None = None
    department_names: list[str] = []
    department_ids: list[uuid.UUID] = []


class DepartmentPickerOut(BaseModel):
    id: uuid.UUID
    name: str
    parent_id: uuid.UUID | None = None


class AclPickerOut(BaseModel):
    """分享/禁止访问时的组织树数据（公司 → 部门 → 员工）。"""

    company_label: str = "公司"
    departments: list[DepartmentPickerOut] = []
    users: list[AclUserCandidateOut] = []
