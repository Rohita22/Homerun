"""Factory selecting the active ``ListingProvider`` from ``Settings.listing_provider``
(PRD section 6: "inject through environment variable LISTING_PROVIDER"). This is the single
place that knows about concrete provider classes; everything else depends on the
``ListingProvider`` protocol only (Dependency Inversion / Open-Closed).
"""

from __future__ import annotations

from functools import lru_cache

from app.core.config import Settings, get_settings
from app.domain.interfaces.listing_provider import ListingProvider
from app.providers.listing.scraped_provider import ScrapedListingProvider


def build_listing_provider(settings: Settings) -> ListingProvider:
    # The whole pipeline runs on scraped PropertyGuru data only; ``LISTING_PROVIDER`` is ignored.
    return ScrapedListingProvider()


@lru_cache
def get_listing_provider() -> ListingProvider:
    return build_listing_provider(get_settings())
