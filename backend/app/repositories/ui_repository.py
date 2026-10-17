"""Persistence for the hub: viewings (with checklist, notes, photos) and enquiry outcomes."""

from __future__ import annotations

import uuid

from sqlalchemy import delete, select
from sqlalchemy.orm import Session as DbSession

from app.db.models import EnquiryRow, ViewingRow


def viewing_dict(row: ViewingRow) -> dict:
    return {
        "id": row.viewing_id,
        "home": row.listing_id,
        "at": row.at_ms,
        "st": row.status,
        "check": dict(row.checks_json or {}),
        "notes": row.notes or "",
        "photos": list(row.photos_json or []),
    }


class ViewingRepository:
    def __init__(self, db: DbSession) -> None:
        self._db = db

    def list(self, session_id: str) -> list[dict]:
        rows = self._db.execute(
            select(ViewingRow).where(ViewingRow.session_id == session_id).order_by(ViewingRow.at_ms)
        ).scalars().all()
        return [viewing_dict(r) for r in rows]

    def get(self, session_id: str, viewing_id: str) -> ViewingRow | None:
        row = self._db.get(ViewingRow, viewing_id)
        return row if row is not None and row.session_id == session_id else None

    def create(self, session_id: str, listing_id: str, at_ms: int, status: str) -> dict:
        row = ViewingRow(session_id=session_id, listing_id=listing_id, at_ms=at_ms, status=status)
        self._db.add(row)
        self._db.commit()
        return viewing_dict(row)

    def update(self, row: ViewingRow, *, checks: dict | None, notes: str | None) -> dict:
        if checks is not None:
            row.checks_json = {**(row.checks_json or {}), **checks}
        if notes is not None:
            row.notes = notes
        self._db.commit()
        return viewing_dict(row)

    def delete(self, row: ViewingRow) -> None:
        self._db.execute(delete(ViewingRow).where(ViewingRow.viewing_id == row.viewing_id))
        self._db.commit()

    def add_photo(self, row: ViewingRow, url: str) -> dict:
        photo = {"id": "p" + uuid.uuid4().hex[:10], "url": url, "status": "loading", "obs": None}
        row.photos_json = [*(row.photos_json or []), photo]
        self._db.commit()
        return photo

    def set_photo(self, row: ViewingRow, photo_id: str, **patch: object) -> dict | None:
        updated, found = [], None
        for photo in row.photos_json or []:
            if photo["id"] == photo_id:
                photo = {**photo, **patch}
                found = photo
            updated.append(photo)
        row.photos_json = updated  # reassign so SQLAlchemy sees the JSON change
        self._db.commit()
        return found

    def remove_photo(self, row: ViewingRow, photo_id: str) -> None:
        row.photos_json = [p for p in (row.photos_json or []) if p["id"] != photo_id]
        self._db.commit()


class EnquiryRepository:
    def __init__(self, db: DbSession) -> None:
        self._db = db

    def record(self, session_id: str, listing_id: str, kind: str, handoff_id: str | None) -> EnquiryRow:
        row = EnquiryRow(session_id=session_id, listing_id=listing_id, kind=kind, handoff_id=handoff_id)
        self._db.add(row)
        self._db.commit()
        return row

    def list(self, session_id: str) -> list[dict]:
        rows = self._db.execute(
            select(EnquiryRow).where(EnquiryRow.session_id == session_id)
            .order_by(EnquiryRow.created_at.desc())
        ).scalars().all()
        return [
            {"id": r.listing_id, "kind": r.kind, "at": r.created_at.isoformat(), "ref": r.handoff_id}
            for r in rows
        ]
