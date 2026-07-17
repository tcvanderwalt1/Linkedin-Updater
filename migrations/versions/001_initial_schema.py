"""Initial schema: articles, drafts, linkedin_tokens, pipeline_runs."""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "pipeline_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("articles_saved", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("drafts_created", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_message", sa.Text(), nullable=True),
    )

    op.create_table(
        "articles",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("snippet", sa.Text(), nullable=False),
        sa.Column("source", sa.String(512), nullable=False),
        sa.Column("topics", sa.Text(), nullable=False),
        sa.Column("quality_score", sa.Float(), nullable=False, server_default="0"),
        sa.Column("is_spam", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("title_norm", sa.String(512), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "fetched_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("fetch_date", sa.Date(), nullable=False),
        sa.Column(
            "pipeline_run_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("pipeline_runs.id"),
            nullable=True,
        ),
        sa.UniqueConstraint("url", name="uq_articles_url"),
    )
    op.create_index("ix_articles_fetch_date", "articles", ["fetch_date"])
    op.create_index("ix_articles_fetched_at", "articles", ["fetched_at"])

    op.create_table(
        "drafts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "article_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("articles.id"),
            nullable=False,
        ),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("linkedin_post_urn", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("model_name", sa.String(128), nullable=False),
    )
    op.create_index("ix_drafts_status", "drafts", ["status"])

    op.create_table(
        "linkedin_tokens",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("access_token", sa.Text(), nullable=False),
        sa.Column("refresh_token", sa.Text(), nullable=False),
        sa.Column("access_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("refresh_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("member_urn", sa.String(256), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_table("linkedin_tokens")
    op.drop_index("ix_drafts_status", table_name="drafts")
    op.drop_table("drafts")
    op.drop_index("ix_articles_fetched_at", table_name="articles")
    op.drop_index("ix_articles_fetch_date", table_name="articles")
    op.drop_table("articles")
    op.drop_table("pipeline_runs")
