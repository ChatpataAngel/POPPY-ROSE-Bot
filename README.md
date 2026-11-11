# 🌹 POPPY ROSE

A Telegram group-management bot built with `python-telegram-bot` and MongoDB.

## Security model

- `OWNER_ID` is mandatory and is the primary global owner.
- Additional owners can only be added by an existing owner with `/addowner`.
- `/start` **never** grants ownership.
- Legacy/non-explicit owner records are ignored.
- Normal users, group administrators, and anonymous administrators cannot execute owner-only commands unless their personal Telegram ID is an explicitly recognized global owner.
- **Anonymous group administrators are treated as normal group administrators for every `@admin_only` command.** Telegram hides their real account ID, so they cannot be treated as global owners.

### Permission matrix

| Sender | Group admin commands | Owner commands |
|---|---:|---:|
| Normal user | ❌ | ❌ |
| Group administrator | ✅ | ❌ |
| Group creator | ✅ | ❌ |
| Anonymous administrator | ✅ | ❌ |
| Global owner | ✅ | ✅ |

## Main features

Moderation: `/ban`, `/unban`, `/kick`, `/mute`, `/unmute`, `/warn`, `/warnings`, `/unwarn`

Protection: `/lock`, `/unlock`, `/purge`

Management: `/promote`, `/demote`, `/pin`, `/unpin`, `/info`, `/setwelcome`, `/setrules`, `/save`, `/get`, `/delnote`

Owner: `/god`, `/ownerhelp`, `/stats`, `/broadcast`, `/announce`, `/addowner`, `/delowner`

## Setup

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
python -m src
```

Set `BOT_TOKEN`, `MONGO_DB_URI`, and your numeric `OWNER_ID` in the environment. Never commit real secrets.

## Telegram requirements

The bot must be a group administrator with the permissions required by the commands you intend to use, especially deleting messages, restricting/banning members, pinning messages, and managing chat content.

Anonymous administrators are supported because authorization checks detect Telegram's `GroupAnonymousBot` message identity and verify that the sender-chat is the current group.

## Render

`render.yaml` is included. Configure the secret environment variables and deploy. The `/health` endpoint is served by Waitress.

## Important (polling safety)

Run only one *active* polling process per bot token. Two simultaneous polling
processes conflict over Telegram updates (409 Conflict). This codebase now
solves that for multi-instance deployments with a MongoDB **leader lease** —
see "Multi-instance deployment" below. With `HA_ENABLED=0` the old rule
applies literally: exactly one process per token.

## Multi-instance deployment (4 Render projects, one bot token)

Telegram allows only ONE concurrent `getUpdates()` consumer per token, but you
can still spread the workload across **4 Render free projects** (so no single
account's 750 h/month quota is exhausted) like this:

1. Create **4 Render projects** from the same repository (e.g. `poppy-1` …
   `poppy-4`).
2. Set the **same** secrets on all four: `BOT_TOKEN`, `MONGO_DB_URI`,
   `DB_NAME`, `OWNER_ID`, plus one shared `DASHBOARD_API_KEY`.
3. Set a **different** `INSTANCE_ID` on each (`poppy-1` … `poppy-4`) and keep
   `HA_ENABLED=true` (the default).
4. Deploy. All four instances start, but only one wins the MongoDB lease and
   polls Telegram; the other three are warm standbys that still serve
   `/health` and the dashboard API.

How failover works (`src/utils/lease.py`):

- Every `LEASE_POLL_SECONDS` (default 5 s) each instance atomically renews a
  lease document with `LEASE_TTL_SECONDS` (default 45 s) deadline.
- If the leader crashes, deploys or is put to sleep by Render, the lease
  expires and another instance takes over polling within **~50 seconds** —
  no double polling, no 409 storms.
- MongoDB outages never cause split-brain: leadership becomes "unknown" and
  each instance keeps its current role until MongoDB answers again.
- Standbys wake when hit (Render free sleeps idle services): the dashboard's
  auto-refresh pings every instance, so keeping the dashboard open doubles as
  a keep-awake pinger.

Each instance exposes a REST API for the dashboard (see `src/api.py`):

| endpoint | auth | purpose |
|----------|------|---------|
| `GET /api/status` | public | role, uptime, errors, lease info |
| `GET /api/health` | public | 200/503 readiness |
| `GET /api/stats` | `X-API-Key` | user/group counts |
| `POST /api/leadership/release` | `X-API-Key` | planned failover (leader steps down) |

## Frontend dashboard (Vercel)

`frontend/` contains a static dashboard ("Frontend of PoppyRoseBot") that
monitors and controls all four instances from one page: leader badge,
uptime/errors/latency per instance, shared stats, and a **Force re-sync**
button for planned failovers. Deploy it on Vercel with **Root Directory =
`frontend`** (no build step). Configuration lives in the browser only —
see `frontend/README.md`.


## Keeping your token healthy (avoid Telegram freezes)

Telegram restricts/freezes bot tokens that behave like spam. This codebase now
enforces the rules that keep tokens alive:

- `/broadcast` and `/announce` are **paced** by `BROADCAST_DELAY` (default: 1
  send/second, configurable, clamped to `0.2–30`s) and automatically sleep when
  Telegram answers with flood control (`RetryAfter`).
- Broadcasts **abort after 8 consecutive failures** instead of hammering
  Telegram, and dead groups are deactivated automatically.
- `/purge` deletes are throttled (~20/second) with flood-control retries.
- Polling uses `drop_pending_updates=False` so updates queued during a brief
  restart/failover are not deliberately discarded.
- Run **exactly one** polling process per token (see `render.yaml`).
- Never commit or publicly share `BOT_TOKEN`. Anyone holding a leaked token can
  get it frozen; if a token ever leaks, revoke it immediately with
  [@BotFather](https://t.me/BotFather) → `/revoke` and set the new value in
  your environment.

## Tests

```bash
pip install pytest
pytest tests -v
```

The suite is static (AST-based) plus a local handler-registration check and
in-process HTTP/HA smoke tests; it never contacts Telegram or MongoDB.
