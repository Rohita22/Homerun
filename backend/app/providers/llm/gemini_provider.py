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
from app.providers.llm.gemini_client import GeminiClient, GeminiUnavailable
from app.providers.llm.template_provider import TemplateLLMProvider

logger = get_logger(__name__)

_SYSTEM_PROMPT = (
    "Extract Singapore property-buyer search preferences from the message as compact JSON with "
    "only these optional keys: transaction_type (buy|rent), property_type (HDB|CONDO|LANDED|EC), "
    "max_price_sgd (number), min_bedrooms (int), preferred_towns (array of uppercase SG town "
    "names), soft_weights (object whose optional keys are commute, mrt, area, price, each an "
    "integer 0-10 for how much the buyer cares), hard_constraints (array of field names among "
    "the above that are non-negotiable). Include a field ONLY if the message states it; never "
    "guess or default. Return JSON only, no prose, no markdown."
)


class GeminiLLMProvider:
    name = "gemini"

    def __init__(self, api_key: str, models: list[str], client: httpx.Client | None = None) -> None:
        self._api_key = api_key
        self._gemini = GeminiClient(api_key, models, timeout_s=12.0, client=client)
        self._fallback = TemplateLLMProvider()

    def extract_preferences(self, message: str, existing_profile: dict) -> ExtractionResult:
        try:
            text = self._gemini.generate([{"text": f"{_SYSTEM_PROMPT}\n\n{message}"}], max_tokens=400)
            text = text.strip().removeprefix("```json").removeprefix("```").removesuffix("```")
            patch = json.loads(text)
            if not isinstance(patch, dict):
                raise ValueError("Gemini response was not a JSON object")
            return ExtractionResult(profile_patch=patch, used_llm=True)
        except (GeminiUnavailable, httpx.HTTPError, KeyError, IndexError, ValueError) as exc:
            logger.warning("gemini_extraction_failed falling_back_to_template error=%s", exc)
            result = self._fallback.extract_preferences(message, existing_profile)
            result.warnings = [*result.warnings, "LLM unavailable; used deterministic extraction."]
            return result

    def health(self) -> bool:
        return bool(self._api_key)
