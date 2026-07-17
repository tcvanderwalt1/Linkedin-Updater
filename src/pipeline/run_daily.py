"""Daily pipeline: search → filter → dedupe → store → draft → notify."""

from __future__ import annotations

import logging
import sys
from dataclasses import dataclass
from datetime import date
from typing import Sequence

from src.config import Settings, get_settings
from src.db.engine import session_scope
from src.db.models import Article, PipelineRunStatus
from src.db.repository import Repository, jaccard, normalize_title, title_tokens
from src.llm.client import LLMClient, LLMError
from src.notify.webhook import notify_empty_day, notify_failure
from src.search.exa_client import SearchResult, fetch_industry_news
from src.search.filter import filter_and_rank, scored_to_record

logger = logging.getLogger(__name__)


@dataclass
class PipelineResult:
    status: str
    articles_saved: int = 0
    drafts_created: int = 0
    error_message: str | None = None


class _TitleOnly:
    def __init__(self, title: str) -> None:
        self.title = title
        self.title_norm = normalize_title(title)


def is_duplicate_title(title: str, articles: Sequence[Article | _TitleOnly]) -> bool:
    tokens = title_tokens(title)
    norm = normalize_title(title)
    for article in articles:
        title_norm = getattr(article, "title_norm", "") or normalize_title(article.title)
        if title_norm == norm:
            return True
        if jaccard(tokens, title_tokens(article.title)) >= 0.72:
            return True
    return False


def dedupe_records(
    scored_records: list[dict],
    existing: Sequence[Article],
) -> list[dict]:
    existing_urls = {a.url for a in existing}
    history: list[Article | _TitleOnly] = list(existing)
    kept: list[dict] = []
    for record in scored_records:
        if record["url"] in existing_urls:
            continue
        if is_duplicate_title(record["title"], history):
            continue
        kept.append(record)
        existing_urls.add(record["url"])
        history.append(_TitleOnly(record["title"]))
    return kept


def run_daily(
    *,
    settings: Settings | None = None,
    search_results: list[SearchResult] | None = None,
    llm: LLMClient | None = None,
) -> PipelineResult:
    """
    Execute the daily job.

    `search_results` and `llm` can be injected for tests (no live API credits).
    """
    s = settings or get_settings()
    with session_scope() as session:
        repo = Repository(session)
        run = repo.start_pipeline_run()
        try:
            if search_results is None:
                raw = fetch_industry_news(settings=s)
            else:
                raw = search_results

            ranked = filter_and_rank(raw, top_n=s.top_articles)
            records = [scored_to_record(item) for item in ranked]
            existing = repo.recent_articles(days=s.dedupe_days)
            fresh = dedupe_records(records, existing)

            if not fresh:
                repo.finish_pipeline_run(
                    run,
                    status=PipelineRunStatus.empty.value,
                    articles_saved=0,
                    drafts_created=0,
                    error_message="No articles passed filter/dedupe",
                )
                notify_empty_day(articles_considered=len(raw))
                return PipelineResult(status=PipelineRunStatus.empty.value)

            saved = repo.save_articles(
                fresh[: s.top_articles],
                pipeline_run_id=run.id,
                fetch_date=date.today(),
            )

            client = llm or LLMClient(s)
            drafts_created = 0
            for article in saved[: s.top_drafts]:
                body = client.draft_linkedin_post(
                    title=article.title,
                    snippet=article.snippet,
                    url=article.url,
                    topics=article.topics,
                )
                repo.create_draft(
                    article_id=article.id,
                    body=body,
                    model_name=client.model_name,
                )
                drafts_created += 1

            repo.finish_pipeline_run(
                run,
                status=PipelineRunStatus.success.value,
                articles_saved=len(saved),
                drafts_created=drafts_created,
            )
            return PipelineResult(
                status=PipelineRunStatus.success.value,
                articles_saved=len(saved),
                drafts_created=drafts_created,
            )
        except (LLMError, RuntimeError, Exception) as exc:
            logger.exception("Pipeline failed")
            repo.finish_pipeline_run(
                run,
                status=PipelineRunStatus.failed.value,
                error_message=str(exc)[:2000],
            )
            notify_failure(str(exc), stage="run_daily")
            return PipelineResult(
                status=PipelineRunStatus.failed.value,
                error_message=str(exc),
            )


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    settings = get_settings()
    result = run_daily(settings=settings)
    logger.info(
        "Pipeline finished status=%s articles=%s drafts=%s",
        result.status,
        result.articles_saved,
        result.drafts_created,
    )
    if result.status == PipelineRunStatus.failed.value:
        return 1
    if result.status == PipelineRunStatus.empty.value:
        return 0 if settings.empty_day_exit_zero else 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
