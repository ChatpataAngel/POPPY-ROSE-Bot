"""REST API served by every instance for the frontend dashboard (frontend/).

Endpoints (all instances expose all of them — the dashboard fans out to the
four Render URLs and merges the results):

  GET  /api/status             public — role (leader/follower), uptime,
                                         errors, lease info, bot username
  GET  /api/health             public — 200/503 like /health, with CORS
  GET  /api/stats              X-API-Key — user/group counts from MongoDB
  POST /api/leadership/release X-API-Key — expire THIS instance's lease so a
                                         standby takes over (planned re-sync)

Flask routes run on Waitress worker threads, NOT on the bot's asyncio loop,
so privileged endpoints use a small thread-safe synchronous pymongo client
instead of the shared motor client (which is bound to the main loop).
"""
from __future__ import annotations

import hmac
import logging
from datetime import datetime, timezone

from flask import jsonify, request

import config
from src.utils import lease
from src.utils.status import error_status, started_at

log = logging.getLogger("poppy_rose.api")

_sync_client = None


def _mongo():
    """Lazily build ONE thread-safe synchronous client for Flask workers."""
    global _sync_client
    if _sync_client is None:
        from pymongo import MongoClient

        _sync_client = MongoClient(
            config.MONGO_DB_URI,
            serverSelectionTimeoutMS=4000,
            connectTimeoutMS=4000,
        )
    return _sync_client


def _do_stats() -> dict:
    """Aggregate counts from the shared database (thread-safe sync client)."""
    database = _mongo()[config.DB_NAME]
    return {
        "users": database["users"].estimated_document_count(),
        "groups": database["groups"].estimated_document_count(),
        "active_groups": database["groups"].count_documents(
            {"active": {"$ne": False}}
        ),
    }


def _do_release() -> dict:
    """Expire OUR lease (if we hold it) so a standby promotes on the next tick."""
    now = datetime.now(timezone.utc)
    result = _mongo()[config.DB_NAME][lease.LEASE_COLLECTION].update_one(
        {"_id": lease.LEASE_ID, "holder": config.INSTANCE_ID},
        {"$set": {"expires_at": now, "released_at": now}},
    )
    return {"released": result.matched_count > 0, "instance_id": config.INSTANCE_ID}


def _require_key() -> bool:
    """Constant-time check of the X-API-Key header against DASHBOARD_API_KEY."""
    expected = config.DASHBOARD_API_KEY
    if not expected:
        # Feature disabled when no key is configured on the service.
        return False
    provided = request.headers.get("X-API-Key", "")
    return hmac.compare_digest(provided.encode(), expected.encode())


def register_routes(app, state) -> None:
    """Attach the dashboard API to the keep-alive Flask app.

    ``state`` is keep_alive.STATE (bot_ready / bot_username), mutated by the
    bot process itself — reading plain dict values across threads is safe.
    """

    @app.after_request
    def _cors(response):
        response.headers["Access-Control-Allow-Origin"] = config.API_CORS_ORIGINS
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type, X-API-Key"
        response.headers["Access-Control-Max-Age"] = "600"
        return response

    @app.route("/api/<path:_path>", methods=["OPTIONS"])
    def _cors_preflight(_path):
        # Browser preflight for dashboard POSTs (e.g. /api/leadership/release
        # with X-API-Key). Empty 204 + the CORS headers from _cors().
        return ("", 204)

    @app.get("/api/status")
    def api_status():
        now = datetime.now(timezone.utc)
        count, last_text, last_at = error_status()
        lease_state = lease.get_state()

        if not config.HA_ENABLED:
            # Legacy single-process mode: this instance always owns the token.
            role = "leader"
            polling = True
        else:
            role = "leader" if lease_state["is_leader"] else "follower"
            polling = lease_state["polling"]

        return jsonify(
            {
                "ok": True,
                "service": "POPPY-ROSE",
                "instance_id": config.INSTANCE_ID,
                "role": role,
                "polling": polling,
                "ha_enabled": config.HA_ENABLED,
                "bot_ready": bool(state.get("bot_ready")),
                "bot_username": state.get("bot_username") or None,
                "uptime_seconds": round((now - started_at()).total_seconds(), 1),
                "started_at": started_at().isoformat(),
                "leader_since": lease_state.get("since"),
                "lease_expires_in": lease_state.get("lease_expires_in"),
                "last_attempt": lease_state.get("last_attempt"),
                "internal_error": lease_state.get("last_error") or None,
                "errors": {
                    "count": count,
                    "last": (last_text or "")[:300],
                    "last_at": last_at.isoformat() if last_at else None,
                    "last_age_seconds": (
                        round((now - last_at).total_seconds(), 1) if last_at else None
                    ),
                },
                "api_key_configured": bool(config.DASHBOARD_API_KEY),
                "time": now.isoformat(),
            }
        )

    @app.get("/api/health")
    def api_health():
        ready = bool(state.get("bot_ready"))
        return (
            jsonify(
                {
                    "status": "ok" if ready else "starting",
                    "bot_ready": ready,
                    "instance_id": config.INSTANCE_ID,
                }
            ),
            200 if ready else 503,
        )

    @app.get("/api/stats")
    def api_stats():
        if not _require_key():
            return jsonify({"ok": False, "error": "unauthorized"}), 401
        try:
            stats = _do_stats()
        except Exception as exc:
            log.warning("stats query failed | %s", exc)
            return jsonify({"ok": False, "error": "database unavailable"}), 503
        return jsonify({"ok": True, "stats": stats})

    @app.post("/api/leadership/release")
    def api_release():
        if not _require_key():
            return jsonify({"ok": False, "error": "unauthorized"}), 401
        if not config.HA_ENABLED:
            return jsonify({"ok": False, "error": "HA disabled"}), 400
        try:
            result = _do_release()
        except Exception as exc:
            log.warning("release failed | %s", exc)
            return jsonify({"ok": False, "error": "database unavailable"}), 503
        return jsonify({"ok": True, **result})
