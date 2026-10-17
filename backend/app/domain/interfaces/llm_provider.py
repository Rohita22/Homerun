"""LLM provider contract for buyer-preference extraction and grounded explanations.

Every implementation returns already-parsed, schema-validated data (``ExtractionResult``) —
never raw text handed straight to the client (PRD section 11: "never pass unvalidated LLM JSON
to the user or database"). The ``template`` implementation makes the whole chat flow work with
zero external calls, satisfying the P0 requirement to "gracefully degrade without LLM".
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from pydantic import BaseModel, Field


class ExtractionResult(BaseModel):
    profile_patch: dict = Field(default_factory=dict)
    followup_question: str | None = None
    warnings: list[str] = Field(default_factory=list)
    used_llm: bool = False


@runtime_checkable
class LLMProvider(Protocol):
    name: str

    def extract_preferences(self, message: str, existing_profile: dict) -> ExtractionResult:
        ...

    def health(self) -> bool:
        ...
