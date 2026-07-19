import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class DocumentStatus(str, enum.Enum):
    draft = "draft"
    active = "active"
    disabled = "disabled"
    archived = "archived"


class PermissionLevel(str, enum.Enum):
    """文档显式授权级别（由低到高：0 可见 < 1 可查 < 2 可修改）。"""

    visible = "visible"
    query = "query"
    modify = "modify"
    # 兼容旧数据与 API
    edit = "edit"
    full = "full"
    read = "read"
    use = "use"
    delete = "delete"


class SubjectType(str, enum.Enum):
    user = "user"
    dept = "dept"
    role = "role"


class DocumentScope(str, enum.Enum):
    company = "company"
    department = "department"
    personal = "personal"


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    title: Mapped[str] = mapped_column(String(512))
    owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id")
    )
    dept_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("departments.id"), nullable=True
    )
    scope: Mapped[str] = mapped_column(
        String(16), default=DocumentScope.personal.value, index=True
    )
    status: Mapped[str] = mapped_column(String(16), default=DocumentStatus.active.value)
    current_version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    description: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    deleted_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    folder_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("document_library_folders.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    share_token: Mapped[str | None] = mapped_column(
        String(64), nullable=True, unique=True, index=True
    )

    versions: Mapped[list["DocumentVersion"]] = relationship(
        back_populates="document",
        foreign_keys="DocumentVersion.document_id",
        cascade="all, delete-orphan",
    )
    permissions: Mapped[list["DocumentPermission"]] = relationship(
        back_populates="document"
    )


class DocumentLibraryFolder(Base):
    """文档库知识库文件夹（公司 / 部门 / 个人级）。"""

    __tablename__ = "document_library_folders"
    __table_args__ = (
        UniqueConstraint(
            "scope",
            "dept_id",
            "owner_id",
            "name",
            name="uq_doc_lib_folder_scope_owner_name",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(256))
    description: Mapped[str] = mapped_column(Text, default="")
    scope: Mapped[str] = mapped_column(String(16), index=True)
    dept_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("departments.id"), nullable=True, index=True
    )
    owner_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True, index=True
    )
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class DocumentVersion(Base):
    __tablename__ = "document_versions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE")
    )
    version_no: Mapped[int] = mapped_column(Integer)
    file_key: Mapped[str] = mapped_column(String(1024))
    file_name: Mapped[str] = mapped_column(String(512))
    file_size: Mapped[int] = mapped_column(Integer, default=0)
    mime_type: Mapped[str] = mapped_column(String(128), default="application/octet-stream")
    checksum: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    change_description: Mapped[str] = mapped_column(Text, default="", server_default="")

    document: Mapped[Document] = relationship(
        back_populates="versions",
        foreign_keys=[document_id],
    )


class DocumentPermission(Base):
    __tablename__ = "document_permissions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE")
    )
    subject_type: Mapped[str] = mapped_column(String(16))
    subject_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    level: Mapped[str] = mapped_column(String(16))
    granted_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id")
    )
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    document: Mapped[Document] = relationship(back_populates="permissions")
