"""LinkedIn OAuth 2.0 helpers (authorization code + refresh)."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlencode

import requests

from src.config import Settings, get_settings

logger = logging.getLogger(__name__)

AUTH_URL = "https://www.linkedin.com/oauth/v2/authorization"
TOKEN_URL = "https://www.linkedin.com/oauth/v2/accessToken"
USERINFO_URL = "https://api.linkedin.com/v2/userinfo"
# Scopes for member profile + creating posts on behalf of the member
DEFAULT_SCOPES = "openid profile w_member_social"


class LinkedInOAuthError(RuntimeError):
    pass


def build_authorize_url(
    settings: Settings | None = None,
    *,
    state: str = "linkedin-updater",
    scopes: str = DEFAULT_SCOPES,
) -> str:
    s = settings or get_settings()
    if not s.linkedin_client_id:
        raise LinkedInOAuthError("LINKEDIN_CLIENT_ID is required")
    params = {
        "response_type": "code",
        "client_id": s.linkedin_client_id,
        "redirect_uri": s.linkedin_redirect_uri,
        "state": state,
        "scope": scopes,
    }
    return f"{AUTH_URL}?{urlencode(params)}"


def exchange_code_for_tokens(
    code: str,
    settings: Settings | None = None,
    *,
    timeout: float = 30.0,
) -> dict[str, Any]:
    s = settings or get_settings()
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": s.linkedin_redirect_uri,
        "client_id": s.linkedin_client_id,
        "client_secret": s.linkedin_client_secret,
    }
    response = requests.post(
        TOKEN_URL,
        data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=timeout,
    )
    if response.status_code >= 400:
        raise LinkedInOAuthError(
            f"Token exchange failed: {response.status_code} {response.text[:300]}"
        )
    return response.json()


def refresh_access_token(
    refresh_token: str,
    settings: Settings | None = None,
    *,
    timeout: float = 30.0,
) -> dict[str, Any]:
    s = settings or get_settings()
    data = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "client_id": s.linkedin_client_id,
        "client_secret": s.linkedin_client_secret,
    }
    response = requests.post(
        TOKEN_URL,
        data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=timeout,
    )
    if response.status_code >= 400:
        raise LinkedInOAuthError(
            f"Token refresh failed: {response.status_code} {response.text[:300]}"
        )
    return response.json()


def fetch_member_urn(access_token: str, *, timeout: float = 20.0) -> str:
    """Resolve the authenticated member URN via OpenID userinfo (sub)."""
    response = requests.get(
        USERINFO_URL,
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=timeout,
    )
    if response.status_code >= 400:
        raise LinkedInOAuthError(
            f"userinfo failed: {response.status_code} {response.text[:300]}"
        )
    data = response.json()
    sub = data.get("sub")
    if not sub:
        raise LinkedInOAuthError(f"userinfo missing sub: {data}")
    if str(sub).startswith("urn:"):
        return str(sub)
    return f"urn:li:person:{sub}"


def token_expiry_from_response(
    token_payload: dict[str, Any],
    *,
    now: datetime | None = None,
) -> tuple[datetime, datetime | None]:
    now = now or datetime.now(timezone.utc)
    expires_in = int(token_payload.get("expires_in") or 3600)
    access_expires = now + timedelta(seconds=expires_in)
    refresh_expires = None
    if "refresh_token_expires_in" in token_payload:
        refresh_expires = now + timedelta(
            seconds=int(token_payload["refresh_token_expires_in"])
        )
    else:
        # LinkedIn marketing/partner refresh tokens are often ~365 days
        refresh_expires = now + timedelta(days=365)
    return access_expires, refresh_expires


def access_token_expired(expires_at: datetime, *, skew_seconds: int = 60) -> bool:
    now = datetime.now(timezone.utc)
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    return now >= (expires_at - timedelta(seconds=skew_seconds))
