"""Application configuration loaded from environment / Streamlit secrets."""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Any

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def _streamlit_secrets() -> dict[str, Any]:
    """Best-effort load of Streamlit secrets (available only in Streamlit runtime)."""
    try:
        import streamlit as st

        return dict(st.secrets)
    except Exception:
        return {}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    database_url: str = Field(default="", alias="DATABASE_URL")
    test_database_url: str = Field(default="", alias="TEST_DATABASE_URL")

    search_provider: str = Field(default="exa", alias="SEARCH_PROVIDER")
    exa_api_key: str = Field(default="", alias="EXA_API_KEY")
    tavily_api_key: str = Field(default="", alias="TAVILY_API_KEY")

    llm_provider: str = Field(default="grok", alias="LLM_PROVIDER")
    grok_api_key: str = Field(default="", alias="GROK_API_KEY")
    grok_api_base: str = Field(default="https://api.x.ai/v1", alias="GROK_API_BASE")
    grok_model: str = Field(default="grok-2-latest", alias="GROK_MODEL")
    anthropic_api_key: str = Field(default="", alias="ANTHROPIC_API_KEY")
    claude_model: str = Field(default="claude-sonnet-4-20250514", alias="CLAUDE_MODEL")

    linkedin_client_id: str = Field(default="", alias="LINKEDIN_CLIENT_ID")
    linkedin_client_secret: str = Field(default="", alias="LINKEDIN_CLIENT_SECRET")
    linkedin_redirect_uri: str = Field(
        default="http://localhost:8501/",
        alias="LINKEDIN_REDIRECT_URI",
    )

    webhook_url: str = Field(default="", alias="WEBHOOK_URL")
    app_password: str = Field(default="", alias="APP_PASSWORD")

    empty_day_exit_zero: bool = Field(default=True, alias="EMPTY_DAY_EXIT_ZERO")
    top_articles: int = Field(default=10, alias="TOP_ARTICLES")
    top_drafts: int = Field(default=3, alias="TOP_DRAFTS")
    dedupe_days: int = Field(default=30, alias="DEDUPE_DAYS")


def _overlay_streamlit(settings: Settings) -> Settings:
    secrets = _streamlit_secrets()
    if not secrets:
        return settings
    data = settings.model_dump()
    # Map Streamlit secret keys (UPPER) onto Settings fields
    mapping = {
        "DATABASE_URL": "database_url",
        "TEST_DATABASE_URL": "test_database_url",
        "SEARCH_PROVIDER": "search_provider",
        "EXA_API_KEY": "exa_api_key",
        "TAVILY_API_KEY": "tavily_api_key",
        "LLM_PROVIDER": "llm_provider",
        "GROK_API_KEY": "grok_api_key",
        "GROK_API_BASE": "grok_api_base",
        "GROK_MODEL": "grok_model",
        "ANTHROPIC_API_KEY": "anthropic_api_key",
        "CLAUDE_MODEL": "claude_model",
        "LINKEDIN_CLIENT_ID": "linkedin_client_id",
        "LINKEDIN_CLIENT_SECRET": "linkedin_client_secret",
        "LINKEDIN_REDIRECT_URI": "linkedin_redirect_uri",
        "WEBHOOK_URL": "webhook_url",
        "APP_PASSWORD": "app_password",
        "EMPTY_DAY_EXIT_ZERO": "empty_day_exit_zero",
        "TOP_ARTICLES": "top_articles",
        "TOP_DRAFTS": "top_drafts",
        "DEDUPE_DAYS": "dedupe_days",
    }
    for secret_key, field_name in mapping.items():
        if secret_key in secrets and secrets[secret_key] not in (None, ""):
            data[field_name] = secrets[secret_key]
    return Settings(**data)


@lru_cache
def get_settings() -> Settings:
    # Allow dotenv without requiring Streamlit
    from dotenv import load_dotenv

    load_dotenv()
    base = Settings()
    return _overlay_streamlit(base)


def clear_settings_cache() -> None:
    get_settings.cache_clear()


def require_database_url(settings: Settings | None = None) -> str:
    s = settings or get_settings()
    url = (s.database_url or os.environ.get("DATABASE_URL", "")).strip()
    if not url:
        raise RuntimeError(
            "DATABASE_URL is required. Use Neon Postgres with sslmode=require "
            "and preferably the -pooler host."
        )
    if "sqlite" in url.lower():
        raise RuntimeError("SQLite is forbidden. Use Neon Serverless PostgreSQL.")
    return url
