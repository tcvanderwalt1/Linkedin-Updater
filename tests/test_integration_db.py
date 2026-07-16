"""Optional Postgres integration tests (skipped without TEST_DATABASE_URL)."""

from __future__ import annotations

import os

import pytest

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def database_url():
    url = os.environ.get("TEST_DATABASE_URL", "").strip()
    if not url:
        pytest.skip("TEST_DATABASE_URL not set")
    if "sqlite" in url.lower():
        pytest.fail("SQLite is forbidden for integration tests")
    return url


def test_ping_and_repository_roundtrip(database_url):
    from datetime import date

    from src.db.engine import get_engine, reset_engine, session_scope
    from src.db.models import Base
    from src.db.repository import Repository

    reset_engine()
    engine = get_engine(database_url, force_new=True)
    Base.metadata.create_all(engine)
    with session_scope(database_url) as session:
        repo = Repository(session)
        run = repo.start_pipeline_run()
        saved = repo.save_articles(
            [
                {
                    "url": "https://example.com/integration-unique",
                    "title": "Integration test article for asset management AI",
                    "snippet": "Institutional investment operations data quality",
                    "source": "example.com",
                    "topics": "ai,asset_management",
                    "quality_score": 4.5,
                }
            ],
            pipeline_run_id=run.id,
            fetch_date=date.today(),
        )
        assert len(saved) == 1
        draft = repo.create_draft(
            article_id=saved[0].id,
            body="Test post\n\n#AssetManagement #AI #Fintech",
            model_name="test",
        )
        assert draft.status == "pending"
        repo.finish_pipeline_run(
            run, status="success", articles_saved=1, drafts_created=1
        )
