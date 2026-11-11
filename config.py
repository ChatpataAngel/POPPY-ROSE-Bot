"""Validated environment-backed configuration for POPPY ROSE."""
from __future__ import annotations

import os


def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def _positive_int(name: str, default: str = "0") -> int:
    raw = _env(name, default)
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return 0
    return value if value > 0 else 0


BOT_TOKEN = _env("BOT_TOKEN")
OWNER_ID = _positive_int("OWNER_ID")
MONGO_DB_URI = _env("MONGO_DB_URI")
DB_NAME = _env("DB_NAME", "POPPY_ROSE") or "POPPY_ROSE"

BOT_NAME = _env("BOT_NAME", "𝙋𝙊𝙋𝙋𝙔 𝙍𝙊𝙎𝙀") or "𝙋𝙊𝙋𝙋𝙔 𝙍𝙊𝙎𝙀"
BOT_USERNAME = _env("BOT_USERNAME", "PoppyRoseBot").lstrip("@")
SUPPORT_USERNAME = _env("SUPPORT_USERNAME", "YourPOPPY42").lstrip("@")
GROUP_1 = _env("GROUP_1", "allhackpack").lstrip("@")
GROUP_2 = _env("GROUP_2", "fighterbyangel").lstrip("@")

try:
    PORT = int(_env("PORT", "10000"))
except ValueError:
    PORT = 10000

LOG_LEVEL = _env("LOG_LEVEL", "INFO").upper() or "INFO"


def _bounded_float(name: str, default: str, low: float, high: float) -> float:
    raw = _env(name, default)
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return float(default)
    return min(high, max(low, value))


# Seconds between messages for /broadcast and /announce. Telegram freezes
# bot tokens that send bulk messages in bursts, so pacing is mandatory and
# the value is clamped to [0.2s, 30s] even if the environment says otherwise.
BROADCAST_DELAY = _bounded_float("BROADCAST_DELAY", "1.0", 0.2, 30.0)


def _bounded_int(name: str, default: str, low: int, high: int) -> int:
    raw = _env(name, default)
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return int(default)
    return min(high, max(low, value))


# ---- High availability (N Render projects sharing ONE bot token) ---------
# Telegram allows only ONE concurrent getUpdates() consumer per bot token
# (a second poller gets 409 Conflict). With HA_ENABLED every instance runs
# the same code but they compete for a short-lived lease document in the
# shared MongoDB; only the lease holder polls Telegram. All instances keep
# their HTTP health/API server running so Render health checks pass and the
# frontend dashboard can monitor them.
#
# HA_ENABLED=0 restores the legacy single-process run_polling() behaviour.
HA_ENABLED = _env("HA_ENABLED", "1").lower() in ("1", "true", "yes", "on")

# Stable per-service id (unique across your 4 Render projects). Falls back to
# a process-local id when not configured — set INSTANCE_ID explicitly when
# deploying multiple instances so the dashboard can label them.
_RENDER_SERVICE_ID = _env("RENDER_SERVICE_ID")
if _RENDER_SERVICE_ID:
    _DEFAULT_INSTANCE_ID = f"render-{_RENDER_SERVICE_ID[:10]}"
else:
    _DEFAULT_INSTANCE_ID = f"local-{os.getpid()}"
INSTANCE_ID = _env("INSTANCE_ID") or _DEFAULT_INSTANCE_ID

# Leader lease: holder renews every LEASE_POLL_SECONDS; the lease expires
# LEASE_TTL_SECONDS after the last renewal. Worst-case failover ≈ TTL + POLL.
# Both values are clamped so a hostile/garbage env can never disable leasing.
LEASE_TTL_SECONDS = _bounded_int("LEASE_TTL_SECONDS", "45", 15, 300)
LEASE_POLL_SECONDS = _bounded_float("LEASE_POLL_SECONDS", "5", 2.0, 60.0)

# Shared secret the dashboard sends as X-API-Key for privileged endpoints
# (/api/stats and /api/leadership/release). Empty = those endpoints disabled.
DASHBOARD_API_KEY = _env("DASHBOARD_API_KEY")
# CORS allow-list for the dashboard origin(s); "*" is fine with a key guard.
API_CORS_ORIGINS = _env("API_CORS_ORIGINS", "*") or "*"


def validate_config() -> None:
    missing = []
    if not BOT_TOKEN:
        missing.append("BOT_TOKEN")
    if not MONGO_DB_URI:
        missing.append("MONGO_DB_URI")
    if OWNER_ID <= 0:
        missing.append("OWNER_ID")
    if missing:
        raise RuntimeError(
            "Missing or invalid required environment variables: " + ", ".join(missing)
        )
