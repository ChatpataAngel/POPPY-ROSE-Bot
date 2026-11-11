/* POPPY ROSE cluster dashboard — Frontend of PoppyRoseBot.
 *
 * Vanilla JS, no build step: add the URLs of your 4 Render services, and the
 * dashboard polls GET /api/status on each one, shows who is the leader
 * (MongoDB lease holder that polls Telegram), lets you force a failover, and
 * reads shared user/group stats via the API key.
 */
"use strict";

const CFG_KEY = "poppy_dash_cfg_v2";
const MAX_INSTANCES = 4;
const FETCH_TIMEOUT_MS = 6000;

let cfg = loadCfg();
let timer = null;
let refreshing = false;
let results = []; // per instance: {data, error, latency}

const $ = (sel, root) => (root || document).querySelector(sel);

// ---------- config persistence ----------
function loadCfg() {
  const fallback = { apiKey: "", interval: 10000, instances: [] };
  try {
    const raw = localStorage.getItem(CFG_KEY);
    if (!raw) return fallback;
    const parsed = JSON.parse(raw);
    return {
      apiKey: typeof parsed.apiKey === "string" ? parsed.apiKey : "",
      interval: Number.isFinite(parsed.interval) ? parsed.interval : 10000,
      instances: Array.isArray(parsed.instances)
        ? parsed.instances.slice(0, MAX_INSTANCES).map((x) => ({
            label: String((x && x.label) || "").slice(0, 40),
            url: String((x && x.url) || "").slice(0, 200),
          }))
        : [],
    };
  } catch (e) {
    return fallback;
  }
}

function saveCfg() {
  try {
    localStorage.setItem(CFG_KEY, JSON.stringify(cfg));
  } catch (e) {
    /* private mode etc. — dashboard still works for this visit */
  }
}

// ---------- formatting ----------
function normalizeUrl(u) {
  let url = String(u || "").trim().replace(/\/+$/, "");
  if (!url) return "";
  if (!/^https?:\/\//i.test(url)) url = "https://" + url;
  try {
    const parsed = new URL(url);
    return parsed.origin + (parsed.pathname === "/" ? "" : parsed.pathname.replace(/\/+$/, ""));
  } catch (e) {
    return "";
  }
}

function fmtUptime(sec) {
  if (sec == null || isNaN(sec)) return "—";
  sec = Math.max(0, Math.floor(sec));
  const d = Math.floor(sec / 86400);
  const h = Math.floor((sec % 86400) / 3600);
  const m = Math.floor((sec % 3600) / 60);
  const s = sec % 60;
  const parts = [];
  if (d) parts.push(d + "d");
  if (d || h) parts.push(h + "h");
  if (d || h || m) parts.push(m + "m");
  parts.push(s + "s");
  return parts.slice(0, 3).join(" ");
}

function fmtAge(sec) {
  if (sec == null || isNaN(sec)) return "age unknown";
  sec = Math.max(0, sec);
  if (sec < 60) return Math.round(sec) + "s ago";
  if (sec < 3600) return Math.round(sec / 60) + "m ago";
  if (sec < 86400) return Math.round(sec / 3600) + "h ago";
  return Math.round(sec / 86400) + "d ago";
}

function fmtIso(iso) {
  try {
    const d = new Date(iso);
    if (isNaN(d.getTime())) return iso;
    return d.toLocaleString();
  } catch (e) {
    return iso;
  }
}

function fmtNum(n) {
  return typeof n === "number" ? n.toLocaleString() : "—";
}

let toastTimer = null;
function toast(msg, isErr) {
  const el = $("#toast");
  el.textContent = msg;
  el.classList.toggle("err", !!isErr);
  el.classList.remove("hidden");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.classList.add("hidden"), 4000);
}

// ---------- setup panel ----------
function openSetup() {
  $("#setup").classList.remove("hidden");
  $("#api-key").value = cfg.apiKey;
  renderSetupRows();
}

function renderSetupRows() {
  const wrap = $("#instance-rows");
  wrap.textContent = "";
  if (!cfg.instances.length) cfg.instances.push({ label: "", url: "" });

  cfg.instances.forEach((inst, i) => {
    const row = document.createElement("div");
    row.className = "irow";

    const label = document.createElement("input");
    label.type = "text";
    label.placeholder = "Label (e.g. poppy-1)";
    label.maxLength = 40;
    label.value = inst.label;
    label.addEventListener("input", () => { inst.label = label.value; });

    const url = document.createElement("input");
    url.type = "text";
    url.placeholder = "https://poppy-1.onrender.com";
    url.value = inst.url;
    url.addEventListener("input", () => { inst.url = url.value; });

    const rm = document.createElement("button");
    rm.type = "button";
    rm.className = "rm";
    rm.textContent = "Remove";
    rm.addEventListener("click", () => {
      if (cfg.instances.length <= 1) {
        toast("Keep at least one row", true);
        return;
      }
      cfg.instances.splice(i, 1);
      renderSetupRows();
    });

    row.append(label, url, rm);
    wrap.append(row);
  });
  $("#btn-add").disabled = cfg.instances.length >= MAX_INSTANCES;
}

function saveFromForm() {
  cfg.apiKey = $("#api-key").value.trim();
  const cleaned = [];
  for (const inst of cfg.instances) {
    const url = normalizeUrl(inst.url);
    if (!url) continue;
    let label = String(inst.label || "").trim();
    if (!label) {
      try { label = new URL(url).hostname.split(".")[0]; } catch (e) { label = url; }
    }
    if (cleaned.some((c) => c.url === url)) continue;
    cleaned.push({ label: label.slice(0, 40), url });
    if (cleaned.length >= MAX_INSTANCES) break;
  }
  if (!cleaned.length) {
    toast("Enter at least one valid service URL", true);
    return false;
  }
  cfg.instances = cleaned;
  saveCfg();
  toast("Saved " + cleaned.length + " instance(s)");
  return true;
}

// ---------- fetching ----------
async function fetchStatus(inst) {
  if (!inst.url) {
    return { data: null, error: "URL not configured", latency: null };
  }
  const started = performance.now();
  const ctrl = new AbortController();
  const timeout = setTimeout(() => ctrl.abort(), FETCH_TIMEOUT_MS);
  try {
    const resp = await fetch(inst.url.replace(/\/+$/, "") + "/api/status", {
      signal: ctrl.signal,
      headers: { Accept: "application/json" },
      cache: "no-store",
    });
    if (!resp.ok) throw new Error("HTTP " + resp.status);
    const data = await resp.json();
    return { data, error: null, latency: Math.round(performance.now() - started) };
  } catch (e) {
    const msg =
      e && e.name === "AbortError"
        ? "timeout after " + FETCH_TIMEOUT_MS + "ms (instance asleep or unreachable)"
        : e && e.message
        ? e.message
        : String(e);
    return { data: null, error: msg, latency: null };
  } finally {
    clearTimeout(timeout);
  }
}

async function refreshAll() {
  if (refreshing || !cfg.instances.length) return;
  refreshing = true;
  $("#btn-refresh").disabled = true;
  try {
    results = await Promise.all(cfg.instances.map(fetchStatus));
    renderCards();
    renderSummary();
    await fetchStats();
    $("#last-sync").textContent = "synced " + new Date().toLocaleTimeString();
  } finally {
    refreshing = false;
    $("#btn-refresh").disabled = false;
  }
}

// ---------- rendering ----------
function renderCards() {
  const grid = $("#cards");
  const tpl = $("#card-tpl");
  grid.textContent = "";
  $("#empty").classList.toggle("hidden", cfg.instances.length > 0);

  cfg.instances.forEach((inst, i) => {
    const node = tpl.content.firstElementChild.cloneNode(true);
    const r = results[i] || null;
    const data = r ? r.data : null;
    const role = data ? data.role : r ? "offline" : "checking";

    node.classList.toggle("leader", !!data && data.role === "leader");
    node.classList.toggle("offline", !data && !!r);
    node.classList.toggle("loading", !r);

    $(".name", node).textContent = inst.label || "Instance " + (i + 1);
    const badge = $(".badge", node);
    badge.className = "badge " + (role === "checking" ? "follower" : role);
    badge.textContent = role;

    $(".bot", node).textContent = data
      ? data.bot_username
        ? "@" + data.bot_username
        : data.bot_ready
        ? "ready"
        : "starting…"
      : "—";
    $(".iid", node).textContent = data ? data.instance_id : "—";
    $(".uptime", node).textContent = data ? fmtUptime(data.uptime_seconds) : "—";
    $(".latency", node).textContent = r && r.latency != null ? r.latency + " ms" : "—";
    $(".since", node).textContent =
      data && data.leader_since ? fmtIso(data.leader_since) : "—";
    const leaseEl = $(".lease", node);
    if (data && data.lease_expires_in != null) {
      leaseEl.textContent = Math.max(0, Math.round(data.lease_expires_in)) + "s";
      leaseEl.className = "lease ok";
    } else {
      leaseEl.textContent = data ? "not held" : "—";
      leaseEl.className = "lease";
    }

    // Error block: unreachable instance OR recorded errors since start.
    const errBox = $(".err", node);
    const errCount = data && data.errors ? data.errors.count || 0 : 0;
    const errLine = data
      ? [
          data.errors && data.errors.last
            ? data.errors.last + " · " + fmtAge(data.errors.last_age_seconds)
            : "",
          data.internal_error ? "lease: " + data.internal_error : "",
        ]
          .filter(Boolean)
          .join("\n")
      : r && r.error
      ? r.error
      : "…";
    const showErr = (r && !data) || errCount > 0 || (data && !!data.internal_error);
    if (showErr) {
      errBox.classList.remove("hidden");
      $(".err-count", node).textContent = data
        ? errCount + " error(s) since start" + (data.internal_error ? " · lease issue" : "")
        : "UNREACHABLE";
      $(".err-text", node).textContent = errLine;
    } else {
      errBox.classList.add("hidden");
    }

    const resync = $(".resync", node);
    if (data && data.role === "leader") resync.classList.remove("hidden");
    resync.addEventListener("click", () => forceResync(inst, node));

    $(".url", node).textContent = inst.url || "no URL";
    const open = $(".actions a", node);
    open.href = inst.url || "#";
    grid.append(node);
  });
}

function renderSummary() {
  const online = results.filter((r) => r && r.data).length;
  const leaderIdx = results.findIndex((r) => r && r.data && r.data.role === "leader");
  const totalErrors = results.reduce(
    (sum, r) => sum + (r && r.data && r.data.errors ? r.data.errors.count || 0 : 0),
    0
  );
  $("#sum-leader").textContent =
    leaderIdx >= 0
      ? cfg.instances[leaderIdx].label || results[leaderIdx].data.instance_id
      : online > 0
      ? "none — failover pending"
      : "—";
  $("#sum-online").textContent = online + "/" + cfg.instances.length;
  $("#sum-errors").textContent = String(totalErrors);
}

async function fetchStats() {
  if (!cfg.apiKey) return;
  const leaderIdx = results.findIndex((r) => r && r.data && r.data.role === "leader");
  const anyIdx = results.findIndex((r) => r && r.data);
  const use = leaderIdx >= 0 ? leaderIdx : anyIdx;
  if (use < 0) return;
  const ctrl = new AbortController();
  const timeout = setTimeout(() => ctrl.abort(), 5000);
  try {
    const resp = await fetch(cfg.instances[use].url.replace(/\/+$/, "") + "/api/stats", {
      headers: { "X-API-Key": cfg.apiKey },
      signal: ctrl.signal,
      cache: "no-store",
    });
    clearTimeout(timeout);
    if (resp.status === 401) {
      toast("API key rejected — check DASHBOARD_API_KEY", true);
      return;
    }
    if (!resp.ok) return;
    const body = await resp.json();
    if (body.ok && body.stats) {
      $("#sum-users").textContent = fmtNum(body.stats.users);
      $("#sum-groups").textContent = fmtNum(
        body.stats.active_groups != null ? body.stats.active_groups : body.stats.groups
      );
    }
  } catch (e) {
    clearTimeout(timeout);
    /* stats are optional — never break the dashboard for them */
  }
}

async function forceResync(inst, cardNode) {
  if (!cfg.apiKey) {
    toast("Set the API key first (⚙ Manage)", true);
    openSetup();
    return;
  }
  const label = inst.label || inst.url;
  const ok = confirm(
    "Release the leader lease on " +
      label +
      "?\nA standby instance takes over Telegram polling within ~50 seconds."
  );
  if (!ok) return;
  const btn = cardNode ? cardNode.querySelector(".resync") : null;
  if (btn) btn.disabled = true;
  try {
    const resp = await fetch(inst.url.replace(/\/+$/, "") + "/api/leadership/release", {
      method: "POST",
      headers: { "X-API-Key": cfg.apiKey },
    });
    const body = await resp.json().catch(() => ({}));
    if (!resp.ok) {
      toast("Re-sync failed: " + (body.error || "HTTP " + resp.status), true);
    } else if (body.released) {
      toast("Lease released — a standby becomes leader within ~50s");
      setTimeout(refreshAll, 2000);
    } else {
      toast("This instance does not hold the lease (leader is elsewhere)", true);
    }
  } catch (e) {
    toast("Re-sync failed: " + e.message, true);
  } finally {
    if (btn) btn.disabled = false;
  }
}

// ---------- timer + events ----------
function applyInterval() {
  if (timer) clearInterval(timer);
  const ms = Number(cfg.interval) || 0;
  if (ms > 0) timer = setInterval(refreshAll, ms);
  $("#interval").value = String(ms);
}

function init() {
  $("#btn-manage").addEventListener("click", () => {
    const panel = $("#setup");
    if (panel.classList.contains("hidden")) openSetup();
    else panel.classList.add("hidden");
  });
  $("#btn-close").addEventListener("click", () => $("#setup").classList.add("hidden"));
  $("#btn-add").addEventListener("click", () => {
    if (cfg.instances.length >= MAX_INSTANCES) {
      toast("Maximum 4 instances", true);
      return;
    }
    cfg.instances.push({ label: "", url: "" });
    renderSetupRows();
  });
  $("#btn-save").addEventListener("click", () => {
    if (saveFromForm()) {
      $("#setup").classList.add("hidden");
      results = [];
      renderCards();
      refreshAll();
    }
  });
  $("#btn-refresh").addEventListener("click", () => refreshAll());
  $("#interval").addEventListener("change", (e) => {
    cfg.interval = Number(e.target.value) || 0;
    saveCfg();
    applyInterval();
  });
  document.addEventListener("visibilitychange", () => {
    if (!document.hidden) refreshAll();
  });

  if (!cfg.instances.length) {
    // First visit: pre-fill the classic 4-project layout so the operator
    // only has to paste the Render URLs.
    cfg.instances = [
      { label: "poppy-1", url: "" },
      { label: "poppy-2", url: "" },
      { label: "poppy-3", url: "" },
      { label: "poppy-4", url: "" },
    ];
    openSetup();
  }

  renderCards();
  applyInterval();
  if (cfg.instances.some((i) => i.url)) refreshAll();
}

document.addEventListener("DOMContentLoaded", init);




