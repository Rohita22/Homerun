"""Gemini ``generateContent`` with an ordered model chain.

The configured model comes first; if Google reports it unknown (404) or the key has no quota for
it (429) the next model in the chain is used, and that verdict is remembered for a while so every
later call goes straight to a model that works instead of paying for a failing request first.
Chat extraction and viewing-photo analysis share this, so they degrade the same way: when no model
in the chain works the caller gets :class:`GeminiUnavailable` and falls back to its own
deterministic path (template extractor / "couldn't read this one").
"""

from __future__ import annotations

import re
import threading
import time

import httpx

from app.core.logging import get_logger

logger = get_logger(__name__)
_BASE = "https://generativelanguage.googleapis.com/v1beta/models"
_NOT_FOUND_TTL_S = 3600.0
_QUOTA_TTL_S = 300.0
_TIMEOUT_TTL_S = 60.0  # a model that just timed out: don't make the next message wait for it too
_skip_until: dict[str, float] = {}
_lock = threading.Lock()


class GeminiUnavailable(RuntimeError):
    """No model in the chain could answer."""


def _skipped(model: str) -> bool:
    with _lock:
        return _skip_until.get(model, 0.0) > time.monotonic()


def _skip(model: str, seconds: float) -> None:
    with _lock:
        _skip_until[model] = time.monotonic() + seconds


def _retry_note(body: str) -> str | None:
    """'Please retry in 1h33m27.4s' -> '1h 33m' (a readable hint for the buyer)."""
    m = re.search(r"retry in (?:(\d+)h)?(?:(\d+)m)?([\d.]+)s", body or "")
    if not m:
        return None
    h, mins = int(m.group(1) or 0), int(m.group(2) or 0)
    return f"{h}h {mins}m" if h else (f"{mins}m" if mins else "a minute")


class GeminiClient:
    def __init__(
        self, api_key: str | None, models: list[str], timeout_s: float = 20.0,
        client: httpx.Client | None = None,
    ) -> None:
        self._api_key = api_key
        self._models = [m for i, m in enumerate(models) if m and m not in models[:i]]
        self._client = client or httpx.Client(timeout=timeout_s)

    @property
    def available(self) -> bool:
        return bool(self._api_key) and bool(self._models)

    def generate(self, parts: list[dict], *, max_tokens: int = 400, temperature: float = 0.2) -> str:
        if not self._api_key:
            raise GeminiUnavailable("no GEMINI_API_KEY")
        last: Exception | None = None
        for model in self._models:
            if _skipped(model):
                continue
            try:
                return self._call(model, parts, max_tokens, temperature)
            except httpx.HTTPStatusError as exc:
                status = exc.response.status_code
                if status == 404:
                    _skip(model, _NOT_FOUND_TTL_S)
                    logger.warning("gemini_model_not_found model=%s trying_next", model)
                elif status == 429:
                    _skip(model, _QUOTA_TTL_S)
                    self._quota_note = _retry_note(exc.response.text)
                    logger.warning("gemini_model_quota model=%s trying_next", model)
                else:
                    raise
                last = exc
            except httpx.TimeoutException as exc:
                _skip(model, _TIMEOUT_TTL_S)
                last = exc
                logger.warning("gemini_model_timeout model=%s trying_next", model)
        note = getattr(self, "_quota_note", None)
        if isinstance(last, httpx.HTTPStatusError) and last.response.status_code == 429 or (last is None and note):
            raise GeminiUnavailable(
                "Gemini's free quota is used up" + (f"; try again in about {note}." if note else "; try again later.")
            ) from last
        raise GeminiUnavailable(f"no Gemini model answered (tried {self._models})") from last

    def _call(self, model: str, parts: list[dict], max_tokens: int, temperature: float) -> str:
        config: dict = {"temperature": temperature, "maxOutputTokens": max_tokens}
        if "flash" in model:  # extraction/vision are short, structured jobs: don't spend time thinking
            config["thinkingConfig"] = {"thinkingBudget": 0}
        body = {"contents": [{"role": "user", "parts": parts}], "generationConfig": config}
        response = self._client.post(f"{_BASE}/{model}:generateContent", params={"key": self._api_key}, json=body)
        if response.status_code == 400 and "thinkingConfig" in config:  # model rejects the knob
            config.pop("thinkingConfig")
            response = self._client.post(f"{_BASE}/{model}:generateContent", params={"key": self._api_key}, json=body)
        response.raise_for_status()
        return response.json()["candidates"][0]["content"]["parts"][0]["text"]
