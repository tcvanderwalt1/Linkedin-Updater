"""Webhook notifier tests — mocked HTTP only."""

from __future__ import annotations

from src.notify import webhook


def test_send_webhook_skips_without_url(mocker):
    mock_post = mocker.patch("src.notify.webhook.requests.post")
    mocker.patch("src.notify.webhook.get_settings", return_value=type("S", (), {"webhook_url": ""})())
    assert webhook.send_webhook("hello") is False
    mock_post.assert_not_called()


def test_send_webhook_posts_payload(mocker):
    mock_resp = mocker.Mock(status_code=204, text="")
    mock_post = mocker.patch("src.notify.webhook.requests.post", return_value=mock_resp)
    ok = webhook.send_webhook(
        "pipeline empty",
        webhook_url="https://hooks.example/discord",
        extra={"articles_considered": 0},
    )
    assert ok is True
    mock_post.assert_called_once()
    args, kwargs = mock_post.call_args
    assert args[0] == "https://hooks.example/discord"
    assert "text" in kwargs["json"]
    assert "content" in kwargs["json"]


def test_notify_failure_and_empty(mocker):
    spy = mocker.patch("src.notify.webhook.send_webhook", return_value=True)
    assert webhook.notify_empty_day(articles_considered=3) is True
    assert webhook.notify_failure("boom", stage="search") is True
    assert spy.call_count == 2
