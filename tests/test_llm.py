"""LLM client + SimCorp-safe prompt contract (mocked HTTP)."""

from __future__ import annotations

import pytest

from src.config import Settings
from src.llm.client import LLMClient, LLMError
from src.llm.prompts import SYSTEM_PROMPT, assert_simcorp_safe_constraints, build_user_prompt


def test_system_prompt_contains_simcorp_safe_contract():
    assert_simcorp_safe_constraints(SYSTEM_PROMPT)
    assert "hashtags" in SYSTEM_PROMPT.lower() or "Hashtags" in SYSTEM_PROMPT


def test_user_prompt_includes_article_fields():
    prompt = build_user_prompt(
        title="AI in asset management",
        snippet="Improving IBOR data quality",
        url="https://example.com/x",
        topics="ai,asset_management",
    )
    assert "AI in asset management" in prompt
    assert "https://example.com/x" in prompt
    assert "SimCorp" in prompt


def test_grok_draft_uses_system_prompt(mocker):
    settings = Settings(
        LLM_PROVIDER="grok",
        GROK_API_KEY="test-key",
        GROK_API_BASE="https://api.x.ai/v1",
        GROK_MODEL="grok-2-latest",
    )
    mock_resp = mocker.Mock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "choices": [{"message": {"content": "Great ops post\n\n#AssetManagement #AI #Fintech"}}]
    }
    mock_resp.raise_for_status = mocker.Mock()
    post = mocker.patch("src.llm.client.requests.post", return_value=mock_resp)

    client = LLMClient(settings)
    text = client.draft_linkedin_post(
        title="Ops AI",
        snippet="Empower IBOR teams",
        url="https://example.com/ops",
        topics="ai",
    )
    assert "AssetManagement" in text or "ops" in text.lower()
    payload = post.call_args.kwargs["json"]
    assert payload["messages"][0]["role"] == "system"
    assert "SimCorp" in payload["messages"][0]["content"]


def test_grok_timeout_raises_llm_error(mocker):
    import requests

    settings = Settings(LLM_PROVIDER="grok", GROK_API_KEY="test-key")
    mocker.patch(
        "src.llm.client.requests.post",
        side_effect=requests.Timeout("timed out"),
    )
    client = LLMClient(settings)
    with pytest.raises(LLMError, match="timeout"):
        client.draft_linkedin_post(title="t", snippet="s", url="https://x")


def test_gemini_draft_uses_system_instruction(mocker):
    settings = Settings(
        LLM_PROVIDER="gemini",
        GEMINI_API_KEY="test-gemini-key",
        GEMINI_MODEL="gemini-2.0-flash",
    )
    mock_resp = mocker.Mock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "candidates": [
            {
                "content": {
                    "parts": [
                        {
                            "text": (
                                "Forward-looking ops note\n\n"
                                "#AssetManagement #AI #Fintech"
                            )
                        }
                    ]
                }
            }
        ]
    }
    mock_resp.raise_for_status = mocker.Mock()
    post = mocker.patch("src.llm.client.requests.post", return_value=mock_resp)

    client = LLMClient(settings)
    text = client.draft_linkedin_post(
        title="Ops AI",
        snippet="Empower IBOR teams",
        url="https://example.com/ops",
        topics="ai",
    )
    assert "AssetManagement" in text
    assert client.model_name == "gemini-2.0-flash"
    kwargs = post.call_args.kwargs
    assert kwargs["params"]["key"] == "test-gemini-key"
    assert "SimCorp" in kwargs["json"]["systemInstruction"]["parts"][0]["text"]
    assert "gemini-2.0-flash" in post.call_args.args[0]