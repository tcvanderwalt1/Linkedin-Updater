"""Repository helpers for articles, drafts, tokens, and pipeline runs."""

from __future__ import annotations

import re
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Any, Sequence

from sqlalchemy import Select, desc, select
from sqlalchemy.orm import Session, joinedload

from src.db.models import (
    Article,
    Draft,
    DraftStatus,
    LinkedInToken,
    PipelineRun,
    PipelineRunStatus,
)


def normalize_title(title: str) -> str:
    text = title.lower().strip()
    text = re.sub(r"[^a-z0-9\s]", "", text)
    text = re.sub(r"\s+", " ", text)
    return text[:512]


def title_tokens(title: str) -> set[str]:
    return {t for t in normalize_title(title).split() if len(t) > 2}


def jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    return inter / union if union else 0.0


class Repository:
    def __init__(self, session: Session) -> None:
        self.session = session

    # --- pipeline runs ---
    def start_pipeline_run(self) -> PipelineRun:
        run = PipelineRun(status=PipelineRunStatus.running.value)
        self.session.add(run)
        self.session.flush()
        return run

    def finish_pipeline_run(
        self,
        run: PipelineRun,
        *,
        status: str,
        articles_saved: int = 0,
        drafts_created: int = 0,
        error_message: str | None = None,
    ) -> PipelineRun:
        run.status = status
        run.articles_saved = articles_saved
        run.drafts_created = drafts_created
        run.error_message = error_message
        run.finished_at = datetime.now(timezone.utc)
        self.session.add(run)
        self.session.flush()
        return run

    def latest_pipeline_run(self) -> PipelineRun | None:
        stmt: Select[tuple[PipelineRun]] = select(PipelineRun).order_by(
            desc(PipelineRun.started_at)
        )
        return self.session.scalars(stmt).first()

    # --- articles ---
    def recent_articles(self, days: int = 30) -> Sequence[Article]:
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        stmt = select(Article).where(Article.fetched_at >= cutoff)
        return list(self.session.scalars(stmt).all())

    def article_urls_in_window(self, days: int = 30) -> set[str]:
        return {a.url for a in self.recent_articles(days)}

    def is_thematic_duplicate(
        self,
        title: str,
        existing: Sequence[Article],
        *,
        threshold: float = 0.72,
    ) -> bool:
        tokens = title_tokens(title)
        norm = normalize_title(title)
        for article in existing:
            if article.title_norm and article.title_norm == norm:
                return True
            if jaccard(tokens, title_tokens(article.title)) >= threshold:
                return True
        return False

    def save_articles(
        self,
        items: Sequence[dict[str, Any]],
        *,
        pipeline_run_id: uuid.UUID | None,
        fetch_date: date | None = None,
    ) -> list[Article]:
        today = fetch_date or date.today()
        saved: list[Article] = []
        for item in items:
            article = Article(
                url=item["url"],
                title=item["title"],
                snippet=item.get("snippet") or "",
                source=item.get("source") or "",
                topics=item.get("topics") or "",
                quality_score=float(item.get("quality_score") or 0.0),
                is_spam=bool(item.get("is_spam") or False),
                title_norm=normalize_title(item["title"]),
                published_at=item.get("published_at"),
                fetch_date=today,
                pipeline_run_id=pipeline_run_id,
            )
            self.session.add(article)
            saved.append(article)
        self.session.flush()
        return saved

    def articles_for_date(self, day: date | None = None) -> Sequence[Article]:
        day = day or date.today()
        stmt = (
            select(Article)
            .where(Article.fetch_date == day)
            .order_by(desc(Article.quality_score))
        )
        return list(self.session.scalars(stmt).all())

    # --- drafts ---
    def create_draft(
        self,
        *,
        article_id: uuid.UUID,
        body: str,
        model_name: str,
        status: str = DraftStatus.pending.value,
    ) -> Draft:
        draft = Draft(
            article_id=article_id,
            body=body,
            model_name=model_name,
            status=status,
        )
        self.session.add(draft)
        self.session.flush()
        return draft

    def list_drafts(
        self,
        *,
        status: str | None = None,
        limit: int = 50,
    ) -> Sequence[Draft]:
        stmt = select(Draft).options(joinedload(Draft.article)).order_by(
            desc(Draft.created_at)
        )
        if status:
            stmt = stmt.where(Draft.status == status)
        stmt = stmt.limit(limit)
        return list(self.session.scalars(stmt).unique().all())

    def get_draft(self, draft_id: uuid.UUID) -> Draft | None:
        stmt = (
            select(Draft)
            .options(joinedload(Draft.article))
            .where(Draft.id == draft_id)
        )
        return self.session.scalars(stmt).first()

    def update_draft_body(self, draft_id: uuid.UUID, body: str) -> Draft | None:
        draft = self.get_draft(draft_id)
        if not draft:
            return None
        draft.body = body
        self.session.add(draft)
        self.session.flush()
        return draft

    def set_draft_status(
        self,
        draft_id: uuid.UUID,
        status: str,
        *,
        linkedin_post_urn: str | None = None,
    ) -> Draft | None:
        draft = self.get_draft(draft_id)
        if not draft:
            return None
        draft.status = status
        now = datetime.now(timezone.utc)
        if status == DraftStatus.approved.value:
            draft.approved_at = now
        if status == DraftStatus.published.value:
            draft.published_at = now
            if linkedin_post_urn:
                draft.linkedin_post_urn = linkedin_post_urn
        if linkedin_post_urn and status != DraftStatus.published.value:
            draft.linkedin_post_urn = linkedin_post_urn
        self.session.add(draft)
        self.session.flush()
        return draft

    # --- linkedin tokens ---
    def get_linkedin_token(self) -> LinkedInToken | None:
        return self.session.get(LinkedInToken, 1)

    def upsert_linkedin_token(
        self,
        *,
        access_token: str,
        refresh_token: str,
        access_expires_at: datetime,
        refresh_expires_at: datetime | None,
        member_urn: str,
    ) -> LinkedInToken:
        row = self.get_linkedin_token()
        if row is None:
            row = LinkedInToken(id=1)
        row.access_token = access_token
        row.refresh_token = refresh_token
        row.access_expires_at = access_expires_at
        row.refresh_expires_at = refresh_expires_at
        row.member_urn = member_urn
        row.updated_at = datetime.now(timezone.utc)
        self.session.add(row)
        self.session.flush()
        return row
