"""Shared agent scaffolding.

Every agent is a small class exposing one ``run`` method and returning a typed
:class:`AgentResult` (PRD section 5 orchestration contracts). ``timed_result`` centralizes the
elapsed-time measurement and status defaulting so individual agents only write business logic
(Single Responsibility) — none of them hand-roll timing or envelope construction.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import TypeVar

from app.domain.entities import AgentResult
from app.domain.enums import AgentResultStatus

T = TypeVar("T")


def timed_result(
    agent_name: str,
    request_id: str,
    fn: Callable[[], T],
    *,
    model_version: str | None = None,
) -> AgentResult[T]:
    start = time.perf_counter()
    warnings: list[str] = []
    try:
        data = fn()
        status = AgentResultStatus.OK.value
    except Exception as exc:  # noqa: BLE001 - agents must degrade, never crash the orchestrator
        data = None
        status = AgentResultStatus.ERROR.value
        warnings.append(str(exc))
    elapsed_ms = (time.perf_counter() - start) * 1000
    return AgentResult(
        request_id=request_id,
        agent_name=agent_name,
        status=status,
        data=data,
        warnings=warnings,
        elapsed_ms=round(elapsed_ms, 3),
        model_version=model_version,
    )
