"""Paced broadcast fan-out shared by /broadcast and /announce.

Sending one copy to every group as fast as possible is the classic way a
bot token gets frozen by Telegram's anti-spam systems. This module paces
every send with ``BROADCAST_DELAY``, retries flood-control responses and
stops entirely after too many consecutive failures.
"""
from __future__ import annotations

import asyncio
import logging

from telegram.error import Forbidden, TelegramError

from config import BROADCAST_DELAY
from src.database.db_core import deactivate_group, get_active_groups
from src.utils.flood import flood_safe

log = logging.getLogger("poppy_rose.broadcast")

# Abort the whole run when this many sends fail back-to-back; continuing
# would just keep hammering Telegram (and risk a token restriction).
MAX_CONSECUTIVE_FAILURES = 8

INACTIVE_MARKERS = (
    "forbidden",
    "bot was kicked",
    "chat not found",
    "user is deactivated",
    "peer_id_invalid",
)


async def copy_to_active_groups(source_message) -> dict:
    """Copy ``source_message`` to every active group, paced and flood-safe.

    Returns a summary dict: ``sent``, ``failed`` and ``aborted``.
    """
    sent = 0
    failed = 0
    consecutive_failures = 0
    aborted = False

    async for doc in get_active_groups():
        chat_id = doc["chat_id"]

        try:
            await flood_safe(lambda: source_message.copy(chat_id=chat_id))
            sent += 1
            consecutive_failures = 0
        except TelegramError as exc:
            failed += 1
            consecutive_failures += 1

            error_text = str(exc).lower()
            if isinstance(exc, Forbidden) or any(
                marker in error_text for marker in INACTIVE_MARKERS
            ):
                try:
                    await deactivate_group(chat_id)
                except Exception:
                    log.exception(
                        "Could not deactivate group | chat=%s",
                        chat_id,
                    )

            if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                aborted = True
                log.warning(
                    "Broadcast aborted after %s consecutive failures",
                    consecutive_failures,
                )
                break

        # Pace every single send so bulk copies never form a burst.
        await asyncio.sleep(BROADCAST_DELAY)

    return {"sent": sent, "failed": failed, "aborted": aborted}
