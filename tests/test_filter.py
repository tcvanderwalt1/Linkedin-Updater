"""Unit tests for spam filter and scoring (no network)."""

from __future__ import annotations

import json
from pathlib import Path

from src.search.exa_client import SearchResult
from src.search.filter import detect_spam, filter_and_rank, score_article

FIXTURES = Path(__file__).parent / "fixtures" / "articles.json"


def _load() -> list[dict]:
    return json.loads(FIXTURES.read_text())


def test_spam_and_low_value_dropped():
    rows = _load()
    spam_labels = {
        "spam_crypto",
        "spam_paywall",
        "spam_bait",
        "spam_hostile_legacy",
        "spam_vendor",
    }
    for row in rows:
        result = SearchResult(url=row["url"], title=row["title"], snippet=row["snippet"])
        is_spam, reason = detect_spam(result)
        if row["label"] in spam_labels:
            assert is_spam, f"{row['label']} should be spam ({reason})"
        else:
            assert not is_spam, f"{row['label']} unexpectedly spam ({reason})"


def test_keep_articles_score_above_high_bar():
    rows = [r for r in _load() if r["label"].startswith("keep_")]
    for row in rows:
        scored = score_article(
            SearchResult(url=row["url"], title=row["title"], snippet=row["snippet"])
        )
        assert not scored.is_spam, row["label"]
        assert scored.quality_score >= 5.0, (row["label"], scored.quality_score)
        assert scored.topics


def test_filter_and_rank_keeps_only_trusted_high_value():
    results = [
        SearchResult(url=r["url"], title=r["title"], snippet=r["snippet"])
        for r in _load()
    ]
    ranked = filter_and_rank(results, top_n=10)
    assert ranked
    assert all(not s.is_spam for s in ranked)
    assert all(s.quality_score >= 5.0 for s in ranked)
    urls = {s.result.url for s in ranked}
    assert any("reuters.com" in u or "finextra.com" in u or "ft.com" in u for u in urls)
    assert "https://vendor.example/product" not in urls
    assert "https://example.com/crypto-moon" not in urls
