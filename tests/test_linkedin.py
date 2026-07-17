"""LinkedIn OAuth refresh + publish payload tests (mocked)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from src.linkedin.oauth import access_token_expired, build_authorize_url, token_expiry_from_response
from src.linkedin.publisher import build_ugc_payload, ensure_fresh_access_token, publish_text_post
from src.config import Settings


def test_build_authorize_url():
    settings = Settings(
        LINKEDIN_CLIENT_ID="abc",
        LINKEDIN_REDIRECT_URI="http://localhost:8501/",
    )
    url = build_authorize_url(settings, state="xyz")
    assert "client_id=abc" in url
    assert "w_member_social" in url
    assert "state=xyz" in url


def test_access_token_expired():
    past = datetime.now(timezone.utc) - timedelta(minutes=5)
    future = datetime.now(timezone.utc) + timedelta(hours=1)
    assert access_token_expired(past) is True
    assert access_token_expired(future) is False


def test_token_expiry_from_response():
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    access, refresh = token_expiry_from_response(
        {"expires_in": 3600, "refresh_token_expires_in": 86400},
        now=now,
    )
    assert access == now + timedelta(seconds=3600)
    assert refresh == now + timedelta(seconds=86400)


def test_ensure_fresh_access_token_refreshes(mocker):
    token = SimpleNamespace(
        access_token="old",
        refresh_token="refresh",
        access_expires_at=datetime.now(timezone.utc) - timedelta(minutes=1),
        refresh_expires_at=datetime.now(timezone.utc) + timedelta(days=300),
        member_urn="urn:li:person:1",
    )
    mocker.patch(
        "src.linkedin.publisher.refresh_access_token",
        return_value={
            "access_token": "new",
            "refresh_token": "refresh2",
            "expires_in": 3600,
            "refresh_token_expires_in": 31536000,
        },
    )
    repo = mocker.Mock()
    repo.upsert_linkedin_token.return_value = SimpleNamespace(
        access_token="new",
        refresh_token="refresh2",
        access_expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        refresh_expires_at=datetime.now(timezone.utc) + timedelta(days=365),
        member_urn="urn:li:person:1",
    )
    updated = ensure_fresh_access_token(repo, token)  # type: ignore[arg-type]
    assert updated.access_token == "new"
    repo.upsert_linkedin_token.assert_called_once()


def test_publish_text_post_payload(mocker):
    mock_resp = mocker.Mock(status_code=201, text="{}", headers={"x-restli-id": "urn:li:share:123"})
    mock_resp.json.return_value = {"id": "urn:li:share:123"}
    post = mocker.patch("src.linkedin.publisher.requests.post", return_value=mock_resp)
    urn = publish_text_post(
        access_token="tok",
        member_urn="urn:li:person:9",
        text="Hello industry",
    )
    assert urn == "urn:li:share:123"
    payload = post.call_args.kwargs["json"]
    assert payload == build_ugc_payload(member_urn="urn:li:person:9", text="Hello industry")


def test_build_authorize_url_requires_client_id():
    with pytest.raises(Exception):
        build_authorize_url(Settings(LINKEDIN_CLIENT_ID=""))
