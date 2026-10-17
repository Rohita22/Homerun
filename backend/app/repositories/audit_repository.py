"""Append-only audit log for every decision (PRD section 5: "All decisions are logged with
stable listing IDs"). Metadata is pre-redacted by callers before it ever reaches this layer —
this repository does not attempt to scrub contact fields itself.
"""

from __future__ import annotations

from sqlalchemy.orm import Session as DbSession

from app.db.models import AuditEventRow


class AuditRepository:
    def __init__(self, db: DbSession) -> None:
        self._db = db

    def record(
        self,
        request_id: str,
        action: str,
        outcome: str,
        latency_ms: float = 0.0,
        metadata_redacted: dict | None = None,
    ) -> None:
        self._db.add(
            AuditEventRow(
                request_id=request_id,
                action=action,
                outcome=outcome,
                latency_ms=latency_ms,
                metadata_redacted_json=metadata_redacted or {},
            )
        )
        self._db.commit()
