"""Deterministic mortgage / affordability math (PRD section 7F).

M = P * r(1+r)^n / ((1+r)^n - 1), handling r=0 separately. Every assumption the buyer supplied
(rate, down payment, tenure) is echoed back, and taxes/stamp duties are explicitly labeled as
excluded — this module never invents grant/loan eligibility, matching the PRD non-goal "No
mortgage approvals ... financial advice".
"""

from __future__ import annotations

from app.domain.entities import FinanceEstimate

ASSUMPTIONS = [
    "Estimate only; not a loan offer or approval.",
    "Excludes stamp duties, legal fees and property taxes unless otherwise stated.",
    "Assumes a fully amortizing fixed-rate loan at the buyer-supplied rate for the full tenure.",
    "Grant/loan eligibility is not assessed; confirm with an official source before relying on this figure.",
]


def monthly_installment(principal_sgd: float, annual_rate_pct: float, tenure_years: int) -> float:
    if principal_sgd <= 0 or tenure_years <= 0:
        return 0.0
    n = tenure_years * 12
    r = (annual_rate_pct / 100) / 12
    if r == 0:
        return principal_sgd / n
    factor = (1 + r) ** n
    return principal_sgd * r * factor / (factor - 1)


class FinanceCalculator:
    def estimate(
        self,
        price_sgd: float,
        down_payment_sgd: float,
        annual_rate_pct: float,
        tenure_years: int,
        stress_rate_deltas_pct: list[float] | None = None,
    ) -> FinanceEstimate:
        down_payment_sgd = min(down_payment_sgd, price_sgd)
        principal = max(0.0, price_sgd - down_payment_sgd)
        base_payment = monthly_installment(principal, annual_rate_pct, tenure_years)

        stress_rate_deltas_pct = stress_rate_deltas_pct or [1.0, 2.0]
        scenarios = []
        for delta in stress_rate_deltas_pct:
            stressed_rate = annual_rate_pct + delta
            stressed_payment = monthly_installment(principal, stressed_rate, tenure_years)
            scenarios.append(
                {
                    "label": f"rate +{delta:.1f}pp stress test",
                    "annual_rate_pct": round(stressed_rate, 2),
                    "monthly_payment_sgd": round(stressed_payment, 2),
                    "delta_vs_base_sgd": round(stressed_payment - base_payment, 2),
                }
            )

        return FinanceEstimate(
            monthly_payment_sgd=round(base_payment, 2),
            loan_principal_sgd=round(principal, 2),
            down_payment_sgd=round(down_payment_sgd, 2),
            annual_rate_pct=annual_rate_pct,
            tenure_years=tenure_years,
            scenarios=scenarios,
            assumptions=ASSUMPTIONS,
        )
