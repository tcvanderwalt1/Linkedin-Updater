"""Pipeline orchestration tests with mocked search/LLM/DB session."""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from uuid import uuid4

import pytest

from src.config import Settings
from src.db.models import PipelineRunStatus
import src.pipeline.run_daily as pipeline_mod
from src.search.exa_client import SearchResult


class FakeArticle:
    def __init__(self, **kwargs):
        self.id = kwargs.get("id", uuid4())
        self.url = kwargs["url"]
        self.title = kwargs["title"]
        self.snippet = kwargs.get("snippet", "")
        self.topics = kwargs.get("topics", "ai")
        self.quality_score = kwargs.get("quality_score", 5.0)


class FakeRun:
    def __init__(self):
        self.id = uuid4()
        self.status = "running"


class FakeRepo:
    def __init__(self):
        self.run = FakeRun()
        self.saved = []
        self.drafts = []
        self.finished = None
        self._existing = []

    def start_pipeline_run(self):
        return self.run

    def finish_pipeline_run(self, run, **kwargs):
        self.finished = kwargs
        run.status = kwargs["status"]
        return run

    def recent_articles(self, days=30):
        return self._existing

    def save_articles(self, items, *, pipeline_run_id, fetch_date=None):
        self.saved = [
            FakeArticle(
                url=i["url"],
                title=i["title"],
                snippet=i.get("snippet", ""),
                topics=i.get("topics", ""),
                quality_score=i.get("quality_score", 0),
            )
            for i in items
        ]
        return self.saved

    def create_draft(self, **kwargs):
        self.drafts.append(kwargs)
        return SimpleNamespace(**kwargs)


@pytest.fixture
def settings():
    return Settings(
        DATABASE_URL="postgresql://app:x@localhost/db?sslmode=require",
        TOP_ARTICLES=10,
        TOP_DRAFTS=3,
        DEDUPE_DAYS=30,
        EMPTY_DAY_EXIT_ZERO=True,
        LLM_PROVIDER="grok",
        GROK_API_KEY="x",
    )


def test_run_daily_success(mocker, settings):
    fake_repo = FakeRepo()
    mocker.patch.object(pipeline_mod, "session_scope")
    mocker.patch.object(pipeline_mod, "Repository", return_value=fake_repo)

    results = [
        SearchResult(
            url="https://www.finextra.com/ai-ops",
            title="How generative AI is improving investment operations data quality",
            snippet=(
                "Asset managers use enterprise AI to augment IBOR workflows and "
                "strengthen risk transparency across institutional platforms."
            ),
            source="finextra.com",
        ),
        SearchResult(
            url="https://www.reuters.com/fintech",
            title="Fintech startup raises Series B to modernize wealth management workflows",
            snippet=(
                "Institutional fintech improves compliance workflows for wealth managers "
                "alongside existing core systems and venture funding news."
            ),
            source="reuters.com",
        ),
        SearchResult(
            url="https://example.com/prop",
            title="Proptech tools help commercial real estate investors improve portfolio transparency",
            snippet=(
                "Property investment teams adopt analytics that complement existing "
                "asset management operations and reporting."
            ),
            source="example.com",
        ),
    ]

    llm = mocker.Mock()
    llm.model_name = "grok-2-latest"
    llm.draft_linkedin_post.return_value = "Positive ops post\n\n#AssetManagement #AI #Fintech"

    result = pipeline_mod.run_daily(settings=settings, search_results=results, llm=llm)
    assert result.status == PipelineRunStatus.success.value
    assert result.articles_saved == 3
    assert result.drafts_created == 3
    assert llm.draft_linkedin_post.call_count == 3
    assert fake_repo.finished["status"] == "success"


def test_run_daily_empty_notifies(mocker, settings):
    fake_repo = FakeRepo()
    mocker.patch.object(pipeline_mod, "session_scope")
    mocker.patch.object(pipeline_mod, "Repository", return_value=fake_repo)
    notify = mocker.patch.object(pipeline_mod, "notify_empty_day", return_value=True)

    spam = [
        SearchResult(
            url="https://example.com/crypto",
            title="Bitcoin memecoin airdrop to the moon guaranteed 100x",
            snippet="shitcoin degen get rich like and share",
        )
    ]
    result = pipeline_mod.run_daily(settings=settings, search_results=spam, llm=mocker.Mock())
    assert result.status == PipelineRunStatus.empty.value
    notify.assert_called_once()


def test_run_daily_failure_notifies(mocker, settings):
    fake_repo = FakeRepo()
    mocker.patch.object(pipeline_mod, "session_scope")
    mocker.patch.object(pipeline_mod, "Repository", return_value=fake_repo)
    mocker.patch.object(
        pipeline_mod,
        "filter_and_rank",
        side_effect=RuntimeError("search exploded"),
    )
    notify = mocker.patch.object(pipeline_mod, "notify_failure", return_value=True)

    result = pipeline_mod.run_daily(
        settings=settings,
        search_results=[SearchResult(url="https://x", title="t", snippet="s")],
        llm=mocker.Mock(),
    )
    assert result.status == PipelineRunStatus.failed.value
    notify.assert_called_once()


def test_main_exit_codes(mocker, settings):
    mocker.patch.object(pipeline_mod, "get_settings", return_value=settings)
    mocker.patch.object(
        pipeline_mod,
        "run_daily",
        return_value=pipeline_mod.PipelineResult(status="failed", error_message="x"),
    )
    assert pipeline_mod.main() == 1

    mocker.patch.object(
        pipeline_mod,
        "run_daily",
        return_value=pipeline_mod.PipelineResult(status="empty"),
    )
    assert pipeline_mod.main() == 0
