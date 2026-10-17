"""Persists buyer feedback events (likes, rejects, pairwise choices) that drive preference
re-weighting (PRD section 7D)."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from app.db.models import FeedbackEventRow


class FeedbackRepository:
    def __init__(self, db: DbSession) -> None:
        self._db = db

    def record(
        self,
        session_id: str,
        event_type: str,
        preferred_listing_id: str | None = None,
        rejected_listing_id: str | None = None,
    ) -> FeedbackEventRow:
        row = FeedbackEventRow(
            session_id=session_id,
            event_type=event_type,
            preferred_listing_id=preferred_listing_id,
            rejected_listing_id=rejected_listing_id,
        )
        self._db.add(row)
        self._db.commit()
        return row

    def list_for_session(self, session_id: str) -> list[FeedbackEventRow]:
        return (
            self._db.execute(
                select(FeedbackEventRow)
                .where(FeedbackEventRow.session_id == session_id)
                .order_by(FeedbackEventRow.created_at.asc())
            )
            .scalars()
            .all()
        )
