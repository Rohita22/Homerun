"""``python -m app.scraper`` — run one scrape now (manual refresh or cron).

Flags: ``--if-due`` only scrape when the schedule says a run is due; ``--headed`` show the browser;
``--geocode-only`` just fill in missing coordinates; ``--push URL`` then ship the catalog to a
server's ``/api/admin/ingest`` (token from ``--token`` or ``ADMIN_TOKEN``), for hosts such as IBM Z
that cannot run a browser; ``--push-only URL`` skips the scrape.
"""

from __future__ import annotations

import argparse
import json
import os

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.scraper.service import run_scrape, seconds_until_due


def main() -> None:
    parser = argparse.ArgumentParser(description="Scrape PropertyGuru into the Homerun database.")
    parser.add_argument("--if-due", action="store_true", help="skip unless a run is due")
    parser.add_argument("--headed", action="store_true", help="show the browser window")
    parser.add_argument("--mode", choices=("auto", "full", "quick"), default="full",
                        help="full crawl (default), quick top-pages refresh, or auto (what the scheduler uses)")
    parser.add_argument("--targets", help='override, e.g. "hdb-for-sale:2,condo-for-sale:1"')
    parser.add_argument("--geocode-only", action="store_true", help="only fill in missing coordinates")
    parser.add_argument("--push", metavar="URL", help="after scraping, push the catalog to this server")
    parser.add_argument("--push-only", metavar="URL", help="push the existing catalog, no scrape")
    parser.add_argument("--token", default=os.environ.get("ADMIN_TOKEN", ""), help="admin token for --push")
    args = parser.parse_args()

    configure_logging()
    if args.geocode_only:
        from app.scraper.geocode import geocode_missing
        from app.scraper.parser import PROVIDER

        print(json.dumps(geocode_missing(PROVIDER, limit=5000), indent=2))
        return
    if args.push_only:
        print(json.dumps(_push(args.push_only, args.token), indent=2))
        return
    settings = get_settings().model_copy()
    if args.headed:
        settings.scrape_headless = False
    if args.targets:
        settings.scrape_targets = args.targets
    if args.if_due and seconds_until_due(settings) > 0:
        print("not due yet; nothing to do")
        return
    print(json.dumps(run_scrape(settings, mode=args.mode), indent=2))
    if args.push:
        print(json.dumps(_push(args.push, args.token), indent=2))


def _push(url: str, token: str) -> dict:
    from app.scraper.push import push_catalog

    if not token:
        raise SystemExit("pass --token or set ADMIN_TOKEN to push")
    return push_catalog(url, token)


if __name__ == "__main__":
    main()
