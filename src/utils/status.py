"""In-process health counters for the /ping diagnostics command.

Lives in src.utils (not src.__main__) so both the shared error handler and
the /ping command can import it without a circular import.
"""
from __future__ import annotations

from datetime import datetime, timezone

_STARTED_AT = datetime.now(timezone.utc)

_error_count = 0
_last_error_at: datetime | None = None
_last_error_text = ""


def record_error(text: str) -> None:
    """Record an error seen by the PTB error handler (called for every update error)."""
    global _error_count, _last_error_at, _last_error_text
    _error_count += 1
    _last_error_at = datetime.now(timezone.utc)
    _last_error_text = text


def error_status() -> tuple[int, str, datetime | None]:
    """Return (count_since_start, last_error_text, last_error_at)."""
    return _error_count, _last_error_text, _last_error_at


def started_at() -> datetime:
    """Return when this process started (UTC)."""
    return _STARTED_AT
