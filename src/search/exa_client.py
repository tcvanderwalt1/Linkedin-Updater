"""Article dataclasses and search provider clients (Exa / Tavily)."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Protocol
from urllib.parse import urlparse

import requests

from src.config import Settings, get_settings

logger = logging.getLogger(__name__)

# Bias toward mainstream / industry news people recognize — not vendor pages.
FOCUS_QUERIES = [
    "asset managers pensions wealth management news analysis",
    "fintech banking wealth management regulation funding news",
    "commercial real estate investment market news",
    "artificial intelligence asset management banks operations news",
    "venture capital fintech startup funding round news",
    "investment operations risk data quality institutional news",
]

# Prefer recognizable outlets at search time (Exa includeDomains).
PREFERRED_DOMAINS = [
    "ft.com",
    "reuters.com",
    "bloomberg.com",
    "wsj.com",
    "economist.com",
    "cnbc.com",
    "bbc.com",
    "nytimes.com",
    "forbes.com",
    "businessinsider.com",
    "finextra.com",
    "waterstechnology.com",
    "ignites.com",
    "institutionalinvestor.com",
    "pionline.com",
    "ipe.com",
    "techcrunch.com",
    "axios.com",
]


@dataclass
class SearchResult:
    url: str
    title: str
    snippet: str = ""
    source: str = ""
    published_at: datetime | None = None
    raw: dict[str, Any] = field(default_factory=dict)

    def host(self) -> str:
        try:
            return urlparse(self.url).netloc.lower()
        except Exception:
            return ""


class SearchClient(Protocol):
    def search(self, query: str, *, num_results: int = 8) -> list[SearchResult]: ...


class ExaClient:
    """Exa.ai neural search client."""

    def __init__(self, api_key: str, *, timeout: float = 30.0) -> None:
        self.api_key = api_key
        self.timeout = timeout
        self.base_url = "https://api.exa.ai"

    def search(self, query: str, *, num_results: int = 8) -> list[SearchResult]:
        if not self.api_key:
            raise RuntimeError("EXA_API_KEY is required for Exa search")
        headers = {
            "x-api-key": self.api_key,
            "Content-Type": "application/json",
        }
        # Prefer recent news from known outlets.
        start = (datetime.now(timezone.utc) - timedelta(days=14)).strftime(
            "%Y-%m-%dT00:00:00.000Z"
        )
        payload: dict[str, Any] = {
            "query": query,
            "type": "auto",
            "numResults": num_results,
            "category": "news",
            "includeDomains": PREFERRED_DOMAINS,
            "startPublishedDate": start,
            "contents": {"text": {"maxCharacters": 800}},
            "useAutoprompt": True,
        }
        response = requests.post(
            f"{self.base_url}/search",
            headers=headers,
            json=payload,
            timeout=self.timeout,
        )
        # If Exa rejects category/domains combo, retry with domains only.
        if response.status_code >= 400:
            logger.warning(
                "Exa search with news category failed (%s); retrying without category",
                response.status_code,
            )
            payload.pop("category", None)
            response = requests.post(
                f"{self.base_url}/search",
                headers=headers,
                json=payload,
                timeout=self.timeout,
            )
        response.raise_for_status()
        data = response.json()
        results: list[SearchResult] = []
        for item in data.get("results", []):
            text = ""
            if isinstance(item.get("text"), str):
                text = item["text"]
            published = None
            if item.get("publishedDate"):
                try:
                    published = datetime.fromisoformat(
                        str(item["publishedDate"]).replace("Z", "+00:00")
                    )
                except ValueError:
                    published = None
            results.append(
                SearchResult(
                    url=item.get("url") or "",
                    title=item.get("title") or item.get("url") or "Untitled",
                    snippet=text[:800],
                    source=urlparse(item.get("url") or "").netloc,
                    published_at=published,
                    raw=item,
                )
            )
        return [r for r in results if r.url]


class TavilyClient:
    """Tavily search client (fallback)."""

    def __init__(self, api_key: str, *, timeout: float = 30.0) -> None:
        self.api_key = api_key
        self.timeout = timeout
        self.base_url = "https://api.tavily.com"

    def search(self, query: str, *, num_results: int = 8) -> list[SearchResult]:
        if not self.api_key:
            raise RuntimeError("TAVILY_API_KEY is required for Tavily search")
        payload = {
            "api_key": self.api_key,
            "query": query,
            "search_depth": "advanced",
            "topic": "news",
            "include_answer": False,
            "max_results": num_results,
            "include_domains": PREFERRED_DOMAINS,
        }
        response = requests.post(
            f"{self.base_url}/search",
            json=payload,
            timeout=self.timeout,
        )
        response.raise_for_status()
        data = response.json()
        results: list[SearchResult] = []
        for item in data.get("results", []):
            results.append(
                SearchResult(
                    url=item.get("url") or "",
                    title=item.get("title") or "Untitled",
                    snippet=(item.get("content") or "")[:800],
                    source=urlparse(item.get("url") or "").netloc,
                    raw=item,
                )
            )
        return [r for r in results if r.url]


def build_search_client(settings: Settings | None = None) -> SearchClient:
    s = settings or get_settings()
    provider = (s.search_provider or "exa").lower().strip()
    if provider == "tavily":
        return TavilyClient(s.tavily_api_key)
    return ExaClient(s.exa_api_key)


def fetch_industry_news(
    client: SearchClient | None = None,
    *,
    settings: Settings | None = None,
    per_query: int = 8,
) -> list[SearchResult]:
    """Run focus queries and return de-duplicated URL list (pre-filter)."""
    s = settings or get_settings()
    search_client = client or build_search_client(s)
    seen: set[str] = set()
    combined: list[SearchResult] = []
    errors: list[str] = []

    for query in FOCUS_QUERIES:
        try:
            batch = search_client.search(query, num_results=per_query)
        except requests.RequestException as exc:
            logger.exception("Search failed for query=%s", query)
            errors.append(str(exc))
            continue
        for item in batch:
            if item.url in seen:
                continue
            seen.add(item.url)
            combined.append(item)

    if not combined and errors:
        raise RuntimeError(f"All search queries failed: {errors[0]}")
    return combined
