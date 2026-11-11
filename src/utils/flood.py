"""Flood-control helpers for bulk Telegram API calls.

Telegram restricts or freezes bot tokens that fire bursts of bulk requests.
Every bulk operation in POPPY ROSE must pace itself and honour Telegram's
``RetryAfter`` (flood control) responses instead of retrying immediately.
"""
from __future__ import annotations

import asyncio
import logging

from telegram.error import RetryAfter

log = logging.getLogger("poppy_rose.flood")


def retry_after_seconds(exc: RetryAfter) -> int:
    """Whole seconds to wait for a ``RetryAfter`` error.

    Handles both ``int`` seconds (PTB v20+) and ``datetime.timedelta``
    (older PTB versions), so the code keeps working across upgrades.
    """
    value = getattr(exc, "retry_after", 1)
    total_seconds = getattr(value, "total_seconds", None)
    if callable(total_seconds):
        value = total_seconds()
    try:
        return max(1, int(value)) + 1
    except (TypeError, ValueError):
        return 5


async def flood_safe(coro_factory, *, retries: int = 3):
    """Await ``coro_factory()`` and retry (with sleeps) on flood control.

    ``coro_factory`` must be a zero-argument callable returning a *new*
    coroutine on every call, e.g. ``lambda: bot.copy_message(...)``.
    """
    attempt = 0
    while True:
        try:
            return await coro_factory()
        except RetryAfter as exc:
            attempt += 1
            if attempt > retries:
                raise
            wait = retry_after_seconds(exc)
            log.warning(
                "Flood control | sleeping %ss | attempt %s/%s",
                wait,
                attempt,
                retries,
            )
            await asyncio.sleep(wait)
