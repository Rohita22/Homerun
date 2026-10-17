"""Persists each ranking run and its items (PRD tables ``recommendation_runs`` /
``recommendation_items``), giving every recommendation a stable, auditable ``run_id``.
"""

from __future__ import annotations

from sqlalchemy.orm import Session as DbSession

from app.db.models import RecommendationItemRow, RecommendationRunRow
from app.domain.entities import RankedItem


class RecommendationRepository:
    def __init__(self, db: DbSession) -> None:
        self._db = db

    def save_run(
        self, session_id: str, model_version: str, input_hash: str, items: list[RankedItem]
    ) -> str:
        run = RecommendationRunRow(
            session_id=session_id, model_version=model_version, input_hash=input_hash
        )
        self._db.add(run)
        self._db.flush()
        for item in items:
            self._db.add(
                RecommendationItemRow(
                    run_id=run.run_id,
                    listing_id=item.listing_id,
                    rank=item.rank,
                    score=item.score,
                    factors_json={"reasons": item.reasons, **item.factors},
                )
            )
        self._db.commit()
        return run.run_id
