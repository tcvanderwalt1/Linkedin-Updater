"""Config guards — SQLite forbidden, DATABASE_URL required."""

from __future__ import annotations

import pytest

from src.config import Settings, clear_settings_cache, require_database_url


def test_require_database_url_rejects_sqlite():
    clear_settings_cache()
    settings = Settings(DATABASE_URL="sqlite:///tmp.db")
    with pytest.raises(RuntimeError, match="SQLite"):
        require_database_url(settings)


def test_require_database_url_ok():
    settings = Settings(
        DATABASE_URL="postgresql://app:x@ep-x-pooler.neon.tech/neondb?sslmode=require"
    )
    assert "postgresql" in require_database_url(settings)
