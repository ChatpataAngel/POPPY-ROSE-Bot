"""In-process health counters for the /ping diagnostics command.

Error summaries are exposed through the dashboard status API and Telegram
/ping command, so they are sanitized before being stored.
"""
from __future__ import annotations

from datetime import datetime, timezone

from src.utils.logging_config import redact_secrets

_STARTED_AT = datetime.now(timezone.utc)

_error_count = 0
_last_error_at: datetime | None = None
_last_error_text = ""


def record_error(text: str) -> None:
    """Record a sanitized error seen by the bot or polling lifecycle."""
    global _error_count, _last_error_at, _last_error_text
    _error_count += 1
    _last_error_at = datetime.now(timezone.utc)
    _last_error_text = redact_secrets(text)


def error_status() -> tuple[int, str, datetime | None]:
    """Return (count_since_start, sanitized last error text, last error time)."""
    return _error_count, _last_error_text, _last_error_at


def started_at() -> datetime:
    """Return when this process started (UTC)."""
    return _STARTED_AT
