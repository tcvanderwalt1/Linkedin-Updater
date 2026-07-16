"""Failure / empty-run webhook notifier (Slack or Discord)."""

from __future__ import annotations

import logging
from typing import Any

import requests

from src.config import get_settings

logger = logging.getLogger(__name__)


def send_webhook(
    message: str,
    *,
    webhook_url: str | None = None,
    title: str = "LinkedIn Updater",
    severity: str = "error",
    extra: dict[str, Any] | None = None,
    timeout: float = 10.0,
) -> bool:
    """
    Post a simple notification to a Slack or Discord incoming webhook.

    Returns True if a request was attempted and succeeded (2xx), False if skipped
    or the request failed. Never raises — notification must not crash the pipeline.
    """
    url = (webhook_url if webhook_url is not None else get_settings().webhook_url).strip()
    if not url:
        logger.warning("WEBHOOK_URL not configured; skip notify: %s", message)
        return False

    lines = [f"**{title}** [{severity}]", message]
    if extra:
        for key, value in extra.items():
            lines.append(f"- {key}: {value}")
    content = "\n".join(lines)

    # Discord expects {"content": ...}; Slack incoming webhooks accept {"text": ...}
    # Send both keys so either provider works with one secret.
    payload = {"content": content, "text": content}

    try:
        response = requests.post(url, json=payload, timeout=timeout)
        if response.status_code >= 400:
            logger.error(
                "Webhook failed status=%s body=%s",
                response.status_code,
                response.text[:300],
            )
            return False
        return True
    except requests.RequestException as exc:
        logger.error("Webhook request error: %s", exc)
        return False


def notify_empty_day(*, articles_considered: int = 0) -> bool:
    return send_webhook(
        "Daily pipeline found zero articles after spam/SimCorp-safe filter. "
        "Skipping drafts for today.",
        title="LinkedIn Updater — empty day",
        severity="warning",
        extra={"articles_considered": articles_considered},
    )


def notify_failure(error: str, *, stage: str = "pipeline") -> bool:
    return send_webhook(
        f"Daily pipeline failed at stage `{stage}`.",
        title="LinkedIn Updater — failure",
        severity="error",
        extra={"error": error[:1500]},
    )
