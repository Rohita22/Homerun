"""Persists lead handoffs. Writes are immutable once created, matching PRD section 8's
"Server records immutable request_id, listing_id, agent_id, consent_version, timestamp,
outcome" requirement.
"""

from __future__ import annotations

from sqlalchemy.orm import Session as DbSession

from app.core.time import utcnow
from app.db.models import LeadHandoffRow


class HandoffRepository:
    def __init__(self, db: DbSession) -> None:
        self._db = db

    def create(
        self,
        listing_id: str,
        agent_id: str | None,
        contact_method: str,
        status: str,
        consented: bool,
    ) -> LeadHandoffRow:
        row = LeadHandoffRow(
            listing_id=listing_id,
            agent_id=agent_id,
            contact_method=contact_method,
            status=status,
            consent_at=utcnow() if consented else None,
        )
        self._db.add(row)
        self._db.commit()
        self._db.refresh(row)
        return row
