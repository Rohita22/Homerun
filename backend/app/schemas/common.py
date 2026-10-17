"""Shared response envelopes. PRD section 11: "All endpoints return structured errors with
code, message, request_id." ``ErrorBody``/``ErrorResponse`` are what ``app.main``'s exception
handler emits for every ``HomerunError``.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class ErrorBody(BaseModel):
    code: str
    message: str
    request_id: str
    details: dict = {}


class ErrorResponse(BaseModel):
    error: ErrorBody


class AgentTraceOut(BaseModel):
    """One agent's contribution to a pipeline run, surfaced to the client so the UI can show the
    full multi-agent orchestration happening behind a single API call (PRD section 12: "system
    evidence panel") instead of a black-box spinner."""

    agent_name: str
    status: str
    elapsed_ms: float
    model_version: str | None = None
    warnings: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)
    detail: str | None = None

    @classmethod
    def from_agent_result(cls, result) -> "AgentTraceOut":  # noqa: ANN001
        return cls(
            agent_name=result.agent_name,
            status=result.status,
            elapsed_ms=result.elapsed_ms,
            model_version=result.model_version,
            warnings=result.warnings,
            evidence_refs=result.evidence_refs,
        )
