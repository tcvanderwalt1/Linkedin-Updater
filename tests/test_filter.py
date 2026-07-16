"""Unit tests for spam filter and scoring (no network)."""

from __future__ import annotations

import json
from pathlib import Path

from src.search.exa_client import SearchResult
from src.search.filter import detect_spam, filter_and_rank, score_article

FIXTURES = Path(__file__).parent / "fixtures" / "articles.json"


def _load() -> list[dict]:
    return json.loads(FIXTURES.read_text())


def test_spam_crypto_and_paywall_and_bait_dropped():
    rows = _load()
    spam_labels = {"spam_crypto", "spam_paywall", "spam_bait", "spam_hostile_legacy"}
    for row in rows:
        result = SearchResult(url=row["url"], title=row["title"], snippet=row["snippet"])
        is_spam, _ = detect_spam(result)
        if row["label"] in spam_labels:
            assert is_spam, row["label"]
        else:
            assert not is_spam, row["label"]


def test_keep_articles_score_above_threshold():
    rows = [r for r in _load() if r["label"].startswith("keep_")]
    for row in rows:
        scored = score_article(
            SearchResult(url=row["url"], title=row["title"], snippet=row["snippet"])
        )
        assert not scored.is_spam
        assert scored.quality_score >= 1.0
        assert scored.topics


def test_filter_and_rank_returns_top_keep_only():
    results = [
        SearchResult(url=r["url"], title=r["title"], snippet=r["snippet"])
        for r in _load()
    ]
    ranked = filter_and_rank(results, top_n=10)
    assert ranked
    assert all(not s.is_spam for s in ranked)
    assert all(s.topics for s in ranked)
    urls = {s.result.url for s in ranked}
    assert "https://example.com/crypto-moon" not in urls
    assert "https://example.com/replace-simcorp" not in urls
