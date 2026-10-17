"""Repository for the normalized listing catalog (``properties`` table) plus agent-association
reads. Acts as the persistence-backed cache in front of whichever ``ListingProvider`` is active
(PRD section 6: "Cache with TTL and provenance; treat missing/contradictory fields as unknown").
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session as DbSession

from app.core.time import utcnow
from app.db.models import AgentRow, ListingAgentLinkRow, PropertyRow
from app.domain.entities import Agent, ListingAgentLink, PropertyListing


def _row_to_entity(row: PropertyRow) -> PropertyListing:
    return PropertyListing(
        listing_id=row.listing_id,
        provider=row.provider,
        external_id=row.external_id,
        source_url=row.source_url,
        published_at=row.published_at,
        fetched_at=row.fetched_at,
        status=row.status,
        transaction_type=row.transaction_type,
        property_type=row.type,
        asking_price_sgd=row.price,
        bedrooms=row.bedrooms,
        bathrooms=row.bathrooms,
        floor_area_sqm=row.floor_area,
        address_public=row.address_public,
        town=row.town,
        latitude=row.lat,
        longitude=row.lon,
        tenure=row.tenure,
        lease_remaining_years=row.lease_remaining_years,
        floor_level=row.floor_level,
        flat_type=row.flat_type,
        flat_model=row.flat_model,
        storey_range=row.storey_range,
        attributes=row.attributes_json or {},
        images_allowed=row.images_allowed,
        agent_ref=row.agent_ref,
        attribution=row.attribution,
        rights_status=row.rights_status,
    )


class PropertyRepository:
    def __init__(self, db: DbSession) -> None:
        self._db = db

    def upsert_many(self, listings: list[PropertyListing]) -> None:
        # Dedupe by listing_id: a provider (e.g. a live connector merging multiple paginated
        # calls) can hand back the same id twice in one batch, which SQLAlchemy may fold into a
        # single multi-row INSERT and SQLite then rejects as a UNIQUE violation.
        deduped: dict[str, PropertyListing] = {listing.listing_id: listing for listing in listings}
        for listing in deduped.values():
            self.upsert(listing)
        self._db.commit()

    def upsert(self, listing: PropertyListing) -> PropertyRow:
        row = self._db.get(PropertyRow, listing.listing_id)
        values = dict(
            provider=listing.provider,
            external_id=listing.external_id,
            source_url=listing.source_url,
            status=listing.status.value if hasattr(listing.status, "value") else listing.status,
            type=listing.property_type.value
            if hasattr(listing.property_type, "value")
            else listing.property_type,
            transaction_type=listing.transaction_type.value
            if hasattr(listing.transaction_type, "value")
            else listing.transaction_type,
            price=listing.asking_price_sgd,
            bedrooms=listing.bedrooms,
            bathrooms=listing.bathrooms,
            floor_area=listing.floor_area_sqm,
            address_public=listing.address_public,
            town=listing.town,
            lat=listing.latitude,
            lon=listing.longitude,
            tenure=listing.tenure,
            lease_remaining_years=listing.lease_remaining_years,
            floor_level=listing.floor_level,
            flat_type=listing.flat_type,
            flat_model=listing.flat_model,
            storey_range=listing.storey_range,
            attributes_json=listing.attributes,
            images_allowed=listing.images_allowed,
            agent_ref=listing.agent_ref,
            attribution=listing.attribution,
            rights_status=listing.rights_status,
            published_at=listing.published_at,
            fetched_at=listing.fetched_at,
        )
        if row is None:
            row = PropertyRow(listing_id=listing.listing_id, **values)
            self._db.add(row)
        else:
            for key, value in values.items():
                setattr(row, key, value)
        return row

    def get(self, listing_id: str) -> PropertyListing | None:
        row = self._db.get(PropertyRow, listing_id)
        return _row_to_entity(row) if row else None

    def latest_fetched_at(self, provider: str) -> datetime | None:
        return self._db.execute(
            select(func.max(PropertyRow.fetched_at)).where(PropertyRow.provider == provider)
        ).scalar_one_or_none()

    def list_all(self) -> list[PropertyListing]:
        rows = self._db.execute(select(PropertyRow)).scalars().all()
        return [_row_to_entity(r) for r in rows]

    def get_by_ids(self, listing_ids: list[str]) -> list[PropertyListing]:
        rows = self._db.execute(
            select(PropertyRow).where(PropertyRow.listing_id.in_(listing_ids))
        ).scalars().all()
        by_id = {r.listing_id: _row_to_entity(r) for r in rows}
        return [by_id[lid] for lid in listing_ids if lid in by_id]

    def get_agent_link(self, listing_id: str) -> tuple[Agent, ListingAgentLink] | None:
        link_row = (
            self._db.execute(
                select(ListingAgentLinkRow)
                .where(ListingAgentLinkRow.listing_id == listing_id)
                .order_by(ListingAgentLinkRow.checked_at.desc())
            )
            .scalars()
            .first()
        )
        if link_row is None:
            return None
        agent_row = self._db.get(AgentRow, link_row.agent_id)
        if agent_row is None:
            return None
        agent = Agent(
            agent_id=agent_row.agent_id,
            provider_id=agent_row.provider_id,
            name=agent_row.name,
            cea_number=agent_row.cea_number,
            approved_contact=agent_row.approved_contact_json,
            verified_at=agent_row.verified_at,
        )
        link = ListingAgentLink(
            listing_id=link_row.listing_id,
            agent_id=link_row.agent_id,
            evidence_source=link_row.evidence_source,
            association_status=link_row.association_status,
            checked_at=link_row.checked_at,
        )
        return agent, link

    def upsert_agent(self, agent: Agent) -> None:
        row = self._db.get(AgentRow, agent.agent_id)
        if row is None:
            row = AgentRow(agent_id=agent.agent_id)
            self._db.add(row)
        row.provider_id = agent.provider_id
        row.name = agent.name
        row.cea_number = agent.cea_number
        row.approved_contact_json = agent.approved_contact
        row.verified_at = agent.verified_at

    def upsert_link(self, link: ListingAgentLink) -> None:
        row = ListingAgentLinkRow(
            listing_id=link.listing_id,
            agent_id=link.agent_id,
            evidence_source=link.evidence_source,
            association_status=link.association_status.value
            if hasattr(link.association_status, "value")
            else link.association_status,
            checked_at=link.checked_at or utcnow(),
        )
        self._db.add(row)

    def commit(self) -> None:
        self._db.commit()
