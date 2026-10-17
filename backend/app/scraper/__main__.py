"""``python -m app.scraper`` — run one scrape now (manual refresh or cron).

Flags: ``--if-due`` only scrape when the schedule says a run is due; ``--headed`` show the browser.
"""

from __future__ import annotations

import argparse
import json

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.scraper.service import run_scrape, seconds_until_due


def main() -> None:
    parser = argparse.ArgumentParser(description="Scrape PropertyGuru into the Homerun database.")
    parser.add_argument("--if-due", action="store_true", help="skip unless a run is due")
    parser.add_argument("--headed", action="store_true", help="show the browser window")
    parser.add_argument("--targets", help='override, e.g. "hdb-for-sale:2,condo-for-sale:1"')
    args = parser.parse_args()

    configure_logging()
    settings = get_settings().model_copy()
    if args.headed:
        settings.scrape_headless = False
    if args.targets:
        settings.scrape_targets = args.targets
    if args.if_due and seconds_until_due(settings) > 0:
        print("not due yet; nothing to do")
        return
    print(json.dumps(run_scrape(settings), indent=2))


if __name__ == "__main__":
    main()
