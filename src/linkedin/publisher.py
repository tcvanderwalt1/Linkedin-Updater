"""LinkedIn REST publishing (UGC Posts API)."""

from __future__ import annotations

import logging
from typing import Any

import requests

from src.db.models import LinkedInToken
from src.db.repository import Repository
from src.linkedin.oauth import (
    LinkedInOAuthError,
    access_token_expired,
    refresh_access_token,
    token_expiry_from_response,
)

logger = logging.getLogger(__name__)

UGC_POSTS_URL = "https://api.linkedin.com/v2/ugcPosts"


class LinkedInPublishError(RuntimeError):
    pass


def ensure_fresh_access_token(repo: Repository, token: LinkedInToken) -> LinkedInToken:
    """Refresh and persist access token when expired."""
    if not access_token_expired(token.access_expires_at):
        return token
    payload = refresh_access_token(token.refresh_token)
    access_expires, refresh_expires = token_expiry_from_response(payload)
    new_refresh = payload.get("refresh_token") or token.refresh_token
    return repo.upsert_linkedin_token(
        access_token=payload["access_token"],
        refresh_token=new_refresh,
        access_expires_at=access_expires,
        refresh_expires_at=refresh_expires or token.refresh_expires_at,
        member_urn=token.member_urn,
    )


def build_ugc_payload(*, member_urn: str, text: str) -> dict[str, Any]:
    return {
        "author": member_urn,
        "lifecycleState": "PUBLISHED",
        "specificContent": {
            "com.linkedin.ugc.ShareContent": {
                "shareCommentary": {"text": text},
                "shareMediaCategory": "NONE",
            }
        },
        "visibility": {"com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"},
    }


def publish_text_post(
    *,
    access_token: str,
    member_urn: str,
    text: str,
    timeout: float = 30.0,
) -> str:
    """Create a LinkedIn UGC post; return the post URN/id."""
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
        "X-Restli-Protocol-Version": "2.0.0",
    }
    payload = build_ugc_payload(member_urn=member_urn, text=text)
    response = requests.post(
        UGC_POSTS_URL, headers=headers, json=payload, timeout=timeout
    )
    if response.status_code >= 400:
        raise LinkedInPublishError(
            f"Publish failed: {response.status_code} {response.text[:500]}"
        )
    # Rest.li returns id in header or body
    post_id = response.headers.get("x-restli-id") or response.headers.get("X-RestLi-Id")
    if not post_id:
        try:
            post_id = response.json().get("id")
        except Exception:
            post_id = None
    if not post_id:
        raise LinkedInPublishError(f"Publish succeeded but no id: {response.text[:300]}")
    return str(post_id)


def publish_draft(repo: Repository, draft_id, body: str | None = None) -> str:
    """Refresh token if needed and publish draft body to LinkedIn."""
    token = repo.get_linkedin_token()
    if token is None:
        raise LinkedInOAuthError("LinkedIn is not connected. Complete OAuth first.")
    token = ensure_fresh_access_token(repo, token)
    draft = repo.get_draft(draft_id)
    if draft is None:
        raise LinkedInPublishError(f"Draft not found: {draft_id}")
    text = body if body is not None else draft.body
    urn = publish_text_post(
        access_token=token.access_token,
        member_urn=token.member_urn,
        text=text,
    )
    repo.set_draft_status(draft_id, "published", linkedin_post_urn=urn)
    return urn
