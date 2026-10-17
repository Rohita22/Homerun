"""Single source of truth for "now" across the codebase.

``datetime.utcnow()`` is deprecated since Python 3.12. We still want naive UTC datetimes
everywhere (SQLite has no timezone type, and every entity/model in this codebase consistently
uses naive-UTC), so this wraps the timezone-aware replacement and strips the tzinfo back off
rather than scattering ``datetime.now(timezone.utc).replace(tzinfo=None)`` through every file.
"""

from __future__ import annotations

from datetime import UTC, datetime


def utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)
