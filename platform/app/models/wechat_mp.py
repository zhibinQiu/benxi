"""微信公众号跟踪与推文汇总。"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class WechatMpSource(Base):
    __tablename__ = "wechat_mp_sources"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    biz: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(256))
    avatar_url: Mapped[str] = mapped_column(String(1024), default="")
    intro: Mapped[str] = mapped_column(Text, default="")
    sync_status: Mapped[str] = mapped_column(String(32), default="idle")
    sync_message: Mapped[str] = mapped_column(Text, default="")
    last_sync_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    subscriptions: Mapped[list["WechatMpSourceSubscription"]] = relationship(
        back_populates="source"
    )
    articles: Mapped[list["WechatMpArticle"]] = relationship(back_populates="source")


class WechatMpSourceSubscription(Base):
    __tablename__ = "wechat_mp_source_subscriptions"
    __table_args__ = (
        UniqueConstraint("user_id", "source_id", name="uq_wechat_mp_sub_user_source"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    source_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("wechat_mp_sources.id", ondelete="CASCADE"),
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    source: Mapped["WechatMpSource"] = relationship(back_populates="subscriptions")


class WechatMpArticle(Base):
    __tablename__ = "wechat_mp_articles"
    __table_args__ = (
        UniqueConstraint("source_id", "content_hash", name="uq_wechat_mp_article_hash"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    source_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("wechat_mp_sources.id", ondelete="CASCADE"),
        index=True,
    )
    title: Mapped[str] = mapped_column(String(512))
    summary: Mapped[str] = mapped_column(Text, default="")
    cover_url: Mapped[str] = mapped_column(String(1024), default="")
    author: Mapped[str] = mapped_column(String(256), default="")
    publish_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    content_html: Mapped[str] = mapped_column(Text, default="")
    original_url: Mapped[str] = mapped_column(String(1024), default="")
    content_hash: Mapped[str] = mapped_column(String(64), index=True)
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    source: Mapped["WechatMpSource"] = relationship(back_populates="articles")
    imports: Mapped[list["WechatMpArticleImport"]] = relationship(
        back_populates="article"
    )


class WechatMpArticleImport(Base):
    __tablename__ = "wechat_mp_article_imports"
    __table_args__ = (
        UniqueConstraint("article_id", "user_id", name="uq_wechat_mp_import_user"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    article_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("wechat_mp_articles.id", ondelete="CASCADE"),
        index=True,
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

    article: Mapped["WechatMpArticle"] = relationship(back_populates="imports")
