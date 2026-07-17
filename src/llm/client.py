"""LLM client for Grok (xAI), Claude (Anthropic), or Gemini (Google)."""

from __future__ import annotations

import logging
from typing import Any
from urllib.parse import quote

import requests

from src.config import Settings, get_settings
from src.llm.prompts import SYSTEM_PROMPT, build_user_prompt

logger = logging.getLogger(__name__)


class LLMError(RuntimeError):
    pass


class LLMClient:
    def __init__(self, settings: Settings | None = None, *, timeout: float = 60.0) -> None:
        self.settings = settings or get_settings()
        self.timeout = timeout

    @property
    def model_name(self) -> str:
        provider = self.settings.llm_provider.lower().strip()
        if provider == "claude":
            return self.settings.claude_model
        if provider in {"gemini", "google"}:
            return self.settings.gemini_model
        return self.settings.grok_model

    def draft_linkedin_post(
        self,
        *,
        title: str,
        snippet: str,
        url: str,
        topics: str = "",
    ) -> str:
        user_prompt = build_user_prompt(
            title=title, snippet=snippet, url=url, topics=topics
        )
        provider = self.settings.llm_provider.lower().strip()
        if provider == "claude":
            return self._call_claude(user_prompt)
        if provider in {"gemini", "google"}:
            return self._call_gemini(user_prompt)
        return self._call_grok(user_prompt)

    def _call_grok(self, user_prompt: str) -> str:
        api_key = self.settings.grok_api_key
        if not api_key:
            raise LLMError("GROK_API_KEY is required")
        url = f"{self.settings.grok_api_base.rstrip('/')}/chat/completions"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        payload: dict[str, Any] = {
            "model": self.settings.grok_model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.7,
        }
        try:
            response = requests.post(
                url, headers=headers, json=payload, timeout=self.timeout
            )
            response.raise_for_status()
        except requests.Timeout as exc:
            raise LLMError(f"Grok API timeout: {exc}") from exc
        except requests.RequestException as exc:
            raise LLMError(f"Grok API error: {exc}") from exc

        data = response.json()
        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMError(f"Unexpected Grok response shape: {data}") from exc
        return str(content).strip()

    def _call_claude(self, user_prompt: str) -> str:
        api_key = self.settings.anthropic_api_key
        if not api_key:
            raise LLMError("ANTHROPIC_API_KEY is required")
        url = "https://api.anthropic.com/v1/messages"
        headers = {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.settings.claude_model,
            "max_tokens": 1024,
            "system": SYSTEM_PROMPT,
            "messages": [{"role": "user", "content": user_prompt}],
        }
        try:
            response = requests.post(
                url, headers=headers, json=payload, timeout=self.timeout
            )
            response.raise_for_status()
        except requests.Timeout as exc:
            raise LLMError(f"Claude API timeout: {exc}") from exc
        except requests.RequestException as exc:
            raise LLMError(f"Claude API error: {exc}") from exc

        data = response.json()
        try:
            blocks = data["content"]
            text_parts = [b["text"] for b in blocks if b.get("type") == "text"]
            content = "\n".join(text_parts)
        except (KeyError, TypeError) as exc:
            raise LLMError(f"Unexpected Claude response shape: {data}") from exc
        return content.strip()

    def _call_gemini(self, user_prompt: str) -> str:
        api_key = self.settings.gemini_api_key
        if not api_key:
            raise LLMError("GEMINI_API_KEY is required")
        model = quote(self.settings.gemini_model, safe="")
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{model}:generateContent"
        )
        headers = {"Content-Type": "application/json"}
        payload = {
            "systemInstruction": {"parts": [{"text": SYSTEM_PROMPT}]},
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": user_prompt}],
                }
            ],
            "generationConfig": {"temperature": 0.7},
        }
        try:
            response = requests.post(
                url,
                headers=headers,
                params={"key": api_key},
                json=payload,
                timeout=self.timeout,
            )
            response.raise_for_status()
        except requests.Timeout as exc:
            raise LLMError(f"Gemini API timeout: {exc}") from exc
        except requests.RequestException as exc:
            detail = ""
            if getattr(exc, "response", None) is not None:
                detail = (exc.response.text or "")[:400]
            raise LLMError(f"Gemini API error: {exc} {detail}".strip()) from exc

        data = response.json()
        try:
            parts = data["candidates"][0]["content"]["parts"]
            content = "".join(str(p.get("text", "")) for p in parts)
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMError(f"Unexpected Gemini response shape: {data}") from exc
        return content.strip()
