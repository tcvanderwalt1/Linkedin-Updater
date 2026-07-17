"""Spam filter, topic scoring, and high-value article ranking."""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urlparse

from src.search.exa_client import SearchResult

TOPIC_KEYWORDS: dict[str, tuple[str, ...]] = {
    "asset_management": (
        "asset management",
        "asset manager",
        "asset managers",
        "portfolio",
        "ibor",
        "abor",
        "investment operations",
        "fund accounting",
        "aum",
        "pensions",
        "wealth management",
    ),
    "fintech": (
        "fintech",
        "payments",
        "banking",
        "wealthtech",
        "neobank",
        "capital markets",
        "digital banking",
    ),
    "property": (
        "real estate",
        "property",
        "reit",
        "commercial property",
        "commercial real estate",
        "proptech",
    ),
    "ai": (
        "artificial intelligence",
        "machine learning",
        "generative ai",
        "llm",
        " ai ",
        "ai-",
    ),
    "vc": (
        "venture capital",
        "series a",
        "series b",
        "funding round",
        "raises $",
        "vc ",
    ),
    "startups": ("startup", "start-up", "founder", "scale-up"),
}

# Recognizable outlets most professionals already know / trust.
TRUSTED_HOSTS: tuple[str, ...] = (
    "ft.com",
    "reuters.com",
    "bloomberg.com",
    "wsj.com",
    "economist.com",
    "cnbc.com",
    "bbc.com",
    "bbc.co.uk",
    "nytimes.com",
    "forbes.com",
    "businessinsider.com",
    "finextra.com",
    "waterstechnology.com",
    "ignites.com",
    "institutionalinvestor.com",
    "pionline.com",
    "ipe.com",
    "funds-europe.com",
    "techcrunch.com",
    "theinformation.com",
    "semafor.com",
    "axios.com",
)

SPAM_PATTERNS = [
    r"\b(bitcoin|btc|ethereum|crypto\s*shill|memecoin|nft\s*drop|to the moon)\b",
    r"\b(guaranteed returns|100x|get rich)\b",
    r"(subscribe to (read|continue)|paywall|members[- ]only)",
    r"(you won.?t believe|clickbait|like and share|comment below)",
    r"\b(airdrop|shitcoin|degen)\b",
]

# Vendor landing pages / thin marketing — not worth a LinkedIn post.
LOW_VALUE_PATTERNS = [
    r"\b(book a demo|request a demo|schedule a (demo|call)|start (your )?free trial)\b",
    r"\b(talk to sales|contact sales|get a quote|pricing plans)\b",
    r"\b(our (ai )?platform|the ai platform for)\b",
    r"\b(transform weeks into minutes|10x your|supercharge your)\b",
    r"\b(appointed as .+ service provider)\b",
]

HOSTILE_LEGACY_PATTERNS = [
    r"replace (your )?(simcorp|ibor|abor|oms)",
    r"rip (and )?replace.*(simcorp|legacy)",
    r"kill (your )?legacy (system|platform|ibor)",
]

SUBSTANCE_BONUS = (
    "regulators",
    "regulation",
    "market",
    "investors",
    "pension",
    "bank",
    "operations",
    "risk",
    "data quality",
    "workflow",
    "compliance",
    "transparency",
    "institutional",
    "enterprise",
    "funding",
    "acquisition",
    "earnings",
    "strategy",
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


def is_trusted_host(host: str) -> bool:
    host = (host or "").lower().removeprefix("www.")
    return any(host == t or host.endswith("." + t) for t in TRUSTED_HOSTS)


def looks_like_article_url(url: str) -> bool:
    """Prefer real article paths over marketing homepages."""
    try:
        parsed = urlparse(url)
    except Exception:
        return False
    path = (parsed.path or "").rstrip("/")
    if not path or path == "":
        return False
    # Single-segment brand homepages / product roots are usually weak.
    parts = [p for p in path.split("/") if p]
    if len(parts) <= 1 and not re.search(r"\d{4}", path):
        return False
    return True


def detect_spam(result: SearchResult) -> tuple[bool, str | None]:
    blob = _text_blob(result)
    for pattern in SPAM_PATTERNS:
        if re.search(pattern, blob, flags=re.IGNORECASE):
            return True, f"spam_pattern:{pattern}"
    for pattern in HOSTILE_LEGACY_PATTERNS:
        if re.search(pattern, blob, flags=re.IGNORECASE):
            return True, f"hostile_legacy:{pattern}"
    for pattern in LOW_VALUE_PATTERNS:
        if re.search(pattern, blob, flags=re.IGNORECASE):
            return True, f"low_value:{pattern}"
    # Engagement bait: very short teaser + exclaim-heavy title
    if blob.count("!") >= 3 and len(result.snippet or "") < 40:
        return True, "engagement_bait"
    # Product-style "Brand | Tagline" titles with thin copy
    if "|" in (result.title or "") and len(result.snippet or "") < 120:
        return True, "product_tagline_title"
    if not looks_like_article_url(result.url):
        return True, "non_article_url"
    if len(result.snippet or "") < 100:
        return True, "snippet_too_thin"
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
    blob = _text_blob(result)
    host = result.host()
    trusted = is_trusted_host(host)

    # Recognizable outlets are the main quality signal.
    if trusted:
        score += 5.0
    else:
        # Unknown blogs/vendor sites rarely make the cut.
        score -= 2.0

    score += min(len(topics), 3) * 1.2
    for token in SUBSTANCE_BONUS:
        if token in blob:
            score += 0.5

    snippet_len = len(result.snippet or "")
    if snippet_len >= 280:
        score += 1.5
    elif snippet_len >= 160:
        score += 1.0

    # News-like verbs / framing people can relate to
    if re.search(
        r"\b(raises|raised|acquires|acquired|launches|warns|plans|cuts|grows|surges|falls)\b",
        blob,
    ):
        score += 1.0

    if not topics:
        score *= 0.2
    # Hard preference: untrusted hosts need an exceptional score to survive min_score
    if not trusted:
        score *= 0.45

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
    min_score: float = 5.0,
) -> list[ScoredArticle]:
    """Keep only high-value, preferably well-known-outlet articles."""
    scored = [score_article(r) for r in results]
    keep = [
        s
        for s in scored
        if not s.is_spam and s.quality_score >= min_score and s.topics
    ]
    # Prefer trusted hosts when scores are close
    keep.sort(
        key=lambda s: (
            s.quality_score,
            1 if is_trusted_host(s.result.host()) else 0,
        ),
        reverse=True,
    )
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
