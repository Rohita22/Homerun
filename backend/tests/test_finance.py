"""PRD section 7F: deterministic mortgage math."""

from __future__ import annotations

from app.services.finance_service import FinanceCalculator, monthly_installment


def test_monthly_installment_known_value() -> None:
    # P=500,000, annual rate 3%, 25 years -> standard amortization formula sanity check.
    payment = monthly_installment(500_000, 3.0, 25)
    assert 2360 < payment < 2380


def test_monthly_installment_zero_rate() -> None:
    payment = monthly_installment(120_000, 0.0, 10)
    assert payment == 120_000 / 120


def test_finance_estimate_includes_stress_scenarios_and_assumptions() -> None:
    estimate = FinanceCalculator().estimate(
        price_sgd=800_000, down_payment_sgd=160_000, annual_rate_pct=3.0, tenure_years=25
    )
    assert estimate.loan_principal_sgd == 640_000
    assert len(estimate.scenarios) == 2
    assert estimate.scenarios[0]["monthly_payment_sgd"] > estimate.monthly_payment_sgd
    assert any("not a loan offer" in a.lower() for a in estimate.assumptions)


def test_down_payment_cannot_exceed_price() -> None:
    estimate = FinanceCalculator().estimate(
        price_sgd=500_000, down_payment_sgd=600_000, annual_rate_pct=2.5, tenure_years=20
    )
    assert estimate.loan_principal_sgd == 0
    assert estimate.monthly_payment_sgd == 0
