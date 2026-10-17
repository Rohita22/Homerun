"""``POST /api/finance/estimate`` (PRD section 11 / 7F), via the Affordability & Risk agent."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.agents.affordability_agent import AffordabilityRiskAgent
from app.api.deps import get_affordability_agent, get_request_id
from app.schemas.common import AgentTraceOut
from app.schemas.finance import FinanceEstimateRequest, FinanceEstimateResponse, FinanceScenarioOut

router = APIRouter(tags=["finance"])


@router.post("/finance/estimate", response_model=FinanceEstimateResponse)
def post_finance_estimate(
    body: FinanceEstimateRequest,
    request_id: str = Depends(get_request_id),
    agent: AffordabilityRiskAgent = Depends(get_affordability_agent),
) -> FinanceEstimateResponse:
    result = agent.run(
        request_id,
        price_sgd=body.price_sgd,
        down_payment_sgd=body.down_payment_sgd,
        annual_rate_pct=body.annual_rate_pct,
        tenure_years=body.years,
    )
    estimate = result.data
    return FinanceEstimateResponse(
        monthly_payment_sgd=estimate.monthly_payment_sgd,
        loan_principal_sgd=estimate.loan_principal_sgd,
        down_payment_sgd=estimate.down_payment_sgd,
        annual_rate_pct=estimate.annual_rate_pct,
        tenure_years=estimate.tenure_years,
        scenarios=[FinanceScenarioOut(**s) for s in estimate.scenarios],
        assumptions=estimate.assumptions,
        trace=[AgentTraceOut.from_agent_result(result)],
    )
