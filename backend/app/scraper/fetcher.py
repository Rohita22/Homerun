"""Playwright page fetcher for PropertyGuru search-result pages.

PropertyGuru sits behind Cloudflare. Empirically (see README "Live listing data") a *fresh*
browser loads any result page fine, but a session that keeps navigating gets a "Just a moment..."
challenge. So every page gets its own short-lived browser, pages are spaced out with jitter, and a
blocked page is retried with backoff in a new browser. We deliberately do NOT try to defeat the
challenge (no stealth plugins, proxy rotation or CAPTCHA solving): if a page stays blocked we
skip it and report it, rather than escalate.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass

from app.core.logging import get_logger

logger = get_logger(__name__)

BASE_URL = "https://www.propertyguru.com.sg"
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)
_NEXT_DATA_RE = re.compile(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.DOTALL)
_SKIPPED_RESOURCES = {"image", "media", "font"}


class PageBlockedError(RuntimeError):
    """Cloudflare challenge / non-200 / missing embedded data."""


@dataclass
class PageResult:
    cards: list[dict]  # each is one ``listingData`` dict
    current_page: int
    total_pages: int


def page_url(path: str, page: int) -> str:
    suffix = "" if page <= 1 else f"/{page}"
    # Plain paths only: any query string (even ?sort=...) trips the Cloudflare challenge.
    return f"{BASE_URL}/{path.strip('/')}{suffix}"


def extract_page(html: str) -> PageResult:
    match = _NEXT_DATA_RE.search(html)
    if not match:
        raise PageBlockedError("no __NEXT_DATA__ in page (likely a bot challenge)")
    try:
        data = json.loads(match.group(1))["props"]["pageProps"]["pageData"]["data"]
        listings = data["listingsData"]
        pagination = data.get("paginationData") or {}
    except (KeyError, TypeError, json.JSONDecodeError) as exc:
        raise PageBlockedError(f"unexpected page structure: {exc!r}") from exc
    cards = [item["listingData"] for item in listings if isinstance(item, dict) and "listingData" in item]
    return PageResult(
        cards=cards,
        current_page=int(pagination.get("currentPage") or 1),
        total_pages=int(pagination.get("totalPages") or 1),
    )


class PropertyGuruFetcher:
    def __init__(self, headless: bool = True, max_retries: int = 3, timeout_s: float = 45.0) -> None:
        self._headless = headless
        self._max_retries = max_retries
        self._timeout_ms = int(timeout_s * 1000)
        self._playwright = None

    def __enter__(self) -> PropertyGuruFetcher:
        from playwright.sync_api import sync_playwright  # lazy: app runs without playwright installed

        self._playwright = sync_playwright().start()
        return self

    def __exit__(self, *exc: object) -> None:
        if self._playwright is not None:
            self._playwright.stop()
            self._playwright = None

    def _fetch_once(self, url: str) -> PageResult:
        assert self._playwright is not None, "use PropertyGuruFetcher as a context manager"
        browser = self._playwright.chromium.launch(headless=self._headless)
        try:
            context = browser.new_context(user_agent=USER_AGENT, locale="en-SG")
            context.route(
                "**/*",
                lambda route: route.abort()
                if route.request.resource_type in _SKIPPED_RESOURCES
                else route.continue_(),
            )
            page = context.new_page()
            response = page.goto(url, wait_until="domcontentloaded", timeout=self._timeout_ms)
            status = response.status if response else 0
            if status != 200:
                raise PageBlockedError(f"HTTP {status}")
            try:
                page.wait_for_selector("script#__NEXT_DATA__", state="attached", timeout=15_000)
            except Exception as exc:  # noqa: BLE001 - playwright TimeoutError
                raise PageBlockedError(f"challenge page ({page.title()[:40]!r})") from exc
            return extract_page(page.content())
        finally:
            browser.close()

    def fetch(self, path: str, page: int) -> PageResult:
        url = page_url(path, page)
        for attempt in range(1, self._max_retries + 1):
            try:
                result = self._fetch_once(url)
                logger.info("scrape_page_ok path=%s page=%d cards=%d total_pages=%d",
                            path, page, len(result.cards), result.total_pages)
                return result
            except PageBlockedError as exc:
                wait = 30 * attempt * attempt
                logger.warning("scrape_page_blocked path=%s page=%d attempt=%d/%d reason=%s",
                               path, page, attempt, self._max_retries, exc)
                if attempt == self._max_retries:
                    raise
                time.sleep(wait)
            except Exception as exc:  # noqa: BLE001 - network/browser crash: retry the same way
                logger.warning("scrape_page_error path=%s page=%d attempt=%d/%d error=%r",
                               path, page, attempt, self._max_retries, exc)
                if attempt == self._max_retries:
                    raise PageBlockedError(f"browser error: {exc!r}") from exc
                time.sleep(15 * attempt)
        raise PageBlockedError("unreachable")  # pragma: no cover
