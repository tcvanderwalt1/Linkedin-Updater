"""Spam filter, topic scoring, and thematic helpers."""

from __future__ import annotations

import re
from dataclasses import dataclass

from src.search.exa_client import SearchResult

TOPIC_KEYWORDS: dict[str, tuple[str, ...]] = {
    "asset_management": (
        "asset management",
        "asset manager",
        "portfolio",
        "ibor",
        "abor",
        "investment operations",
        "fund accounting",
        "aum",
    ),
    "fintech": (
        "fintech",
        "payments",
        "banking",
        "wealthtech",
        "neobank",
        "capital markets",
    ),
    "property": (
        "real estate",
        "property",
        "reit",
        "commercial property",
        "proptech",
    ),
    "ai": (
        "artificial intelligence",
        " machine learning",
        "generative ai",
        "llm",
        "ai ",
        " ai",
    ),
    "vc": ("venture capital", "series a", "series b", "funding round", "vc "),
    "startups": ("startup", "start-up", "founder", "scale-up"),
}

SPAM_PATTERNS = [
    r"\b(bitcoin|btc|ethereum|crypto\s*shill|memecoin|nft\s*drop|to the moon)\b",
    r"\b(guaranteed returns|100x|get rich)\b",
    r"(subscribe to (read|continue)|paywall|members[- ]only)",
    r"(you won.?t believe|clickbait|like and share|comment below)",
    r"\b(airdrop|shitcoin|degen)\b",
]

# Soft anti-patterns: replacement framing vs legacy AM platforms
HOSTILE_LEGACY_PATTERNS = [
    r"replace (your )?(simcorp|ibor|abor|oms)",
    r"rip (and )?replace.*(simcorp|legacy)",
    r"kill (your )?legacy (system|platform|ibor)",
]

SUBSTANCE_BONUS = (
    "operations",
    "risk",
    "data quality",
    "workflow",
    "compliance",
    "transparency",
    "institutional",
    "enterprise",
    "investment book",
    "accounting book",
)


@dataclass
class ScoredArticle:
    result: SearchResult
    quality_score: float
    topics: list[str]
    is_spam: bool
    spam_reason: str | None = None


def _text_blob(result: SearchResult) -> str:
    return f"{result.title} {result.snippet}".lower()


def detect_spam(result: SearchResult) -> tuple[bool, str | None]:
    blob = _text_blob(result)
    for pattern in SPAM_PATTERNS:
        if re.search(pattern, blob, flags=re.IGNORECASE):
            return True, f"spam_pattern:{pattern}"
    for pattern in HOSTILE_LEGACY_PATTERNS:
        if re.search(pattern, blob, flags=re.IGNORECASE):
            return True, f"hostile_legacy:{pattern}"
    # Engagement bait: very short teaser + exclaim-heavy title
    if blob.count("!") >= 3 and len(result.snippet or "") < 40:
        return True, "engagement_bait"
    return False, None


def detect_topics(result: SearchResult) -> list[str]:
    blob = _text_blob(result)
    found: list[str] = []
    for topic, keywords in TOPIC_KEYWORDS.items():
        if any(k in blob for k in keywords):
            found.append(topic)
    return found


def score_article(result: SearchResult) -> ScoredArticle:
    is_spam, reason = detect_spam(result)
    topics = detect_topics(result)
    if is_spam:
        return ScoredArticle(
            result=result,
            quality_score=0.0,
            topics=topics,
            is_spam=True,
            spam_reason=reason,
        )

    score = 0.0
    # Topic coverage
    score += min(len(topics), 3) * 1.5
    blob = _text_blob(result)
    for token in SUBSTANCE_BONUS:
        if token in blob:
            score += 0.6
    # Prefer longer substantive snippets
    snippet_len = len(result.snippet or "")
    if snippet_len >= 200:
        score += 1.0
    elif snippet_len >= 80:
        score += 0.5
    # Slight preference for known institutional-ish domains
    host = result.host()
    if any(
        h in host
        for h in (
            "ft.com",
            "reuters.com",
            "bloomberg.com",
            "wsj.com",
            "finextra.com",
            "waterstechnology",
            "ignites.com",
            "institutionalinvestor",
        )
    ):
        score += 1.2

    # Must hit at least one focus topic
    if not topics:
        score *= 0.25

    return ScoredArticle(
        result=result,
        quality_score=round(score, 3),
        topics=topics,
        is_spam=False,
    )


def filter_and_rank(
    results: list[SearchResult],
    *,
    top_n: int = 10,
    min_score: float = 1.0,
) -> list[ScoredArticle]:
    scored = [score_article(r) for r in results]
    keep = [s for s in scored if not s.is_spam and s.quality_score >= min_score and s.topics]
    keep.sort(key=lambda s: s.quality_score, reverse=True)
    return keep[:top_n]


def scored_to_record(scored: ScoredArticle) -> dict:
    r = scored.result
    return {
        "url": r.url,
        "title": r.title,
        "snippet": r.snippet,
        "source": r.source or r.host(),
        "topics": ",".join(scored.topics),
        "quality_score": scored.quality_score,
        "is_spam": scored.is_spam,
        "published_at": r.published_at,
    }
