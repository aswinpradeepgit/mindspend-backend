"""Shared Groq client — OpenAI-compatible chat-completions with JSON mode.

Single source of truth for the Groq HTTP call used by both NL expense parsing
and the AI Coach. Groq's free tier needs no billing and has generous limits.

Raises on any non-2xx (including 429) and on a malformed response, so callers
can catch and fall back gracefully (regex parse / rules-based coaching).
"""

import json

import httpx

from app.core.config import get_settings

settings = get_settings()

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"


def groq_json(prompt: str, *, temperature: float = 0.2, timeout: float = 20.0) -> dict:
    """Call Groq in JSON mode and return the parsed JSON object.

    Raises ``httpx.HTTPStatusError`` (incl. 429) on API failure, or a JSON/Value
    error on a bad response — callers are expected to catch and degrade.
    """
    resp = httpx.post(
        GROQ_URL,
        headers={"Authorization": f"Bearer {settings.GROQ_API_KEY}"},
        json={
            "model": settings.GROQ_MODEL,
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


def is_rate_limit_error(exc: Exception) -> bool:
    """True if an LLM exception is a quota / rate-limit (HTTP 429)."""
    code = getattr(exc, "code", None) or getattr(exc, "status_code", None)
    resp = getattr(exc, "response", None)  # httpx.HTTPStatusError
    if code == 429 or getattr(resp, "status_code", None) == 429:
        return True
    text = str(exc).upper()
    return "429" in text or "RESOURCE_EXHAUSTED" in text or "TOO MANY REQUESTS" in text
