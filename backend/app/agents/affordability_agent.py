"""Agent 4 — Affordability & Risk (PRD section 5). Wraps ``FinanceCalculator`` so it fits the
same agent interface as the others; all math lives in the service (Single Responsibility)."""

from __future__ import annotations

from app.agents.base import timed_result
from app.domain.entities import AgentResult, FinanceEstimate
from app.services.finance_service import FinanceCalculator


class AffordabilityRiskAgent:
    name = "affordability_risk"
    version = "finance-calc-v1"

    def __init__(self, calculator: FinanceCalculator | None = None) -> None:
        self._calculator = calculator or FinanceCalculator()

    def run(
        self,
        request_id: str,
        price_sgd: float,
        down_payment_sgd: float,
        annual_rate_pct: float,
        tenure_years: int,
    ) -> AgentResult[FinanceEstimate]:
        def _work() -> FinanceEstimate:
            return self._calculator.estimate(
                price_sgd, down_payment_sgd, annual_rate_pct, tenure_years
            )

        return timed_result(self.name, request_id, _work, model_version=self.version)
