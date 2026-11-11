# 🌹 Frontend of PoppyRoseBot — Cluster Dashboard

A dependency-free static dashboard that manages **all 4 parallel POPPY ROSE
bot instances from one page**. Deploy it on **Vercel** (no build step).

## What it shows

- One card per Render service: role badge (**leader** / **follower** /
  **offline**), `@botusername`, instance id, uptime, API latency, leader
  since, lease countdown, error count + last error.
- Cluster summary: current leader, online count, total errors, shared
  user/group stats (via the API key).
- **Force re-sync** button on the leader: `POST /api/leadership/release`
  drops the lease so a standby instance takes over Telegram polling (~50 s).
- Auto-refresh (5 s / 10 s / 30 s / 1 m / off). Open tabs also act as a
  keep-awake pinger for your Render free instances (Render spins down idle
  services after ~15 min; each refresh wakes a sleeping instance).

## Connect it to your 4 services

1. Press **⚙ Manage**.
2. Add up to 4 rows: a label + the service URL
   (`https://poppy-1.onrender.com`, ...).
3. Paste your shared **API key** (the `DASHBOARD_API_KEY` value you set on
   the Render services). Without it the dashboard still monitors status;
   stats and re-sync stay disabled (server returns 401).
4. **Save** — settings are stored only in your browser (`localStorage`).

## Deploy on Vercel

```bash
# from the repository root
npx vercel        # then pick the `frontend` directory as the project root
# or via dashboard: New Project → import repo → Root Directory = frontend
```

No framework preset needed ("Other"), no build command, no output dir —
`index.html` is served as-is. The page only talks to your Render URLs, so no
Vercel env vars are required.

## Files

| file | purpose |
|------|---------|
| `index.html` | page structure + card template |
| `styles.css` | dark rose theme, responsive grid |
| `app.js` | config storage, fan-out polling, cards, failover button |

> The dashboard talks to the bot's REST API (`/api/status`, `/api/stats`,
> `/api/leadership/release`) — see `src/api.py` in the main project.
