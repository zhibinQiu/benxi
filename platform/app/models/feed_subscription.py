"""RSS/Atom 与网站资讯订阅（知识中心 · 订阅）。"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

SOURCE_KIND_RSS = "rss"
SOURCE_KIND_WEBSITE = "website"
SOURCE_KIND_LINK = "link"


class FeedSource(Base):
    __tablename__ = "feed_sources"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    feed_url: Mapped[str] = mapped_column(String(1024), unique=True, index=True)
    site_url: Mapped[str] = mapped_column(String(1024), default="")
    name: Mapped[str] = mapped_column(String(256))
    kind: Mapped[str] = mapped_column(String(16), default=SOURCE_KIND_RSS, index=True)
    category: Mapped[str] = mapped_column(String(64), default="")
    icon_url: Mapped[str] = mapped_column(String(1024), default="")
    sync_status: Mapped[str] = mapped_column(String(32), default="idle")
    sync_message: Mapped[str] = mapped_column(Text, default="")
    last_sync_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    subscriptions: Mapped[list["FeedSourceSubscription"]] = relationship(
        back_populates="source"
    )
    entries: Mapped[list["FeedEntry"]] = relationship(back_populates="source")


class FeedSourceSubscription(Base):
    __tablename__ = "feed_source_subscriptions"
    __table_args__ = (
        UniqueConstraint("user_id", "source_id", name="uq_feed_sub_user_source"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    source_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("feed_sources.id", ondelete="CASCADE"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    source: Mapped["FeedSource"] = relationship(back_populates="subscriptions")


class FeedEntry(Base):
    __tablename__ = "feed_entries"
    __table_args__ = (
        UniqueConstraint("source_id", "entry_key", name="uq_feed_entry_key"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    source_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("feed_sources.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str] = mapped_column(String(512))
    summary: Mapped[str] = mapped_column(Text, default="")
    link: Mapped[str] = mapped_column(String(1024), default="")
    content_html: Mapped[str] = mapped_column(Text, default="")
    entry_key: Mapped[str] = mapped_column(String(128), index=True)
    publish_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    source: Mapped["FeedSource"] = relationship(back_populates="entries")
    imports: Mapped[list["FeedEntryImport"]] = relationship(back_populates="entry")


class FeedEntryImport(Base):
    __tablename__ = "feed_entry_imports"
    __table_args__ = (
        UniqueConstraint("entry_id", "user_id", name="uq_feed_import_user"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    entry_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("feed_entries.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE")
    )
    imported_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    entry: Mapped["FeedEntry"] = relationship(back_populates="imports")
