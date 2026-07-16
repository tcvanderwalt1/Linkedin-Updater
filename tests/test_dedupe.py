"""Dedupe helpers without a live database."""

from __future__ import annotations

from types import SimpleNamespace

from src.db.repository import jaccard, normalize_title, title_tokens
from src.pipeline.run_daily import dedupe_records, is_duplicate_title


def test_normalize_and_jaccard():
    assert normalize_title("Hello, World!!!") == "hello world"
    a = title_tokens("Asset management AI workflows")
    b = title_tokens("Asset management AI workflows tools")
    assert jaccard(a, b) > 0.5


def test_thematic_duplicate_detection():
    existing = [
        SimpleNamespace(
            title="Generative AI improves investment operations data quality",
            title_norm=normalize_title(
                "Generative AI improves investment operations data quality"
            ),
        )
    ]
    assert is_duplicate_title(
        "Generative AI improves investment operations data quality for managers",
        existing,
    )


def test_dedupe_records_drops_url_and_theme():
    existing = [
        SimpleNamespace(
            url="https://example.com/a",
            title="Fintech startup raises Series B for wealth workflows",
            title_norm=normalize_title(
                "Fintech startup raises Series B for wealth workflows"
            ),
        )
    ]
    records = [
        {
            "url": "https://example.com/a",
            "title": "Different title same url",
        },
        {
            "url": "https://example.com/b",
            "title": "Fintech startup raises Series B for wealth workflows today",
        },
        {
            "url": "https://example.com/c",
            "title": "Commercial real estate proptech portfolio transparency",
        },
    ]
    kept = dedupe_records(records, existing)  # type: ignore[arg-type]
    assert len(kept) == 1
    assert kept[0]["url"] == "https://example.com/c"
