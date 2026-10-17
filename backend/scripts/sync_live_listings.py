#!/usr/bin/env python
"""Thin CLI wrapper so the live catalog can be refreshed as
``python scripts/sync_live_listings.py`` from the ``backend/`` directory (same convention as
``train_valuation_model.py``). Delegates entirely to ``app.bootstrap``: if ``LISTING_PROVIDER``
is ``demo_fixture`` this just re-syncs the static fixtures; if it's ``authorized`` this pulls
fresh live PropertyGuru listings via Parse.bot into the local catalog.
"""

from app.bootstrap import bootstrap
from app.core.logging import configure_logging

if __name__ == "__main__":
    configure_logging()
    bootstrap()
