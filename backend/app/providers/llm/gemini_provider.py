"""Gemini-backed preference extraction.

Sends only the buyer's free-text message plus the current (already-anonymous) profile patch —
never raw session/contact data (PRD section 6: "Send minimal information; no unsanitized private
buyer details"). The model is instructed to return JSON only; that JSON is schema-validated by
``ExtractionResult``/``BuyerProfile`` before it ever reaches a caller, and any failure (network,
timeout, malformed JSON) degrades to :class:`TemplateLLMProvider` rather than surfacing raw
model output (PRD: "LLM output can be displayed only after schema validation and source
grounding").
"""

from __future__ import annotations

import json

import httpx

from app.core.logging import get_logger
from app.domain.interfaces.llm_provider import ExtractionResult
from app.providers.llm.template_provider import TemplateLLMProvider

logger = get_logger(__name__)

_SYSTEM_PROMPT = (
    "Extract Singapore property-buyer search preferences from the message as compact JSON with "
    "only these optional keys: transaction_type (buy|rent), property_type (HDB|CONDO|LANDED|EC), "
    "max_price_sgd (number), min_bedrooms (int), preferred_towns (array of uppercase SG town "
    "names), soft_weights (object of feature->0..1 weight), hard_constraints (array of field "
    "names among the above that are non-negotiable). Return JSON only, no prose, no markdown."
)


class GeminiLLMProvider:
    name = "gemini"

    def __init__(self, api_key: str, client: httpx.Client | None = None) -> None:
        self._api_key = api_key
        self._client = client or httpx.Client(timeout=8.0)
        self._fallback = TemplateLLMProvider()

    def extract_preferences(self, message: str, existing_profile: dict) -> ExtractionResult:
        try:
            response = self._client.post(
                "https://generativelanguage.googleapis.com/v1beta/models/"
                "gemini-2.0-flash:generateContent",
                params={"key": self._api_key},
                json={
                    "contents": [
                        {"role": "user", "parts": [{"text": f"{_SYSTEM_PROMPT}\n\n{message}"}]}
                    ]
                },
            )
            response.raise_for_status()
            text = response.json()["candidates"][0]["content"]["parts"][0]["text"]
            text = text.strip().removeprefix("```json").removeprefix("```").removesuffix("```")
            patch = json.loads(text)
            if not isinstance(patch, dict):
                raise ValueError("Gemini response was not a JSON object")
            return ExtractionResult(profile_patch=patch, used_llm=True)
        except (httpx.HTTPError, KeyError, IndexError, ValueError, json.JSONDecodeError) as exc:
            logger.warning("gemini_extraction_failed falling_back_to_template error=%s", exc)
            result = self._fallback.extract_preferences(message, existing_profile)
            result.warnings = [*result.warnings, "LLM unavailable; used deterministic extraction."]
            return result

    def health(self) -> bool:
        return bool(self._api_key)
