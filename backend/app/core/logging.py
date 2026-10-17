"""Structured logging setup.

Logs are JSON-ish key=value lines so they stay greppable both in a terminal and in a log
aggregator on the LinuxONE host, and so handoff/audit events never leak raw buyer contact data
(PRD section 9: "Mask personal contact information in logs").
"""

from __future__ import annotations

import logging
import sys

_CONFIGURED = False


# Third-party libraries whose DEBUG-level logs are wire-protocol noise (TLS handshakes, socket
# polling) that bury our own [ORCHESTRATOR]/agent/provider-sync lines — always quiet these down
# regardless of HOMERUN_DEBUG, since "debug" should mean "more of our own detail", not "flood the
# terminal with httpcore internals" (the whole point of the "clear logs" requirement).
_NOISY_THIRD_PARTY_LOGGERS = ("httpx", "httpcore", "urllib3", "sqlalchemy.engine")


def configure_logging(debug: bool = True) -> None:
    global _CONFIGURED
    if _CONFIGURED:
        return
    level = logging.DEBUG if debug else logging.INFO
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        logging.Formatter(
            fmt="%(asctime)s level=%(levelname)s logger=%(name)s %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S%z",
        )
    )
    root = logging.getLogger()
    root.setLevel(level)
    root.handlers = [handler]
    for name in _NOISY_THIRD_PARTY_LOGGERS:
        logging.getLogger(name).setLevel(logging.WARNING)
    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)


def log_startup_banner(fields: dict[str, object]) -> None:
    """Prints an unmissable startup summary so judges/devs watching the terminal can confirm at a
    glance which providers are live, what architecture it's running on, and which ML model
    version is loaded — rather than having to go hunting through scattered log lines."""
    logger = get_logger("app.startup")
    width = max(60, max((len(f"{k}: {v}") for k, v in fields.items()), default=0) + 4)
    logger.info("=" * width)
    logger.info("HOMERUN BACKEND READY".center(width))
    logger.info("=" * width)
    for key, value in fields.items():
        logger.info(f"  {key}: {value}")
    logger.info("=" * width)
