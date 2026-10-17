"""Schemas for ``POST /api/chat`` (PRD section 11)."""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.schemas.common import AgentTraceOut


class ChatRequest(BaseModel):
    session_id: str | None = None
    message: str = Field(min_length=1, max_length=2000)


class ChatResponse(BaseModel):
    session_id: str
    buyer_profile_patch: dict
    buyer_profile: dict
    followup_question: str | None = None
    warnings: list[str] = Field(default_factory=list)
    used_llm: bool = False
    trace: list[AgentTraceOut] = Field(default_factory=list)
    disclosure: str = (
        "Your message may be processed by an external LLM provider (or a local deterministic "
        "fallback) to extract structured search preferences."
    )
