"""In-process timer: scrape every ``SCRAPE_INTERVAL_HOURS`` (default 12).

Due-ness comes from the ``scrape_runs`` table, not from process uptime, so restarts (including
``uvicorn --reload``) neither skip a due run nor re-scrape right after a fresh one. For a server
that should scrape independently of the API, run ``python -m app.scraper`` from cron instead and
set ``SCRAPE_ENABLED=false`` for the API process.
"""

from __future__ import annotations

import asyncio

from app.core.config import Settings
from app.core.logging import get_logger
from app.scraper.service import run_scrape, seconds_until_due

logger = get_logger(__name__)
_STARTUP_DELAY_S = 10
_MAX_SLEEP_S = 600  # wake regularly so a changed clock / cancelled task is handled promptly


async def scrape_forever(settings: Settings) -> None:
    logger.info("scrape_scheduler_started interval_hours=%s targets=%s",
                settings.scrape_interval_hours, settings.scrape_target_list)
    await asyncio.sleep(_STARTUP_DELAY_S)
    while True:
        try:
            wait = await asyncio.to_thread(seconds_until_due, settings)
            if wait > 0:
                await asyncio.sleep(min(wait, _MAX_SLEEP_S))
                continue
            logger.info("scrape_run_starting")
            await asyncio.to_thread(run_scrape, settings)
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 - the timer must survive any single failure
            logger.exception("scrape_scheduler_error")
            await asyncio.sleep(300)
