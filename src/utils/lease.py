"""MongoDB-backed leader election for multiple instances sharing ONE token.

Why this exists
---------------
Telegram allows only ONE concurrent ``getUpdates()`` consumer per bot token:
a second instance polling with the same token receives ``409 Conflict`` and
the polling loops fight each other. To run the bot across several Render
projects (free-tier hour splitting) we therefore give every instance the same
code + token, but only the *lease holder* starts PTB's updater polling.

How it works
------------
- All instances share one MongoDB database (``instance_leases`` collection,
  single document ``_id="poller"``).
- Every LEASE_POLL_SECONDS each awake instance runs :func:`try_acquire`,
  an atomic ``find_one_and_update`` that wins only if the lease is ours OR
  already expired. Two instances can never both win the same tick.
- The holder renews with a LEASE_TTL_SECONDS deadline. If the holder dies,
  crashes or is put to sleep by Render, the lease expires and the next
  instance that tries takes over — automatic failover within ~TTL+POLL.
- Standbys still run the Flask/Waitress HTTP server (health + dashboard API)
  so Render keeps them deployed and the dashboard can see them.
- If MongoDB is unreachable the loop treats leadership as *unknown* and keeps
  its current behaviour (a leader keeps polling through a Mongo blip instead
  of handing the token to nobody).
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from telegram import Update
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from config import (
    HA_ENABLED,
    INSTANCE_ID,
    LEASE_POLL_SECONDS,
    LEASE_TTL_SECONDS,
)
from src.database.db_core import db
from src.utils.status import record_error

log = logging.getLogger("poppy_rose.lease")

LEASE_COLLECTION = "instance_leases"
LEASE_ID = "poller"

_leases = db[LEASE_COLLECTION]

_state: dict = {
    "is_leader": False,
    "polling": False,
    # iso timestamp when this instance became leader (else None)
    "since": None,
    # unix timestamp when our lease expires (else None)
    "expires_at": None,
    "last_attempt": None,
    "last_error": "",
}

# True once shutdown begins so late failures are not recorded as errors.
_shutting_down = False


def get_state() -> dict:
    """Snapshot of lease state for the dashboard API (JSON-friendly)."""
    now = datetime.now(timezone.utc)
    expires_in = None
    if _state["is_leader"] and _state["expires_at"]:
        expires_in = round(_state["expires_at"] - now.timestamp(), 1)
    return {
        "is_leader": bool(_state["is_leader"]),
        "polling": bool(_state["polling"]),
        "since": _state["since"],
        "lease_expires_in": expires_in,
        "last_attempt": _state["last_attempt"],
        "last_error": _state["last_error"],
        "instance_id": INSTANCE_ID,
        "ha_enabled": HA_ENABLED,
    }


async def _ensure_doc() -> None:
    """Create the lease document once so ``try_acquire`` can use an atomic $or."""
    now = datetime.now(timezone.utc)
    try:
        await _leases.update_one(
            {"_id": LEASE_ID},
            {
                "$setOnInsert": {
                    "holder": "",
                    # born expired so the very first instance can claim it
                    "expires_at": now - timedelta(seconds=1),
                    "created_at": now,
                }
            },
            upsert=True,
        )
    except DuplicateKeyError:
        # Lost the insert race — another instance created it first. Fine.
        pass


async def try_acquire() -> bool:
    """Atomically acquire (or renew) the poller lease.

    Returns True when this instance holds the lease after the call.
    Raises on MongoDB failure so the caller can treat leadership as unknown.
    """
    now = datetime.now(timezone.utc)
    _state["last_attempt"] = now.isoformat()
    await _ensure_doc()

    doc = await _leases.find_one_and_update(
        {
            "_id": LEASE_ID,
            "$or": [
                {"holder": INSTANCE_ID},      # we already hold it → renew
                {"expires_at": {"$lte": now}},  # holder gone → steal
            ],
        },
        {
            "$set": {
                "holder": INSTANCE_ID,
                "expires_at": now + timedelta(seconds=LEASE_TTL_SECONDS),
                "renewed_at": now,
            }
        },
        return_document=ReturnDocument.AFTER,
    )

    mine = bool(doc and doc.get("holder") == INSTANCE_ID)
    if mine:
        if not _state["is_leader"]:
            log.info(
                "Instance %s acquired the poller lease — taking over Telegram polling",
                INSTANCE_ID,
            )
            _state["since"] = now.isoformat()
        _state["is_leader"] = True
        _state["expires_at"] = (now + timedelta(seconds=LEASE_TTL_SECONDS)).timestamp()
        _state["last_error"] = ""
    else:
        if _state["is_leader"]:
            log.warning(
                "Instance %s LOST the poller lease — another instance is now the leader",
                INSTANCE_ID,
            )
        _state["is_leader"] = False
        _state["since"] = None
        _state["expires_at"] = None
    return mine


async def release() -> None:
    """Expire our own lease on shutdown so a standby takes over immediately."""
    if not _state["is_leader"]:
        return
    now = datetime.now(timezone.utc)
    try:
        result = await _leases.update_one(
            {"_id": LEASE_ID, "holder": INSTANCE_ID},
            {"$set": {"expires_at": now, "released_at": now}},
        )
        if result.matched_count:
            log.info("Instance %s released the poller lease on shutdown", INSTANCE_ID)
    except Exception as exc:  # never block shutdown on Mongo
        log.warning("Could not release lease during shutdown | %s", exc)
    finally:
        _state["is_leader"] = False
        _state["polling"] = False
        _state["since"] = None
        _state["expires_at"] = None


def _install_signal_handlers(stop: asyncio.Event) -> None:
    """Ask the event loop to set ``stop`` on SIGTERM/SIGINT (Render sends SIGTERM)."""
    import signal

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop.set)
        except (NotImplementedError, RuntimeError, ValueError):
            # e.g. Windows ProactorEventLoop — Ctrl+C still raises
            # KeyboardInterrupt, which lands in the same finally-block path.
            log.debug("Signal handler for %s not installable on this platform", sig)


async def leader_loop(app, stop: asyncio.Event | None = None) -> None:
    """Run the PTB lifecycle with polling gated by the leader lease.

    Mirrors Application.run_polling's documented order:
      initialize → post_init → (gained lease) start_polling → start
      … → (lost lease) stop polling → stop → post_stop → shutdown → post_shutdown
    but start/stop of *polling* flips on every lease change while the process,
    HTTP server and application stay alive the whole time.

    ``stop`` may be provided by tests to terminate the loop deterministically;
    in production it is created here and set by SIGTERM/SIGINT handlers.
    """
    stop = stop or asyncio.Event()
    _install_signal_handlers(stop)

    log.info(
        "HA loop starting | instance=%s | ttl=%ss | poll=%.1fs",
        INSTANCE_ID,
        LEASE_TTL_SECONDS,
        LEASE_POLL_SECONDS,
    )

    try:
        await app.initialize()
        if app.post_init:
            await app.post_init(app)
        await app.start()

        while not stop.is_set():
            try:
                acquired: bool | None = await try_acquire()
            except Exception as exc:
                # Mongo unreachable → leadership unknown → KEEP current role.
                acquired = None
                _state["last_error"] = f"lease acquire failed: {type(exc).__name__}: {exc}"
                if not _shutting_down:
                    record_error(f"Lease: {type(exc).__name__}: {exc}")
                log.warning("Leader lease check failed | %s", exc)

            if acquired is True and not app.updater.running:
                try:
                    await app.updater.start_polling(
                        poll_interval=0.0,
                        bootstrap_retries=3,
                        allowed_updates=Update.ALL_TYPES,
                        drop_pending_updates=False,
                        error_callback=lambda exc: app.create_task(
                            app.process_error(error=exc, update=None)
                        ),
                    )
                    _state["polling"] = True
                    log.info(
                        "Instance %s is LEADER — Telegram polling started",
                        INSTANCE_ID,
                    )
                except Exception as exc:
                    _state["polling"] = False
                    _state["last_error"] = f"polling start failed: {type(exc).__name__}: {exc}"
                    if not _shutting_down:
                        record_error(f"PollingStart: {type(exc).__name__}: {exc}")
                    log.exception("Could not start polling; will retry next tick")
            elif acquired is False and app.updater.running:
                await app.updater.stop()
                _state["polling"] = False
                log.info(
                    "Instance %s is a STANDBY — Telegram polling stopped "
                    "(another instance owns the token)",
                    INSTANCE_ID,
                )
            # acquired is None → keep whatever polling state we already had.

            try:
                await asyncio.wait_for(stop.wait(), timeout=LEASE_POLL_SECONDS)
            except asyncio.TimeoutError:
                pass
    finally:
        _shutting_down = True
        try:
            if app.updater and app.updater.running:
                await app.updater.stop()
        except Exception:
            log.exception("Error stopping updater during shutdown")
        _state["polling"] = False

        try:
            await release()
        except Exception:
            log.exception("Error releasing lease during shutdown")

        # Same teardown order as Application.run_polling.
        try:
            await app.stop()
            if app.post_stop:
                await app.post_stop(app)
            await app.shutdown()
            if app.post_shutdown:
                await app.post_shutdown(app)
        except Exception:
            log.exception("Error during application shutdown")
        log.info("HA loop stopped | instance=%s", INSTANCE_ID)


