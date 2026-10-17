"""One full scrape run: fetch pages -> normalize -> upsert into ``properties`` -> bookkeeping.

Commits after every target so a crash or a blocked later target never loses earlier pages. The
run is recorded in ``scrape_runs`` which also drives scheduling ("is a refresh due?") and the
"last refreshed" notice shown to buyers.
"""

from __future__ import annotations

import os
import random
import threading
import time
from datetime import timedelta

from sqlalchemy import select

from app.core.config import Settings, get_settings
from app.core.logging import get_logger
from app.core.time import utcnow
from app.db.base import SessionLocal, init_db
from app.db.models import PropertyRow, ScrapeRunRow
from app.repositories.property_repository import PropertyRepository
from app.scraper.fetcher import PageBlockedError, PropertyGuruFetcher
from app.scraper.parser import PROVIDER, parse_card
from app.scraper.towns import get_town_resolver

logger = get_logger(__name__)

_run_lock = threading.Lock()
_CONSECUTIVE_FAILURE_LIMIT = 3  # stop hammering a target that keeps getting blocked
_RUNNING_GUARD = timedelta(hours=3)


def last_successful_run(db) -> ScrapeRunRow | None:  # noqa: ANN001
    return db.execute(
        select(ScrapeRunRow)
        .where(ScrapeRunRow.status.in_(("ok", "partial")))
        .order_by(ScrapeRunRow.started_at.desc())
    ).scalars().first()


def _pid_alive(pid: int | None) -> bool:
    if not pid:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _is_live_run(row: ScrapeRunRow) -> bool:
    """A 'running' row only counts while the process that wrote it is still alive (a killed or
    crashed run must not block the schedule)."""
    pid = (row.detail_json or {}).get("pid")
    return row.status == "running" and _pid_alive(pid) and utcnow() - row.started_at < _RUNNING_GUARD


def _is_full(row: ScrapeRunRow) -> bool:
    # Runs recorded before quick mode existed have no "mode" and were full crawls.
    return (row.detail_json or {}).get("mode", "full") == "full"


def choose_mode(settings: Settings) -> str:
    """'full' when no full crawl succeeded within ``scrape_full_every_hours``, else 'quick'."""
    db = SessionLocal()
    try:
        rows = db.execute(
            select(ScrapeRunRow)
            .where(ScrapeRunRow.status.in_(("ok", "partial")))
            .order_by(ScrapeRunRow.started_at.desc())
        ).scalars().all()
        last_full = next((r for r in rows if _is_full(r)), None)
        if last_full is None:
            return "full"
        age = utcnow() - last_full.started_at
        return "full" if age >= timedelta(hours=settings.scrape_full_every_hours) else "quick"
    finally:
        db.close()


def seconds_until_due(settings: Settings | None = None) -> float:
    """0 when a scrape should run now. A fully failed attempt is retried after 1h, not 12h."""
    settings = settings or get_settings()
    db = SessionLocal()
    try:
        rows = db.execute(select(ScrapeRunRow).order_by(ScrapeRunRow.started_at.desc())).scalars().all()
        latest = next((r for r in rows if r.status != "running" or _is_live_run(r)), None)
        if latest is None:
            return 0.0
        if latest.status == "running":
            return 300.0  # another live run (e.g. cron CLI) is in progress; look again shortly
        interval = timedelta(hours=settings.scrape_interval_hours)
        if latest.status == "failed":
            interval = min(interval, timedelta(hours=1))
        ref = latest.finished_at or latest.started_at
        return max(0.0, (ref + interval - utcnow()).total_seconds())
    finally:
        db.close()


def _sync_listing(db, repo: PropertyRepository, listing, now) -> str:  # noqa: ANN001
    """Compare with what we hold: unchanged listings only get their last-seen time bumped (so they
    are not retired); new or changed ones are written in full. Returns new/updated/unchanged."""
    row = db.get(PropertyRow, listing.listing_id)
    if row is None:
        repo.upsert(listing)
        return "new"
    status = listing.status.value if hasattr(listing.status, "value") else listing.status
    if row.price == listing.asking_price_sgd and row.status == status and row.attributes_json == listing.attributes:
        row.fetched_at = now
        return "unchanged"
    repo.upsert(listing)
    return "updated"


def run_scrape(
    settings: Settings | None = None, fetcher: PropertyGuruFetcher | None = None, mode: str = "full"
) -> dict:
    """Run one scrape. ``mode`` is 'full', 'quick' or 'auto' (pick by time since the last full crawl).
    Returns a summary dict; never raises for page-level failures."""
    settings = settings or get_settings()
    if mode == "auto":
        mode = choose_mode(settings)
    if not _run_lock.acquire(blocking=False):
        logger.info("scrape_skipped reason=already_running_in_this_process")
        return {"status": "skipped"}
    try:
        return _run_scrape_locked(settings, fetcher, mode)
    finally:
        _run_lock.release()


def _run_scrape_locked(settings: Settings, fetcher: PropertyGuruFetcher | None, mode: str) -> dict:
    init_db()
    db = SessionLocal()
    run = ScrapeRunRow(started_at=utcnow(), status="running", detail_json={"pid": os.getpid(), "mode": mode})
    db.add(run)
    db.commit()
    started = utcnow()
    resolver = get_town_resolver()
    pages_ok = pages_failed = seen = 0
    counts = {"new": 0, "updated": 0, "unchanged": 0}
    per_target: dict[str, dict] = {}
    error: str | None = None

    try:
        owns_fetcher = fetcher is None
        fetcher = fetcher or PropertyGuruFetcher(
            headless=settings.scrape_headless, max_retries=settings.scrape_max_retries
        )
        if owns_fetcher:
            fetcher.__enter__()
        try:
            repo = PropertyRepository(db)
            for path, max_pages in settings.scrape_target_list:
                stats = per_target[path] = {"pages_ok": 0, "pages_failed": 0, "listings": 0}
                consecutive_failures = 0
                total_pages = max_pages
                if mode == "quick":
                    max_pages = min(max_pages, settings.scrape_quick_pages)
                page = 1
                while page <= min(max_pages, total_pages):
                    try:
                        result = fetcher.fetch(path, page)
                    except PageBlockedError as exc:
                        pages_failed += 1
                        stats["pages_failed"] += 1
                        consecutive_failures += 1
                        logger.warning("scrape_page_skipped path=%s page=%d reason=%s", path, page, exc)
                        if consecutive_failures >= _CONSECUTIVE_FAILURE_LIMIT:
                            logger.warning("scrape_target_aborted path=%s reason=repeated_blocks", path)
                            break
                    else:
                        consecutive_failures = 0
                        total_pages = result.total_pages
                        pages_ok += 1
                        stats["pages_ok"] += 1
                        now = utcnow()
                        for card in result.cards:
                            parsed = parse_card(card, resolver, now)
                            if parsed is None:
                                continue
                            listing, agent, link = parsed
                            outcome = _sync_listing(db, repo, listing, now)
                            counts[outcome] += 1
                            if outcome == "unchanged":
                                seen += 1
                                stats["listings"] += 1
                                continue
                            if agent is not None and link is not None:
                                repo.upsert_agent(agent)
                                db.flush()
                                repo.replace_link(link)
                            seen += 1
                            stats["listings"] += 1
                        db.commit()
                        if not result.cards:
                            break
                    page += 1
                    if page <= min(max_pages, total_pages):
                        time.sleep(settings.scrape_delay_seconds * random.uniform(0.75, 1.5))
                db.commit()
        finally:
            if owns_fetcher:
                fetcher.__exit__(None, None, None)

        deactivated = 0
        if pages_ok > 0 and mode == "full":  # only age listings out after a run that actually saw something
            cutoff = utcnow() - timedelta(hours=settings.scrape_stale_after_hours)
            deactivated = repo.deactivate_unseen(PROVIDER, cutoff)
            db.commit()
    except Exception as exc:  # noqa: BLE001 - record and report, never crash the scheduler
        logger.exception("scrape_run_crashed")
        error = repr(exc)
        db.rollback()
        deactivated = 0

    if pages_ok > 0:  # best effort: coordinates feed the map and the commute estimate
        try:
            from app.scraper.geocode import geocode_missing

            geocode_missing(PROVIDER)
        except Exception:  # noqa: BLE001 - a geocoder outage must not fail a good scrape
            logger.exception("geocode_after_scrape_failed")

    status = "failed" if pages_ok == 0 else ("partial" if pages_failed or error else "ok")
    run = db.get(ScrapeRunRow, run.run_id)
    run.finished_at = utcnow()
    run.status = status
    run.pages_ok, run.pages_failed = pages_ok, pages_failed
    run.listings_seen, run.listings_deactivated = seen, deactivated
    run.detail_json = {"pid": os.getpid(), "targets": per_target, "error": error,
                       "mode": mode, **counts}
    db.commit()
    db.close()

    summary = {
        "status": status, "pages_ok": pages_ok, "pages_failed": pages_failed,
        "listings_seen": seen, "listings_deactivated": deactivated,
        "mode": mode, **counts, "elapsed_s": round((utcnow() - started).total_seconds()), "targets": per_target,
    }
    logger.info("scrape_run_complete %s", summary)
    return summary
