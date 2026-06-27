"""Provider-agnostic LLM layer.

One entry point — ``complete_json(prompt)`` — used by the AI Coach, NL expense
parsing, and push-notification copy. The active provider is chosen by config, so
the rest of the app never imports a vendor SDK or URL.

Swapping providers:
  * To any **OpenAI-compatible** API (OpenAI, OpenRouter, Together, Fireworks,
    DeepInfra, a local server, …) → just set LLM_PROVIDER / LLM_BASE_URL /
    LLM_API_KEY / LLM_MODEL in the environment. No code change.
  * To an **exotic** API (e.g. Anthropic-native, Gemini-native) → write one small
    adapter class with a ``complete_json`` method and select it in ``_build_client``.
    Callers (coach_ai, nl_parse, notifications) stay untouched.

Raises on any non-2xx (incl. 429) and on a malformed response, so callers can
catch and degrade gracefully (rules / regex / static fallback).
"""

import json
from typing import Protocol

import httpx

from app.core.config import get_settings

settings = get_settings()


class LLMClient(Protocol):
    """Anything that can turn a prompt into a parsed JSON object."""

    def complete_json(self, prompt: str, *, temperature: float = 0.2, timeout: float = 20.0) -> dict:
        ...


class OpenAICompatibleClient:
    """Adapter for any OpenAI-compatible ``/chat/completions`` endpoint in JSON
    mode — covers Groq, OpenAI, OpenRouter, Together, Fireworks, DeepInfra, etc."""

    def __init__(self, base_url: str, api_key: str, model: str):
        self._url = base_url.rstrip("/") + "/chat/completions"
        self._key = api_key
        self._model = model

    def complete_json(self, prompt: str, *, temperature: float = 0.2, timeout: float = 20.0) -> dict:
        resp = httpx.post(
            self._url,
            headers={"Authorization": f"Bearer {self._key}"},
            json={
                "model": self._model,
                "messages": [{"role": "user", "content": prompt}],
                "response_format": {"type": "json_object"},
                "temperature": temperature,
            },
            timeout=timeout,
        )
        resp.raise_for_status()
        raw = (resp.json()["choices"][0]["message"]["content"] or "").strip()
        if raw.startswith("```"):
            raw = raw.strip("`").lstrip("json").strip()
        return json.loads(raw)


# Known OpenAI-compatible providers → base URL. Add more freely; or set
# LLM_BASE_URL directly to use one not listed here.
_OPENAI_COMPATIBLE_BASES = {
    "groq": "https://api.groq.com/openai/v1",
    "openai": "https://api.openai.com/v1",
    "openrouter": "https://openrouter.ai/api/v1",
    "together": "https://api.together.xyz/v1",
    "fireworks": "https://api.fireworks.ai/inference/v1",
    "deepinfra": "https://api.deepinfra.com/v1/openai",
}


def _build_client() -> LLMClient:
    provider = (settings.LLM_PROVIDER or "groq").lower()
    # Resolve key/model/base, falling back to the Groq-specific settings so an
    # existing deploy with only GROQ_* set keeps working unchanged.
    api_key = settings.LLM_API_KEY or settings.GROQ_API_KEY
    model = settings.LLM_MODEL or settings.GROQ_MODEL
    base_url = settings.LLM_BASE_URL or _OPENAI_COMPATIBLE_BASES.get(provider)
    if not base_url:
        raise ValueError(
            f"Unknown LLM provider '{provider}'. Set LLM_BASE_URL, or add it to "
            "_OPENAI_COMPATIBLE_BASES, or write a dedicated adapter in llm.py."
        )
    return OpenAICompatibleClient(base_url=base_url, api_key=api_key, model=model)


_client: LLMClient | None = None


def get_llm() -> LLMClient:
    """Lazily build and cache the configured provider client."""
    global _client
    if _client is None:
        _client = _build_client()
    return _client


def complete_json(prompt: str, *, temperature: float = 0.2, timeout: float = 20.0) -> dict:
    """Provider-agnostic JSON completion. Raises on failure (incl. 429)."""
    return get_llm().complete_json(prompt, temperature=temperature, timeout=timeout)


def has_llm() -> bool:
    """True if an API key is configured (so callers can skip the LLM and use a fallback)."""
    return bool(settings.LLM_API_KEY or settings.GROQ_API_KEY)


def is_rate_limit_error(exc: Exception) -> bool:
    """True if an LLM exception is a quota / rate-limit (HTTP 429). Generic across providers."""
    code = getattr(exc, "code", None) or getattr(exc, "status_code", None)
    resp = getattr(exc, "response", None)  # httpx.HTTPStatusError
    if code == 429 or getattr(resp, "status_code", None) == 429:
        return True
    text = str(exc).upper()
    return "429" in text or "RESOURCE_EXHAUSTED" in text or "TOO MANY REQUESTS" in text
