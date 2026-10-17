"""Repository for sessions + buyer profiles (Single Responsibility: all persistence for buyer
state lives here; nothing above this layer writes SQL/ORM directly).
"""

from __future__ import annotations

from datetime import timedelta

from sqlalchemy.orm import Session as DbSession

from app.core.config import get_settings
from app.core.time import utcnow
from app.db.models import BuyerProfileRow
from app.db.models import Session as SessionRow
from app.domain.entities import BuyerProfile


class SessionRepository:
    def __init__(self, db: DbSession) -> None:
        self._db = db

    def get_or_create(self, session_id: str | None) -> SessionRow:
        if session_id:
            existing = self._db.get(SessionRow, session_id)
            if existing is not None:
                if existing.expires_at <= utcnow():
                    # Renew an expired anonymous session rather than orphaning its data
                    # (PRD section 9: "anonymous sessions expire after 24 hours (demo)").
                    existing.expires_at = utcnow() + timedelta(
                        hours=get_settings().session_ttl_hours
                    )
                    self._db.commit()
                return existing
            row = SessionRow(session_id=session_id)
        else:
            row = SessionRow()
        self._db.add(row)
        self._db.commit()
        self._db.refresh(row)
        return row

    def get_profile(self, session_id: str) -> BuyerProfile | None:
        row = self._db.get(BuyerProfileRow, session_id)
        if row is None:
            return None
        data = dict(row.preferences_json or {})
        data["session_id"] = session_id
        if row.budget is not None:
            data.setdefault("max_price_sgd", row.budget)
        if row.property_type is not None:
            data.setdefault("property_type", row.property_type)
        return BuyerProfile.model_validate(data)

    def save_profile(self, profile: BuyerProfile) -> BuyerProfile:
        self.get_or_create(profile.session_id)
        row = self._db.get(BuyerProfileRow, profile.session_id)
        payload = profile.model_dump(mode="json", exclude={"session_id"})
        if row is None:
            row = BuyerProfileRow(
                session_id=profile.session_id,
                budget=profile.max_price_sgd,
                property_type=profile.property_type.value if profile.property_type else None,
                preferences_json=payload,
            )
            self._db.add(row)
        else:
            row.budget = profile.max_price_sgd
            row.property_type = profile.property_type.value if profile.property_type else None
            row.preferences_json = payload
        self._db.commit()
        return profile

    def merge_patch(self, session_id: str, patch: dict) -> BuyerProfile:
        existing = self.get_profile(session_id) or BuyerProfile(session_id=session_id)
        merged = existing.model_dump()
        for key, value in patch.items():
            if value is None:
                continue
            if key in {"preferred_towns", "hard_constraints"} and isinstance(value, list):
                merged[key] = sorted(set(merged.get(key, []) or []) | set(value))
            elif key == "soft_weights" and isinstance(value, dict):
                merged.setdefault("soft_weights", {}).update(value)
            else:
                merged[key] = value
        merged["session_id"] = session_id
        profile = BuyerProfile.model_validate(merged)
        return self.save_profile(profile)
