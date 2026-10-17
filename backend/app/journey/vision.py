"""Viewing-photo analysis with Gemini vision.

Given one photo taken during a viewing, return concrete things a buyer should remember: the room
and up to three good / three bad observations. The prompt forbids prices, valuations and legal
claims and asks for "possible" when unsure; the reply is parsed defensively and clipped, and any
failure (no key, HTTP error, unparseable reply) is reported as an error the UI can retry — it is
never replaced with invented observations.
"""

from __future__ import annotations

import base64
import json
import re

import httpx

from app.core.logging import get_logger
from app.providers.llm.gemini_client import GeminiClient, GeminiUnavailable

logger = get_logger(__name__)

PROMPT = (
    "You help a home buyer during a property viewing in Singapore. Look at this photo and note "
    "concrete observations a buyer should remember. Reply with ONLY JSON, no prose: "
    '{"room":"short room or area name","good":["..."],"bad":["..."]}. At most 3 items each, '
    "each under 12 words. Only describe what is visible; use \"possible\" when unsure. No "
    "prices, valuations or legal claims."
)
_DATA_URL = re.compile(r"^data:(image/(?:jpeg|png|webp));base64,(.+)$", re.DOTALL)


class VisionUnavailable(RuntimeError):
    pass


def _clip(items: object, limit: int = 3) -> list[str]:
    if not isinstance(items, list):
        return []
    return [str(i).strip()[:90] for i in items if str(i).strip()][:limit]


class GeminiVisionAnalyzer:
    def __init__(self, api_key: str | None, models: list[str], client: httpx.Client | None = None) -> None:
        self._api_key = api_key
        self._gemini = GeminiClient(api_key, models, timeout_s=40.0, client=client)

    @property
    def available(self) -> bool:
        return self._gemini.available

    def analyze(self, image_data_url: str) -> dict:
        if not self._api_key:
            raise VisionUnavailable("Photo analysis needs a GEMINI_API_KEY.")
        match = _DATA_URL.match(image_data_url or "")
        if not match:
            raise ValueError("Expected a base64 image data URL (jpeg, png or webp).")
        mime, b64 = match.groups()
        base64.b64decode(b64, validate=True)  # reject garbage before spending an API call
        try:
            text = self._gemini.generate(
                [{"inline_data": {"mime_type": mime, "data": b64}}, {"text": PROMPT}], max_tokens=500
            )
        except GeminiUnavailable as exc:
            raise VisionUnavailable(str(exc)) from exc
        payload = json.loads(text[text.index("{"): text.rindex("}") + 1])
        return {
            "room": str(payload.get("room") or "")[:28],
            "good": _clip(payload.get("good")),
            "bad": _clip(payload.get("bad")),
        }
