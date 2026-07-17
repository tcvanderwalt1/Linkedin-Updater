"""SQLAlchemy ORM models for Neon Postgres."""

from __future__ import annotations

import enum
import uuid
from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class DraftStatus(str, enum.Enum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"
    published = "published"
    failed = "failed"


class PipelineRunStatus(str, enum.Enum):
    running = "running"
    success = "success"
    empty = "empty"
    failed = "failed"


class Article(Base):
    __tablename__ = "articles"
    __table_args__ = (UniqueConstraint("url", name="uq_articles_url"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    url: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    snippet: Mapped[str] = mapped_column(Text, nullable=False, default="")
    source: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    topics: Mapped[str] = mapped_column(Text, nullable=False, default="")
    quality_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    is_spam: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    title_norm: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    fetch_date: Mapped[date] = mapped_column(Date, nullable=False)
    pipeline_run_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("pipeline_runs.id"), nullable=True
    )

    drafts: Mapped[list[Draft]] = relationship(back_populates="article")
    pipeline_run: Mapped[PipelineRun | None] = relationship(back_populates="articles")


class Draft(Base):
    __tablename__ = "drafts"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    article_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("articles.id"), nullable=False
    )
    body: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default=DraftStatus.pending.value
    )
    linkedin_post_urn: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    model_name: Mapped[str] = mapped_column(String(128), nullable=False, default="")

    article: Mapped[Article] = relationship(back_populates="drafts")


class LinkedInToken(Base):
    """Singleton-style token row (id=1)."""

    __tablename__ = "linkedin_tokens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    access_token: Mapped[str] = mapped_column(Text, nullable=False)
    refresh_token: Mapped[str] = mapped_column(Text, nullable=False)
    access_expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    refresh_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    member_urn: Mapped[str] = mapped_column(String(256), nullable=False, default="")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class PipelineRun(Base):
    __tablename__ = "pipeline_runs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default=PipelineRunStatus.running.value
    )
    articles_saved: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    drafts_created: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_message: Mapped[str | None] = mapped_column(Text)

    articles: Mapped[list[Article]] = relationship(back_populates="pipeline_run")
