"""Factory selecting the active ``ListingProvider`` from ``Settings.listing_provider``
(PRD section 6: "inject through environment variable LISTING_PROVIDER"). This is the single
place that knows about concrete provider classes; everything else depends on the
``ListingProvider`` protocol only (Dependency Inversion / Open-Closed).
"""

from __future__ import annotations

from functools import lru_cache

from app.core.config import Settings, get_settings
from app.domain.interfaces.listing_provider import ListingProvider
from app.providers.listing.authorized_provider import AuthorizedListingProvider
from app.providers.listing.demo_fixture_provider import DemoFixtureProvider


def build_listing_provider(settings: Settings) -> ListingProvider:
    if settings.listing_provider == "authorized":
        return AuthorizedListingProvider(
            base_url=settings.parse_bot_base_url,
            api_key=settings.parse_bot_api_key,
            max_search_pages=settings.parse_bot_max_search_pages,
            include_rent=settings.parse_bot_include_rent,
            detail_enrich_limit=settings.parse_bot_detail_enrich_limit,
        )
    return DemoFixtureProvider(fixtures_dir=settings.fixtures_dir)


@lru_cache
def get_listing_provider() -> ListingProvider:
    return build_listing_provider(get_settings())
