"""Tests for the multi-instance HA layer, dashboard API, and frontend assets.

Never contacts Telegram or MongoDB: the lease loop is driven by a stubbed
``try_acquire`` and the Flask endpoints by stubbed DB helpers.
"""
from __future__ import annotations

import asyncio
import os
from pathlib import Path

# Environment MUST be set before any project module is imported because
# src.database.db_core validates the config at import time. setdefault keeps
# real local credentials intact when a developer runs the suite on .env.
os.environ.setdefault("BOT_TOKEN", "123456:TEST-token-for-pytest")
os.environ.setdefault("MONGO_DB_URI", "mongodb://localhost:27017")
os.environ.setdefault("OWNER_ID", "1")
os.environ.setdefault("INSTANCE_ID", "test-instance")

ROOT = Path(__file__).resolve().parents[1]


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Static checks
# ---------------------------------------------------------------------------

def test_lease_module_uses_atomic_acquire():
    src = _read("src/utils/lease.py")
    assert "find_one_and_update" in src
    assert "ReturnDocument.AFTER" in src
    assert "upsert" in src
    assert "LEASE_TTL_SECONDS" in src
    # Leadership is treated as unknown on Mongo failure (no blind hand-over).
    assert "acquired = None" in src


def test_api_guards_and_cors():
    src = _read("src/api.py")
    assert '"/api/status"' in src
    assert '"/api/stats"' in src
    assert '"/api/leadership/release"' in src
    assert "X-API-Key" in src
    assert "compare_digest" in src
    assert "Access-Control-Allow-Origin" in src


def test_keep_alive_registers_dashboard_api():
    src = _read("src/keep_alive.py")
    assert "from src.api import register_routes" in src
    assert "register_routes(app, STATE)" in src


def test_main_branches_on_ha_enabled():
    src = _read("src/__main__.py")
    assert "HA_ENABLED" in src
    assert "leader_loop" in src
    assert "asyncio.run(leader_loop(app))" in src
    # Legacy single-instance path is preserved for HA_ENABLED=0.
    assert "app.run_polling(" in src
    assert "drop_pending_updates=False" in src
    assert "allowed_updates=Update.ALL_TYPES" in src


def test_frontend_assets_exist():
    for rel in ("frontend/index.html", "frontend/styles.css", "frontend/app.js"):
        text = _read(rel)
        assert len(text) > 500, rel
    js = _read("frontend/app.js")
    assert "/api/status" in js
    assert "X-API-Key" in js
    assert "/api/leadership/release" in js
    html = _read("frontend/index.html")
    assert 'src="app.js"' in html
    assert 'href="styles.css"' in html


def test_config_ha_defaults():
    import config

    assert config.HA_ENABLED is True
    assert 15 <= config.LEASE_TTL_SECONDS <= 300
    assert 2.0 <= config.LEASE_POLL_SECONDS <= 60.0
    assert config.INSTANCE_ID  # never empty (auto-generated fallback)


# ---------------------------------------------------------------------------
# HTTP API smoke (Flask test client — no server, no Mongo)
# ---------------------------------------------------------------------------

def test_api_status_endpoint():
    from src.keep_alive import app as flask_app

    client = flask_app.test_client()
    resp = client.get("/api/status")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["ok"] is True
    assert data["instance_id"] == "test-instance"
    assert data["role"] in ("leader", "follower")
    assert isinstance(data["polling"], bool)
    assert data["uptime_seconds"] >= 0
    assert data["errors"]["count"] >= 0
    # CORS so the Vercel dashboard can call cross-origin.
    assert resp.headers["Access-Control-Allow-Origin"] == "*"

    health = client.get("/api/health")
    assert health.status_code in (200, 503)
    assert "Access-Control-Allow-Origin" in health.headers


def test_api_key_guards_privileged_endpoints(monkeypatch):
    import config
    import src.api as api
    from src.keep_alive import app as flask_app

    client = flask_app.test_client()

    # No key configured → privileged endpoints are disabled (always 401).
    monkeypatch.setattr(config, "DASHBOARD_API_KEY", "")
    assert client.get("/api/stats").status_code == 401
    assert client.post("/api/leadership/release").status_code == 401

    # Key configured → wrong/missing keys rejected before touching the DB.
    monkeypatch.setattr(config, "DASHBOARD_API_KEY", "sekret")
    assert client.get("/api/stats").status_code == 401
    wrong = client.post("/api/leadership/release", headers={"X-API-Key": "wrong"})
    assert wrong.status_code == 401

    # Correct key → helpers run (stubbed so no Mongo connection happens).
    monkeypatch.setattr(
        api, "_do_stats", lambda: {"users": 5, "groups": 2, "active_groups": 2}
    )
    monkeypatch.setattr(
        api,
        "_do_release",
        lambda: {"released": True, "instance_id": config.INSTANCE_ID},
    )
    stats = client.get("/api/stats", headers={"X-API-Key": "sekret"})
    assert stats.status_code == 200
    assert stats.get_json()["stats"]["users"] == 5

    release = client.post(
        "/api/leadership/release", headers={"X-API-Key": "sekret"}
    )
    assert release.status_code == 200
    assert release.get_json()["released"] is True


# ---------------------------------------------------------------------------
# Leader loop behaviour (stubbed lease — no Mongo)
# ---------------------------------------------------------------------------

def test_leader_loop_gates_polling_by_lease(monkeypatch):
    import src.utils.lease as lease_mod

    class FakeUpdater:
        def __init__(self):
            self.running = False
            self.starts = 0
            self.stops = 0

        async def start_polling(self, **kwargs):
            self.starts += 1
            self.running = True

        async def stop(self):
            assert self.running, "Updater.stop() raises when not running"
            self.stops += 1
            self.running = False

    class FakeApp:
        def __init__(self):
            self.updater = FakeUpdater()
            self.post_init = None
            self.post_stop = None
            self.post_shutdown = None
            self.initialized = False
            self.started = False
            self.stopped = False
            self.shutdown_done = False

        async def initialize(self):
            self.initialized = True

        async def start(self):
            self.started = True

        async def stop(self):
            self.stopped = True

        async def shutdown(self):
            self.shutdown_done = True

    stop_event = asyncio.Event()
    # leader -> standby -> leader -> (sequence done) -> stop
    outcomes = iter([True, False, True])

    async def fake_acquire():
        try:
            return next(outcomes)
        except StopIteration:
            stop_event.set()
            return False

    async def fake_release():
        return None

    monkeypatch.setattr(lease_mod, "try_acquire", fake_acquire)
    monkeypatch.setattr(lease_mod, "release", fake_release)
    monkeypatch.setattr(lease_mod, "LEASE_POLL_SECONDS", 0.01)
    monkeypatch.setattr(lease_mod, "_shutting_down", False)

    app = FakeApp()
    asyncio.run(lease_mod.leader_loop(app, stop_event))

    # Lifecycle ran in run_polling order.
    assert app.initialized and app.started
    assert app.stopped and app.shutdown_done
    # Polling started exactly twice (two promotions) and stopped exactly
    # twice (one demotion + shutdown guard) — never while a standby.
    assert app.updater.starts == 2
    assert app.updater.stops == 2
    assert app.updater.running is False
    assert lease_mod._state["polling"] is False

