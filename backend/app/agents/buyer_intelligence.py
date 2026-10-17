"""Agent 1 — Buyer Intelligence (PRD section 5).

Turns a free-text buyer message into a structured ``BuyerProfile`` patch via the injected
``LLMProvider`` (template or Gemini — Dependency Inversion again: this agent never imports a
concrete provider). It never executes freeform SQL and never invents listings; its only output
is a validated patch plus an optional clarification question.
"""

from __future__ import annotations

from app.agents.base import timed_result
from app.domain.entities import AgentResult
from app.domain.interfaces.llm_provider import LLMProvider


class BuyerIntelligenceAgent:
    name = "buyer_intelligence"

    def __init__(self, llm_provider: LLMProvider) -> None:
        self._llm = llm_provider

    def run(self, request_id: str, message: str, existing_profile: dict) -> AgentResult[dict]:
        def _work() -> dict:
            extraction = self._llm.extract_preferences(message, existing_profile)
            return {
                "profile_patch": extraction.profile_patch,
                "followup_question": extraction.followup_question,
                "extraction_warnings": extraction.warnings,
                "used_llm": extraction.used_llm,
            }

        result = timed_result(self.name, request_id, _work, model_version=self._llm.name)
        if result.data:
            result.warnings = [*result.warnings, *result.data.get("extraction_warnings", [])]
        return result
