"""``POST /api/chat`` (PRD section 11): free-text buyer message -> structured profile patch via
the Buyer Intelligence agent."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.agents.buyer_intelligence import BuyerIntelligenceAgent
from app.api.deps import get_buyer_intelligence_agent, get_request_id, get_session_repository
from app.core.logging import get_logger
from app.repositories.session_repository import SessionRepository
from app.schemas.chat import ChatRequest, ChatResponse
from app.schemas.common import AgentTraceOut

logger = get_logger(__name__)

router = APIRouter(tags=["chat"])


@router.post("/chat", response_model=ChatResponse)
def chat(
    body: ChatRequest,
    request_id: str = Depends(get_request_id),
    agent: BuyerIntelligenceAgent = Depends(get_buyer_intelligence_agent),
    session_repo: SessionRepository = Depends(get_session_repository),
) -> ChatResponse:
    session_row = session_repo.get_or_create(body.session_id)
    existing_profile = session_repo.get_profile(session_row.session_id)
    existing_dict = existing_profile.model_dump(mode="json") if existing_profile else {}

    result = agent.run(request_id, body.message, existing_dict)
    patch = (result.data or {}).get("profile_patch", {})
    followup = (result.data or {}).get("followup_question")
    used_llm = bool((result.data or {}).get("used_llm", False))
    logger.info(
        "[ORCHESTRATOR] request_id=%s stage=extract agent=%s status=%s elapsed_ms=%.1f "
        "used_llm=%s model_version=%s",
        request_id, result.agent_name, result.status, result.elapsed_ms, used_llm,
        result.model_version,
    )

    merged_profile = session_repo.merge_patch(session_row.session_id, patch)

    return ChatResponse(
        session_id=session_row.session_id,
        buyer_profile_patch=patch,
        buyer_profile=merged_profile.model_dump(mode="json"),
        followup_question=followup,
        warnings=result.warnings,
        used_llm=used_llm,
        trace=[AgentTraceOut.from_agent_result(result)],
    )
