"""The "My move" hub: viewings (calendar), checklist, notes and photo observations."""

from __future__ import annotations

from app.core.errors import NotFoundError, ValidationFailedError
from app.core.logging import get_logger
from app.journey.vision import GeminiVisionAnalyzer, VisionUnavailable
from app.journey.views import listing_view
from app.repositories.property_repository import PropertyRepository
from app.repositories.session_repository import SessionRepository
from app.repositories.ui_repository import EnquiryRepository, ViewingRepository, viewing_dict
from app.schemas.journey import ViewingCreate, ViewingPatch

logger = get_logger(__name__)
CHECKLIST_KEYS = {"a", "b", "c", "d", "e", "f"}


class ViewingService:
    def __init__(
        self,
        viewings: ViewingRepository,
        enquiries: EnquiryRepository,
        properties: PropertyRepository,
        vision: GeminiVisionAnalyzer,
        sessions: SessionRepository,
    ) -> None:
        self._sessions = sessions
        self._viewings = viewings
        self._enquiries = enquiries
        self._properties = properties
        self._vision = vision

    def _row(self, session_id: str, viewing_id: str):  # noqa: ANN202
        row = self._viewings.get(session_id, viewing_id)
        if row is None:
            raise NotFoundError(f"Viewing {viewing_id} not found.")
        return row

    def hub(self, session_id: str) -> dict:
        viewings = self._viewings.list(session_id)
        enquiries = self._enquiries.list(session_id)
        ids = list({v["home"] for v in viewings} | {e["id"] for e in enquiries})
        listings = {
            l.listing_id: listing_view(l, self._properties.get_agent_link(l.listing_id))
            for l in self._properties.get_by_ids(ids)
        }
        return {
            "viewings": viewings,
            "enquiries": enquiries,
            "listings": listings,
            "vision_available": self._vision.available,
        }

    def create(self, body: ViewingCreate) -> dict:
        if self._properties.get(body.listing_id) is None:
            raise NotFoundError(f"Listing {body.listing_id} not found.")
        self._sessions.get_or_create(body.session_id)  # viewings hang off a session row
        return self._viewings.create(body.session_id, body.listing_id, body.at_ms, body.status)

    def patch(self, session_id: str, viewing_id: str, body: ViewingPatch) -> dict:
        checks = None
        if body.checks is not None:
            if not set(body.checks) <= CHECKLIST_KEYS:
                raise ValidationFailedError("Unknown checklist item.")
            checks = body.checks
        return self._viewings.update(self._row(session_id, viewing_id), checks=checks, notes=body.notes)

    def delete(self, session_id: str, viewing_id: str) -> None:
        self._viewings.delete(self._row(session_id, viewing_id))

    def add_photo(self, session_id: str, viewing_id: str, data_url: str) -> dict:
        return self._viewings.add_photo(self._row(session_id, viewing_id), data_url)

    def analyze_photo(self, session_id: str, viewing_id: str, photo_id: str) -> dict:
        row = self._row(session_id, viewing_id)
        photo = next((p for p in row.photos_json or [] if p["id"] == photo_id), None)
        if photo is None:
            raise NotFoundError(f"Photo {photo_id} not found.")
        try:
            obs = self._vision.analyze(photo["url"])
        except VisionUnavailable as exc:
            return self._viewings.set_photo(row, photo_id, status="error", reason=str(exc))
        except Exception as exc:  # noqa: BLE001 - HTTP/parse failures are retryable, never fatal
            logger.warning("photo_analysis_failed photo=%s error=%s", photo_id, exc)
            return self._viewings.set_photo(row, photo_id, status="error", reason="analysis failed")
        return self._viewings.set_photo(row, photo_id, status="done", obs=obs, reason=None)

    def remove_photo(self, session_id: str, viewing_id: str, photo_id: str) -> None:
        self._viewings.remove_photo(self._row(session_id, viewing_id), photo_id)


__all__ = ["ViewingService", "viewing_dict"]
