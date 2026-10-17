"""Agent 3 — Valuation (PRD section 5). Thin wrapper around the injected ``ValuationModel`` so
the orchestrator can call every agent through the same ``run(request_id, ...)`` shape; all
HDB-only / unsupported-type logic lives in the model implementation (``ValuationService``).
"""

from __future__ import annotations

from app.agents.base import timed_result
from app.domain.entities import AgentResult, PropertyListing, ValuationResult
from app.domain.interfaces.valuation_model import ValuationModel


class ValuationAgent:
    name = "valuation"

    def __init__(self, model: ValuationModel) -> None:
        self._model = model

    def run(self, request_id: str, listing: PropertyListing) -> AgentResult[ValuationResult]:
        def _work() -> ValuationResult:
            return self._model.predict(listing)

        return timed_result(self.name, request_id, _work, model_version=self._model.version)
