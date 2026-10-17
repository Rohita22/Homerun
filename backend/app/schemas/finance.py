"""Schemas for ``POST /api/finance/estimate`` (PRD section 11 / 7F)."""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.schemas.common import AgentTraceOut


class FinanceEstimateRequest(BaseModel):
    price_sgd: float = Field(gt=0)
    down_payment_sgd: float = Field(ge=0)
    annual_rate_pct: float = Field(ge=0, le=20)
    years: int = Field(gt=0, le=35)


class FinanceScenarioOut(BaseModel):
    label: str
    annual_rate_pct: float
    monthly_payment_sgd: float
    delta_vs_base_sgd: float


class FinanceEstimateResponse(BaseModel):
    monthly_payment_sgd: float
    loan_principal_sgd: float
    down_payment_sgd: float
    annual_rate_pct: float
    tenure_years: int
    scenarios: list[FinanceScenarioOut]
    assumptions: list[str]
    trace: list[AgentTraceOut] = Field(default_factory=list)
