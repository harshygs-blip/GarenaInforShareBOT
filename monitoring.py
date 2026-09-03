"""Monitoring web dashboard and aiohttp API handlers for Garena Bot."""

import asyncio
import os
import threading

from aiohttp import web

import db

MASTER_KEY = "shivambhatt@admin"
MONITORING_KEY = os.environ.get("MONITORING_KEY", MASTER_KEY)

# ─── Auth ────────────────────────────────────────────────────────────────────

def _auth(req: web.Request) -> bool:
    key = req.rel_url.query.get("key") or req.cookies.get("monitor_key") or ""
    return key in (MASTER_KEY, MONITORING_KEY)

# ─── Handlers ────────────────────────────────────────────────────────────────

async def _root(req: web.Request) -> web.Response:
    key = req.rel_url.query.get("key") or req.cookies.get("monitor_key")
    if key and key in (MASTER_KEY, MONITORING_KEY):
        raise web.HTTPFound(f"/monitor?key={key}")
    raise web.HTTPFound("/monitor")


async def _dashboard(req: web.Request) -> web.Response:
    key = req.rel_url.query.get("key") or req.cookies.get("monitor_key") or ""
    if key in (MASTER_KEY, MONITORING_KEY):
        resp = web.Response(text=DASHBOARD_HTML, content_type="text/html")
        resp.set_cookie("monitor_key", key, max_age=86400 * 30, httponly=False)
        return resp
    return web.Response(text=LOGIN_HTML, content_type="text/html")


async def _api_data(req: web.Request) -> web.Response:
    if not _auth(req):
        return web.json_response({"error": "forbidden"}, status=403)
    feature = req.rel_url.query.get("feature") or None
    result  = req.rel_url.query.get("result")  or None
    search  = req.rel_url.query.get("search")  or None
    uid_str = req.rel_url.query.get("user_id") or None
    user_id = int(uid_str) if uid_str and uid_str.isdigit() else None
    return web.json_response({
        "activities": db.get_activities(limit=500, feature=feature, result=result, search=search, user_id=user_id),
        "debug_logs": db.get_user_debug_logs(user_id=user_id, limit=300),
        "active_bf":  db.get_active_bf_sessions(),
        "recent_bf":  db.get_recent_bf_sessions(10),
        "stats":      db.get_stats(),
        "alerts":     db.get_alerts(),
    })


async def _api_user_logs(req: web.Request) -> web.Response:
    if not _auth(req):
        return web.json_response({"error": "forbidden"}, status=403)
    uid_str = req.match_info.get("user_id") or ""
    user_id = int(uid_str) if uid_str.isdigit() else None
    return web.json_response({
        "user_id": user_id,
        "logs": db.get_user_debug_logs(user_id=user_id, limit=500),
        "activities": db.get_activities(user_id=user_id, limit=200) if user_id else [],
    })


async def _api_stop_bf(req: web.Request) -> web.Response:
    if not _auth(req):
        return web.json_response({"error": "forbidden"}, status=403)
    sid = int(req.match_info["id"])
    stopped = db.stop_bf_session(sid)
    return web.json_response({"session_id": sid, "stopped": stopped})


async def _api_flag(req: web.Request) -> web.Response:
    if not _auth(req):
        return web.json_response({"error": "forbidden"}, status=403)
    eid     = int(req.match_info["id"])
    flagged = db.toggle_flag(eid)
    return web.json_response({"id": eid, "flagged": flagged})


# ─── Route Registry ──────────────────────────────────────────────────────────

def get_webhook_routes() -> list:
    """Pass these as custom_routes to Application.run_webhook()."""
    return [
        web.get("/",                        _root),
        web.get("/monitor",                 _dashboard),
        web.get("/api/data",                _api_data),
        web.get("/api/user-logs/{user_id}", _api_user_logs),
        web.post("/api/bf/stop/{id}",       _api_stop_bf),
        web.post("/api/flag/{id}",          _api_flag),
    ]


def start_polling_monitor(port: int = 8081) -> None:
    """Start monitoring in a background thread (for local polling mode)."""
    if not MONITORING_KEY:
        print("[Monitor] MONITORING_KEY not set — dashboard disabled.")
        return

    def _run() -> None:
        async def _main() -> None:
            app = web.Application()
            app.router.add_get("/",                        _root)
            app.router.add_get("/monitor",                 _dashboard)
            app.router.add_get("/api/data",                _api_data)
            app.router.add_get("/api/user-logs/{user_id}", _api_user_logs)
            app.router.add_post("/api/bf/stop/{id}",       _api_stop_bf)
            app.router.add_post("/api/flag/{id}",          _api_flag)
            runner = web.AppRunner(app)
            await runner.setup()
            await web.TCPSite(runner, "0.0.0.0", port).start()
            print(f"[Monitor] http://localhost:{port}/monitor?key={MONITORING_KEY}")
            await asyncio.Event().wait()

        asyncio.run(_main())

    threading.Thread(target=_run, daemon=True).start()


# ─── Dashboard HTML ───────────────────────────────────────────────────────────

DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Garena Bot Monitor & Debugger</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600&display=swap" rel="stylesheet">
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<style>
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
:root{
  --bg:#07070f;--s:rgba(255,255,255,.04);--s2:rgba(255,255,255,.07);
  --b:rgba(255,255,255,.08);--b2:rgba(255,255,255,.14);
  --cyan:#00f5ff;--purple:#a855f7;--green:#10b981;--red:#ef4444;
  --orange:#f97316;--yellow:#eab308;--blue:#3b82f6;--pink:#ec4899;
  --t:#e2e8f0;--td:#94a3b8;--tdd:#475569
}
body{background:var(--bg);color:var(--t);font-family:'Inter',sans-serif;min-height:100vh;overflow-x:hidden}
body::before{
  content:'';position:fixed;inset:0;pointer-events:none;z-index:0;
  background:
    radial-gradient(ellipse 80% 50% at 10% 10%,rgba(0,245,255,.05) 0,transparent 60%),
    radial-gradient(ellipse 60% 50% at 90% 90%,rgba(168,85,247,.05) 0,transparent 60%)
}
.wrap{position:relative;z-index:1;max-width:1480px;margin:0 auto;padding:0 24px 64px}

/* ── Header ── */
header{display:flex;align-items:center;justify-content:space-between;padding:24px 0 28px;border-bottom:1px solid var(--b);margin-bottom:28px}
.logo{display:flex;align-items:center;gap:12px}
.logo-icon{width:44px;height:44px;border-radius:12px;background:linear-gradient(135deg,var(--cyan),var(--purple));display:flex;align-items:center;justify-content:center;font-size:24px}
.logo-name{font-size:18px;font-weight:700;letter-spacing:-.5px}
.logo-name span{color:var(--cyan)}
.logo-sub{font-size:11px;color:var(--tdd);margin-top:2px}
.nav-actions{display:flex;align-items:center;gap:10px}
.live-badge{display:flex;align-items:center;gap:8px;background:var(--s);border:1px solid var(--b);border-radius:8px;padding:7px 13px;font-size:12px;color:var(--td)}
.dot{width:7px;height:7px;border-radius:50%;background:var(--green);animation:pulse 2s infinite}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.3}}

/* ── Card ── */
.card{background:var(--s);border:1px solid var(--b);border-radius:16px;padding:22px;backdrop-filter:blur(12px);transition:border-color .2s;margin-bottom:20px}
.card:hover{border-color:var(--b2)}

/* ── Stats ── */
.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:14px;margin-bottom:24px}
.sc{padding:18px 20px;position:relative;overflow:hidden;border-radius:16px}
.sc::after{content:'';position:absolute;top:0;left:0;right:0;height:2px;border-radius:2px 2px 0 0}
.sc.c::after{background:linear-gradient(90deg,var(--cyan),transparent)}
.sc.p::after{background:linear-gradient(90deg,var(--purple),transparent)}
.sc.g::after{background:linear-gradient(90deg,var(--green),transparent)}
.sc.o::after{background:linear-gradient(90deg,var(--orange),transparent)}
.sc.b::after{background:linear-gradient(90deg,var(--pink),transparent)}
.sc.r::after{background:linear-gradient(90deg,var(--red),transparent)}
.sl{font-size:10px;text-transform:uppercase;letter-spacing:1px;color:var(--tdd);margin-bottom:8px}
.sv{font-size:28px;font-weight:700;line-height:1}
.sv.c{color:var(--cyan)}.sv.p{color:var(--purple)}.sv.g{color:var(--green)}
.sv.o{color:var(--orange)}.sv.b{color:var(--pink)}.sv.r{color:var(--red)}

/* ── Live Brute Force Monitor Card ── */
.bf-live-wrap{border-color:rgba(236,72,153,.25);background:rgba(236,72,153,.03);transition:all .3s}
.bf-live-wrap.active{border-color:rgba(239,68,68,.6);background:rgba(239,68,68,.08);box-shadow:0 0 30px rgba(239,68,68,.3);animation:bfGlow 2s infinite alternate}
@keyframes bfGlow{from{box-shadow:0 0 15px rgba(239,68,68,.15)}to{box-shadow:0 0 35px rgba(239,68,68,.35)}}
.bf-head{display:flex;align-items:center;justify-content:space-between;margin-bottom:14px}
.bf-title{font-size:13px;font-weight:700;letter-spacing:.5px;display:flex;align-items:center;gap:9px}
.bf-dot{width:9px;height:9px;border-radius:50%;background:var(--tdd)}
.bf-dot.live{background:var(--red);box-shadow:0 0 12px var(--red);animation:pulse 1s infinite}
.bf-status-badge{font-size:11px;font-weight:700;padding:4px 10px;border-radius:6px;background:var(--s2);color:var(--td)}
.bf-status-badge.live{background:rgba(239,68,68,.25);color:var(--red);border:1px solid rgba(239,68,68,.5);animation:pulse 1.5s infinite}
.bf-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:14px}
.bf-card{background:rgba(0,0,0,.45);border:1px solid var(--b);border-radius:12px;padding:16px;position:relative}
.bf-row{display:flex;align-items:center;justify-content:space-between;margin-bottom:8px;font-size:12px}
.bf-lbl{color:var(--tdd);font-size:10.5px;text-transform:uppercase;letter-spacing:.5px}
.stop-bf-btn{background:rgba(239,68,68,.2);border:1px solid rgba(239,68,68,.5);color:#fca5a5;padding:7px 14px;border-radius:7px;font-size:11.5px;font-weight:700;cursor:pointer;transition:all .15s}
.stop-bf-btn:hover{background:var(--red);color:#fff}
.bf-progress-bar{height:5px;background:rgba(255,255,255,.08);border-radius:3px;overflow:hidden;margin-top:10px}
.bf-progress-fill{height:100%;width:100%;background:linear-gradient(90deg,var(--pink),var(--red));border-radius:3px;animation:bfSlide 2s linear infinite}
@keyframes bfSlide{0%{transform:translateX(-100%)}100%{transform:translateX(100%)}}

/* ── Alerts ── */
.alerts-wrap{margin-bottom:20px;display:none}
.alerts-wrap.on{display:block}
.ah{font-size:13px;font-weight:600;margin-bottom:10px;display:flex;align-items:center;gap:7px}
.ai{padding:9px 13px;border-radius:8px;font-size:13px;line-height:1.55;margin-bottom:7px}
.ai.danger{background:rgba(239,68,68,.1);border:1px solid rgba(239,68,68,.3)}
.ai.warning{background:rgba(245,158,11,.1);border:1px solid rgba(245,158,11,.3)}

/* ── Tab Navigation ── */
.tab-bar{display:flex;gap:8px;margin-bottom:20px;border-bottom:1px solid var(--b);padding-bottom:12px}
.tab-btn{background:transparent;border:1px solid var(--b);border-radius:8px;color:var(--td);padding:8px 16px;font-size:13px;font-weight:600;cursor:pointer;transition:all .15s}
.tab-btn:hover{background:var(--s2);color:var(--t)}
.tab-btn.active{background:linear-gradient(135deg,rgba(0,245,255,.15),rgba(168,85,247,.15));border-color:var(--cyan);color:var(--cyan)}

/* ── Charts ── */
.charts{display:grid;grid-template-columns:1fr 2fr;gap:16px;margin-bottom:20px}
@media(max-width:768px){.charts{grid-template-columns:1fr}}
.ct{font-size:12px;font-weight:600;color:var(--td);margin-bottom:14px;text-transform:uppercase;letter-spacing:.5px}

/* ── Toolbar ── */
.toolbar{display:flex;align-items:center;gap:10px;margin-bottom:14px;flex-wrap:wrap}
.toolbar h2{font-size:14px;font-weight:600;flex:1;min-width:140px}
input,select{
  background:var(--s);border:1px solid var(--b);border-radius:8px;
  color:var(--t);padding:8px 12px;font-size:12px;font-family:inherit;
  outline:none;transition:border-color .2s
}
input:focus,select:focus{border-color:var(--cyan)}
input{width:220px}
select option{background:#121324}

/* ── Table ── */
.tw{overflow-x:auto;border-radius:10px}
table{width:100%;border-collapse:collapse;font-size:12px}
thead th{
  padding:10px 12px;text-align:left;font-size:10.5px;font-weight:600;
  text-transform:uppercase;letter-spacing:.5px;color:var(--tdd);
  border-bottom:1px solid var(--b);background:rgba(255,255,255,.02);white-space:nowrap
}
tbody tr{border-bottom:1px solid rgba(255,255,255,.03);transition:background .15s}
tbody tr:hover{background:rgba(255,255,255,.04)}
tbody tr.fr{background:rgba(239,68,68,.08)}
td{padding:10px 12px;vertical-align:middle}

/* ── Badges ── */
.badge{display:inline-flex;align-items:center;padding:3px 8px;border-radius:5px;font-size:10.5px;font-weight:600;white-space:nowrap}
.b-add{background:rgba(0,245,255,.12);color:var(--cyan)}
.b-check{background:rgba(16,185,129,.12);color:var(--green)}
.b-platform{background:rgba(168,85,247,.12);color:var(--purple)}
.b-cancel{background:rgba(249,115,22,.12);color:var(--orange)}
.b-revoke{background:rgba(239,68,68,.12);color:var(--red)}
.b-unbind{background:rgba(234,179,8,.12);color:var(--yellow)}
.b-change{background:rgba(59,130,246,.12);color:var(--blue)}
.b-bf{background:rgba(236,72,153,.12);color:var(--pink)}

.rs{color:var(--green);font-weight:600}
.rf{color:var(--red);font-weight:600}
.rp{color:var(--yellow);font-weight:600}

.flag-btn{background:none;border:none;cursor:pointer;font-size:14px;padding:3px 6px;border-radius:6px;transition:background .15s;color:var(--tdd)}
.flag-btn:hover{background:var(--s2);color:var(--red)}
.flag-btn.on{color:var(--red)}

.user-link{cursor:pointer;color:var(--cyan);text-decoration:none;font-weight:600}
.user-link:hover{text-decoration:underline}

/* Token Box with Copy Button */
.token-box{display:flex;align-items:center;gap:6px;max-width:280px}
.token-text{
  font-family:'JetBrains Mono',monospace;font-size:11px;color:var(--td);
  background:rgba(0,0,0,.3);padding:4px 8px;border-radius:6px;
  overflow:hidden;text-overflow:ellipsis;white-space:nowrap;flex:1;
}
.copy-btn{
  background:var(--s2);border:1px solid var(--b);color:var(--td);
  border-radius:6px;padding:4px 7px;font-size:11px;cursor:pointer;transition:all .15s;
}
.copy-btn:hover{background:var(--cyan);color:#000;border-color:var(--cyan)}

.code{font-family:'JetBrains Mono',monospace;font-size:11.5px;color:var(--td)}
.ts{font-size:11px;color:var(--tdd);white-space:nowrap}
.nd{text-align:center;padding:40px;color:var(--tdd);font-size:13px}
.spin-wrap{text-align:center;padding:50px}
.spin{display:inline-block;width:28px;height:28px;border:3px solid var(--b);border-top-color:var(--cyan);border-radius:50%;animation:sp .8s linear infinite}
@keyframes sp{to{transform:rotate(360deg)}}

/* ── Modal for User Bug Debugger ── */
.modal-overlay{display:none;position:fixed;inset:0;background:rgba(0,0,0,.75);z-index:1000;backdrop-filter:blur(8px);align-items:center;justify-content:center;padding:20px}
.modal-overlay.open{display:flex}
.modal{background:#0d0e1c;border:1px solid var(--b2);border-radius:18px;width:100%;max-width:900px;max-height:85vh;display:flex;flex-direction:column;box-shadow:0 25px 60px rgba(0,0,0,.8)}
.modal-head{display:flex;align-items:center;justify-content:space-between;padding:18px 24px;border-bottom:1px solid var(--b)}
.modal-head h3{font-size:16px;font-weight:700}
.modal-close{background:transparent;border:none;color:var(--tdd);font-size:22px;cursor:pointer;padding:4px 8px;border-radius:6px}
.modal-close:hover{color:var(--t);background:var(--s2)}
.modal-body{padding:20px 24px;overflow-y:auto;flex:1}

/* ── Countdown bar ── */
.cbar{position:fixed;bottom:0;left:0;right:0;height:2px;background:var(--b);z-index:999}
.cfill{height:100%;background:linear-gradient(90deg,var(--cyan),var(--purple));transition:width 1s linear}
</style>
</head>
<body>
<div class="wrap">

<!-- Header -->
<header>
  <div class="logo">
    <div class="logo-icon">🎮</div>
    <div>
      <div class="logo-name">Garena <span>Monitor & Debugger</span></div>
      <div class="logo-sub">Full Credential Inspection & User Debug Logging</div>
    </div>
  </div>
  <div class="nav-actions">
    <div class="live-badge">
      <span class="dot"></span>
      Auto-refresh in <span id="cd">30</span>s
    </div>
  </div>
</header>

<!-- Stats -->
<div class="stats" id="stats">
  <div class="card sc c"><div class="sl">Total Operations</div><div class="sv c" id="s0">—</div></div>
  <div class="card sc p"><div class="sl">Unique Users</div><div class="sv p" id="s1">—</div></div>
  <div class="card sc g"><div class="sl">Unique Emails</div><div class="sv g" id="s2">—</div></div>
  <div class="card sc o"><div class="sl">Today</div><div class="sv o" id="s3">—</div></div>
  <div class="card sc b"><div class="sl">Active Brute Force</div><div class="sv b" id="s4">0</div></div>
  <div class="card sc r"><div class="sl">Security Alerts</div><div class="sv r" id="s5">—</div></div>
</div>

<!-- LIVE BRUTE FORCE MONITOR CARD -->
<div class="card bf-live-wrap" id="bf-wrap">
  <div class="bf-head">
    <div class="bf-title"><span class="bf-dot" id="bf-dot"></span> 🔨 LIVE SECURITY CODE BRUTE FORCE MONITOR</div>
    <span class="bf-status-badge" id="bf-badge">Idle</span>
  </div>
  <div id="bf-content">
    <div style="color:var(--tdd);font-size:12.5px;padding:4px 0">🟢 No security code brute force operations currently running.</div>
  </div>
</div>

<!-- Alerts -->
<div class="card alerts-wrap" id="awrap">
  <div class="ah">⚠️ Security Alerts</div>
  <div id="alist"></div>
</div>

<!-- Tab Navigation -->
<div class="tab-bar">
  <button class="tab-btn active" id="tab-act-btn" onclick="switchTab('activities')">📋 Activity Log (Full Tokens)</button>
  <button class="tab-btn" id="tab-dbg-btn" onclick="switchTab('debugger')">🐞 User Debug Logs (Step-by-Step Traces)</button>
</div>

<!-- Charts Section -->
<div class="charts" id="charts-sec">
  <div class="card"><div class="ct">📊 By Feature</div><div style="position:relative;height:220px"><canvas id="cc"></canvas></div></div>
  <div class="card"><div class="ct">📈 Last 7 Days Activity</div><div style="position:relative;height:220px"><canvas id="lc"></canvas></div></div>
</div>

<!-- TAB 1: Activity Log Table -->
<div class="card" id="act-panel">
  <div class="toolbar">
    <h2>📋 Operations & Full Tokens</h2>
    <input id="srch" type="text" placeholder="Search user, email, token…">
    <select id="ff">
      <option value="">All Features</option>
      <option value="add">Add Email</option>
      <option value="check">Check Email</option>
      <option value="platform">Platform</option>
      <option value="cancel">Cancel Email</option>
      <option value="revoke">Revoke Token</option>
      <option value="unbind">Unbind Email</option>
      <option value="change">Change Bind</option>
      <option value="bf">Security Code BF</option>
    </select>
    <select id="rf2">
      <option value="">All Results</option>
      <option value="success">✅ Success</option>
      <option value="failed">❌ Failed</option>
      <option value="pending">⏳ Pending</option>
      <option value="stopped">🛑 Stopped</option>
      <option value="cancelled">🚫 Cancelled</option>
    </select>
    <span id="row-count" style="font-size:12px;color:var(--tdd);margin-left:auto"></span>
  </div>
  <div class="tw">
    <table>
      <thead><tr>
        <th>#</th><th>Time</th><th>User (Click to Debug)</th><th>Feature</th>
        <th>Email</th><th>Full Access Token</th><th>Result</th><th>Flag</th>
      </tr></thead>
      <tbody id="tb"><tr><td colspan="8" class="spin-wrap"><div class="spin"></div></td></tr></tbody>
    </table>
  </div>
</div>

<!-- TAB 2: User Debug Traces -->
<div class="card" id="dbg-panel" style="display:none">
  <div class="toolbar">
    <h2>🐞 Granular User Traces (Bug Diagnostics)</h2>
    <input id="dbg-srch" type="text" placeholder="Filter by User ID or text…">
    <span id="dbg-count" style="font-size:12px;color:var(--tdd);margin-left:auto"></span>
  </div>
  <div class="tw">
    <table>
      <thead><tr>
        <th>Time</th><th>User ID</th><th>Username</th><th>Event</th><th>Feature</th><th>Message / Error</th><th>Data Payload</th>
      </tr></thead>
      <tbody id="dbg-tb"><tr><td colspan="7" class="spin-wrap"><div class="spin"></div></td></tr></tbody>
    </table>
  </div>
</div>

</div><!-- /wrap -->

<!-- User Inspect Modal -->
<div class="modal-overlay" id="user-modal" onclick="if(event.target===this)closeModal()">
  <div class="modal">
    <div class="modal-head">
      <h3 id="m-title">User Debug Traces</h3>
      <button class="modal-close" onclick="closeModal()">&times;</button>
    </div>
    <div class="modal-body" id="m-body">
      <div class="spin-wrap"><div class="spin"></div></div>
    </div>
  </div>
</div>

<div class="cbar"><div class="cfill" id="cf" style="width:100%"></div></div>

<script>
const KEY = new URLSearchParams(location.search).get('key') || (document.cookie.match(/monitor_key=([^;]+)/)||[])[1] || '';
const API  = `/api/data?key=${encodeURIComponent(KEY)}`;
const FLAGAPI = id => `/api/flag/${id}?key=${encodeURIComponent(KEY)}`;
const STOPBFAPI = id => `/api/bf/stop/${id}?key=${encodeURIComponent(KEY)}`;
const INTERVAL = 30;

const FL = {add:'Add Email',check:'Check Email',platform:'Platform',cancel:'Cancel Email',revoke:'Revoke Token',unbind:'Unbind Email',change:'Change Bind',bf:'Security Code BF'};
const FC = {add:'#00f5ff',check:'#10b981',platform:'#a855f7',cancel:'#f97316',revoke:'#ef4444',unbind:'#eab308',change:'#3b82f6',bf:'#ec4899'};

let ALL=[], DBG=[], cc=null, lc=null, timer=INTERVAL, curTab='activities';

function switchTab(tab){
  curTab = tab;
  document.getElementById('tab-act-btn').classList.toggle('active', tab==='activities');
  document.getElementById('tab-dbg-btn').classList.toggle('active', tab==='debugger');
  document.getElementById('act-panel').style.display = (tab==='activities') ? 'block' : 'none';
  document.getElementById('dbg-panel').style.display = (tab==='debugger') ? 'block' : 'none';
  document.getElementById('charts-sec').style.display = (tab==='activities') ? 'grid' : 'none';
  if(tab==='debugger') renderDebugTable();
}

async function load(){
  try{
    const r = await fetch(API);
    const d = await r.json();
    ALL = d.activities || [];
    DBG = d.debug_logs || [];
    renderStats(d.stats || {});
    renderAlerts(d.alerts || []);
    renderCharts(d.stats || {});
    renderLiveBruteForce(d.active_bf || [], d.recent_bf || []);
    renderTable();
    if(curTab==='debugger') renderDebugTable();
  }catch(e){console.error(e)}
}

function renderStats(s){
  document.getElementById('s0').textContent = s.total ?? '—';
  document.getElementById('s1').textContent = s.unique_users ?? '—';
  document.getElementById('s2').textContent = s.unique_emails ?? '—';
  document.getElementById('s3').textContent = s.today ?? '—';
  document.getElementById('s4').textContent = s.active_bf ?? '0';
}

function renderAlerts(al){
  document.getElementById('s5').textContent = al.length;
  const w = document.getElementById('awrap');
  if(!al.length){w.classList.remove('on'); return;}
  w.classList.add('on');
  document.getElementById('alist').innerHTML = al.map(a =>
    `<div class="ai ${a.level}">${a.icon} ${a.msg}</div>`).join('');
}

function renderLiveBruteForce(activeList, recentList){
  const wrap = document.getElementById('bf-wrap');
  const dot = document.getElementById('bf-dot');
  const badge = document.getElementById('bf-badge');
  const content = document.getElementById('bf-content');

  if(activeList.length > 0){
    wrap.classList.add('active');
    dot.className = 'bf-dot live';
    badge.className = 'bf-status-badge live';
    badge.textContent = `🔥 ${activeList.length} RUNNING`;

    content.innerHTML = `<div class="bf-grid">` + activeList.map(b => {
      const uDisplay = b.username ? `@${escapeHtml(b.username)}` : `ID:${b.user_id}`;
      return `
        <div class="bf-card">
          <div class="bf-row">
            <span style="font-weight:700;color:var(--pink)">⚡ Session #${b.id}</span>
            <button class="stop-bf-btn" onclick="stopBfSession(${b.id})">🛑 Stop Attack</button>
          </div>
          <div class="bf-row">
            <span class="bf-lbl">Target User</span>
            <a class="user-link" onclick="openUserLogs(${b.user_id}, '${escapeHtml(b.username||'')}')">${uDisplay}</a>
          </div>
          <div class="bf-row">
            <span class="bf-lbl">Target Email</span>
            <span class="code" style="color:var(--cyan)">${escapeHtml(b.email)}</span>
          </div>
          <div class="bf-row">
            <span class="bf-lbl">Full Token</span>
            <div class="token-box" style="max-width:200px">
              <span class="token-text" title="${escapeHtml(b.access_token)}">${escapeHtml(b.access_token)}</span>
              <button class="copy-btn" onclick="copyText('${escapeHtml(b.access_token)}', this)">📋</button>
            </div>
          </div>
          <div class="bf-row" style="margin-top:6px">
            <span class="bf-lbl">Security Codes Tried</span>
            <span style="font-weight:700;color:var(--yellow)">${(b.attempts||0).toLocaleString()} / 1,000,000</span>
          </div>
          <div class="bf-row">
            <span class="bf-lbl">Started</span>
            <span class="ts">${(b.started_at||'').replace('T',' ')}</span>
          </div>
          <div class="bf-progress-bar"><div class="bf-progress-fill"></div></div>
        </div>
      `;
    }).join('') + `</div>`;
  } else {
    wrap.classList.remove('active');
    dot.className = 'bf-dot';
    badge.className = 'bf-status-badge';
    badge.textContent = 'Idle';

    let recentSummary = '';
    if(recentList && recentList.length > 0){
      const last = recentList[0];
      const resColor = last.status==='success' ? 'var(--green)' : last.status==='stopped_by_admin' ? 'var(--orange)' : 'var(--red)';
      recentSummary = `
        <div style="margin-top:8px;font-size:11.5px;color:var(--td)">
          🕒 <b>Last Session:</b> #${last.id} on <code>${escapeHtml(last.email)}</code> &mdash;
          Status: <b style="color:${resColor}">${last.status.toUpperCase()}</b>
          ${last.found_code ? `(Found Security Code: <code>${last.found_code}</code>)` : `(${last.attempts||0} codes tested)`}
        </div>
      `;
    }

    content.innerHTML = `
      <div style="color:var(--tdd);font-size:12.5px">🟢 No brute force operations currently running.</div>
      ${recentSummary}
    `;
  }
}

async function stopBfSession(id){
  if(!confirm(`Kya aap session #${id} brute force ko turant terminate karna chahte hain?`)) return;
  try{
    const r = await fetch(STOPBFAPI(id), {method:'POST'});
    const d = await r.json();
    alert(`🛑 Brute Force session #${id} stop kar diya gaya hai.`);
    load();
  }catch(e){
    alert('Failed to stop: ' + e);
  }
}

function renderCharts(s){
  const bf = s.by_feature || {};
  const fts = Object.keys(bf), cnts = fts.map(f=>bf[f]), cols = fts.map(f=>FC[f]||'#475569');
  if(cc) cc.destroy();
  cc = new Chart(document.getElementById('cc').getContext('2d'),{
    type:'doughnut',
    data:{labels:fts.map(f=>FL[f]||f),datasets:[{data:cnts,backgroundColor:cols,borderWidth:0,hoverOffset:8}]},
    options:{responsive:true,maintainAspectRatio:false,cutout:'68%',
      plugins:{legend:{position:'right',labels:{color:'#94a3b8',font:{size:10},padding:10,boxWidth:10}}}}
  });
  const days = (s.last_7_days||[]).map(d=>d.date), dcts = (s.last_7_days||[]).map(d=>d.count);
  if(lc) lc.destroy();
  lc = new Chart(document.getElementById('lc').getContext('2d'),{
    type:'line',
    data:{labels:days,datasets:[{label:'Ops',data:dcts,borderColor:'#00f5ff',
      backgroundColor:'rgba(0,245,255,.07)',fill:true,tension:.4,
      pointBackgroundColor:'#00f5ff',pointRadius:4,pointHoverRadius:6}]},
    options:{responsive:true,maintainAspectRatio:false,
      plugins:{legend:{display:false}},
      scales:{
        x:{grid:{color:'rgba(255,255,255,.04)'},ticks:{color:'#475569',font:{size:10}}},
        y:{grid:{color:'rgba(255,255,255,.04)'},ticks:{color:'#475569',font:{size:10}},beginAtZero:true}
      }}
  });
}

function renderTable(){
  const srch = document.getElementById('srch').value.toLowerCase();
  const ff = document.getElementById('ff').value;
  const rf = document.getElementById('rf2').value;
  let rows = ALL.filter(r=>{
    if(ff && r.feature!==ff) return false;
    if(rf && r.result!==rf) return false;
    if(srch){
      const h = `${r.email||''} ${r.username||''} ${r.user_id||''} ${r.access_token||''}`.toLowerCase();
      if(!h.includes(srch)) return false;
    }
    return true;
  });
  document.getElementById('row-count').textContent = `${rows.length} operations`;
  const tb = document.getElementById('tb');
  if(!rows.length){tb.innerHTML='<tr><td colspan="8" class="nd">No operations recorded yet</td></tr>'; return;}
  tb.innerHTML = rows.map(r=>{
    const rc = r.result==='success'?'rs':r.result==='failed'?'rf':'rp';
    const ts = (r.ts||'').replace('T',' ');
    const flagOn = r.flagged ? 'on' : '';
    const flagIcon = r.flagged ? '🚩' : '⚑';
    const rawTok = r.access_token || '';
    const tokHtml = rawTok ? `
      <div class="token-box">
        <span class="token-text" title="${escapeHtml(rawTok)}">${escapeHtml(rawTok)}</span>
        <button class="copy-btn" onclick="copyText('${escapeHtml(rawTok)}', this)" title="Copy Full Token">📋</button>
      </div>
    ` : '<span style="color:var(--tdd)">—</span>';

    return `<tr class="${r.flagged?'fr':''}" id="row-${r.id}">
      <td class="code" style="color:var(--tdd)">${r.id}</td>
      <td class="ts">${ts}</td>
      <td>
        <div><a class="user-link" onclick="openUserLogs(${r.user_id}, '${escapeHtml(r.username||'')}')">${r.username?'@'+escapeHtml(r.username):'ID:'+r.user_id}</a></div>
        <div style="font-size:10px;color:var(--tdd)">${escapeHtml(r.first_name||'')} (Click to debug)</div>
      </td>
      <td><span class="badge b-${r.feature}">${FL[r.feature]||r.feature}</span></td>
      <td class="code">${r.email?escapeHtml(r.email):'<span style="color:var(--tdd)">—</span>'}</td>
      <td>${tokHtml}</td>
      <td class="${rc}">${r.result||'—'}</td>
      <td><button class="flag-btn ${flagOn}" onclick="doFlag(${r.id})" title="${r.flagged?'Unflag':'Flag'}">${flagIcon}</button></td>
    </tr>`;
  }).join('');
}

function renderDebugTable(){
  const srch = (document.getElementById('dbg-srch').value || '').toLowerCase();
  let rows = DBG.filter(d=>{
    if(srch){
      const h = `${d.user_id||''} ${d.username||''} ${d.event_type||''} ${d.message||''} ${d.data||''}`.toLowerCase();
      if(!h.includes(srch)) return false;
    }
    return true;
  });
  document.getElementById('dbg-count').textContent = `${rows.length} trace records`;
  const tb = document.getElementById('dbg-tb');
  if(!rows.length){tb.innerHTML='<tr><td colspan="7" class="nd">No debug traces found</td></tr>'; return;}
  tb.innerHTML = rows.map(d=>{
    const ts = (d.ts||'').replace('T',' ');
    const isErr = d.event_type==='error' || (d.message||'').toLowerCase().includes('fail') || (d.message||'').toLowerCase().includes('error');
    return `<tr style="${isErr?'background:rgba(239,68,68,.06)':''}">
      <td class="ts">${ts}</td>
      <td class="code"><a class="user-link" onclick="openUserLogs(${d.user_id}, '${escapeHtml(d.username||'')}')">${d.user_id}</a></td>
      <td style="font-weight:500">${d.username?'@'+escapeHtml(d.username):'—'}</td>
      <td><span class="badge" style="background:rgba(255,255,255,.08)">${escapeHtml(d.event_type||'')}</span></td>
      <td><span class="badge b-${d.feature}">${FL[d.feature]||d.feature||'—'}</span></td>
      <td style="color:${isErr?'var(--red)':'var(--t)'}">${escapeHtml(d.message||'—')}</td>
      <td class="code" style="max-width:320px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="${escapeHtml(d.data||'')}">${escapeHtml(d.data||'—')}</td>
    </tr>`;
  }).join('');
}

async function openUserLogs(userId, username){
  document.getElementById('user-modal').classList.add('open');
  document.getElementById('m-title').textContent = `🐞 User Traces: ${username?'@'+username:userId} (ID: ${userId})`;
  const body = document.getElementById('m-body');
  body.innerHTML = '<div class="spin-wrap"><div class="spin"></div></div>';
  try{
    const r = await fetch(`/api/user-logs/${userId}?key=${encodeURIComponent(KEY)}`);
    const d = await r.json();
    const logs = d.logs || [];
    const acts = d.activities || [];
    if(!logs.length && !acts.length){
      body.innerHTML = '<div class="nd">No logs or activities recorded for this user yet.</div>';
      return;
    }
    let html = `<div style="margin-bottom:18px"><h4 style="margin-bottom:8px;font-size:13px;color:var(--cyan)">Recent Activities:</h4>`;
    if(acts.length){
      html += `<table style="width:100%;margin-bottom:16px"><thead><tr><th>Time</th><th>Feature</th><th>Email</th><th>Token</th><th>Result</th></tr></thead><tbody>`;
      acts.forEach(a=>{
        html += `<tr>
          <td class="ts">${(a.ts||'').replace('T',' ')}</td>
          <td><span class="badge b-${a.feature}">${FL[a.feature]||a.feature}</span></td>
          <td class="code">${escapeHtml(a.email||'—')}</td>
          <td class="code" style="max-width:180px;overflow:hidden;text-overflow:ellipsis" title="${escapeHtml(a.access_token||'')}">${escapeHtml(a.access_token||'—')}</td>
          <td>${a.result}</td>
        </tr>`;
      });
      html += `</tbody></table>`;
    } else {
      html += '<p style="color:var(--tdd);font-size:12px">No feature activity</p>';
    }
    html += `</div><div><h4 style="margin-bottom:8px;font-size:13px;color:var(--purple)">Detailed Debug Traces:</h4>`;
    if(logs.length){
      html += `<table style="width:100%"><thead><tr><th>Time</th><th>Event</th><th>Feature</th><th>Message</th><th>Payload Data</th></tr></thead><tbody>`;
      logs.forEach(l=>{
        html += `<tr>
          <td class="ts">${(l.ts||'').replace('T',' ')}</td>
          <td><span class="badge">${escapeHtml(l.event_type||'')}</span></td>
          <td><span class="badge b-${l.feature}">${FL[l.feature]||l.feature||'—'}</span></td>
          <td>${escapeHtml(l.message||'—')}</td>
          <td class="code" style="max-width:240px;overflow:hidden;text-overflow:ellipsis" title="${escapeHtml(l.data||'')}">${escapeHtml(l.data||'—')}</td>
        </tr>`;
      });
      html += `</tbody></table>`;
    } else {
      html += '<p style="color:var(--tdd);font-size:12px">No granular debug traces</p>';
    }
    html += `</div>`;
    body.innerHTML = html;
  }catch(e){
    body.innerHTML = `<div class="nd" style="color:var(--red)">Failed to load user logs: ${e}</div>`;
  }
}

function closeModal(){
  document.getElementById('user-modal').classList.remove('open');
}

function copyText(txt, btn){
  navigator.clipboard.writeText(txt).then(()=>{
    const old = btn.textContent;
    btn.textContent = '✅';
    setTimeout(()=>btn.textContent=old, 1500);
  });
}

function escapeHtml(str){
  if(!str) return '';
  return String(str).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;').replace(/'/g,'&#39;');
}

async function doFlag(id){
  try{
    const r = await fetch(FLAGAPI(id),{method:'POST'});
    const d = await r.json();
    const e = ALL.find(a=>a.id===id);
    if(e) e.flagged = d.flagged ? 1 : 0;
    renderTable();
  }catch(e){console.error(e)}
}

function tick(){
  timer--;
  document.getElementById('cd').textContent = timer;
  document.getElementById('cf').style.width = (timer/INTERVAL*100)+'%';
  if(timer<=0){timer=INTERVAL; load();}
}

document.getElementById('srch').addEventListener('input',renderTable);
document.getElementById('ff').addEventListener('change',renderTable);
document.getElementById('rf2').addEventListener('change',renderTable);
document.getElementById('dbg-srch').addEventListener('input',renderDebugTable);

load();
setInterval(tick,1000);
</script>
</body>
</html>
"""

LOGIN_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Garena Monitor — Master Key Required</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
:root{
  --bg:#07070f;--s:rgba(255,255,255,.05);--b:rgba(255,255,255,.1);
  --cyan:#00f5ff;--purple:#a855f7;--red:#ef4444;--t:#e2e8f0;--td:#94a3b8;
}
body{
  background:var(--bg);color:var(--t);font-family:'Inter',sans-serif;
  min-height:100vh;display:flex;align-items:center;justify-content:center;
  padding:20px;position:relative;overflow:hidden;
}
body::before{
  content:'';position:fixed;inset:0;pointer-events:none;
  background:
    radial-gradient(ellipse 60% 40% at 30% 20%,rgba(0,245,255,.08) 0,transparent 60%),
    radial-gradient(ellipse 50% 40% at 70% 80%,rgba(168,85,247,.08) 0,transparent 60%);
}
.card{
  width:100%;max-width:420px;background:var(--s);border:1px solid var(--b);
  border-radius:20px;padding:36px 32px;backdrop-filter:blur(20px);
  position:relative;z-index:1;box-shadow:0 20px 50px rgba(0,0,0,.5);
}
.icon{
  width:56px;height:56px;border-radius:14px;
  background:linear-gradient(135deg,var(--cyan),var(--purple));
  display:flex;align-items:center;justify-content:center;
  font-size:28px;margin:0 auto 20px;
}
h1{font-size:22px;font-weight:700;text-align:center;letter-spacing:-.5px;margin-bottom:6px}
h1 span{color:var(--cyan)}
p{font-size:13px;color:var(--td);text-align:center;line-height:1.5;margin-bottom:28px}
.form-group{margin-bottom:18px}
label{display:block;font-size:12px;font-weight:600;margin-bottom:8px;color:var(--td);text-transform:uppercase;letter-spacing:.5px}
input{
  width:100%;background:rgba(255,255,255,.04);border:1px solid var(--b);
  border-radius:10px;padding:12px 16px;font-size:14px;color:var(--t);
  font-family:inherit;outline:none;transition:all .2s;
}
input:focus{border-color:var(--cyan);box-shadow:0 0 15px rgba(0,245,255,.2)}
button{
  width:100%;padding:13px;border:none;border-radius:10px;
  background:linear-gradient(135deg,var(--cyan),var(--purple));
  color:#000;font-weight:700;font-size:14px;cursor:pointer;
  transition:transform .15s, opacity .15s;margin-top:8px;
}
button:hover{opacity:.95;transform:translateY(-1px)}
button:active{transform:translateY(1px)}
.err{display:none;background:rgba(239,68,68,.15);border:1px solid rgba(239,68,68,.4);color:#fca5a5;padding:10px 12px;border-radius:8px;font-size:12.5px;margin-bottom:16px;text-align:center}
</style>
</head>
<body>
<div class="card">
  <div class="icon">🛡️</div>
  <h1>Garena <span>Monitor</span></h1>
  <p>Dashboard access karne ke liye Master Key enter karein</p>
  <div class="err" id="errmsg">❌ Invalid Master Key! Sahi key enter karein.</div>
  <form id="lform" onsubmit="handleLogin(event)">
    <div class="form-group">
      <label for="mk">Master Key</label>
      <input type="password" id="mk" placeholder="Master key yahan dalein..." autocomplete="current-password" autofocus required>
    </div>
    <button type="submit">Unlock Dashboard 🚀</button>
  </form>
</div>
<script>
async function handleLogin(e){
  e.preventDefault();
  const key = document.getElementById('mk').value.trim();
  if(!key) return;
  try{
    const r = await fetch(`/api/data?key=${encodeURIComponent(key)}`);
    if(r.ok){
      document.cookie = `monitor_key=${encodeURIComponent(key)};path=/;max-age=2592000`;
      window.location.href = `/monitor?key=${encodeURIComponent(key)}`;
    } else {
      document.getElementById('errmsg').style.display = 'block';
    }
  }catch(err){
    window.location.href = `/monitor?key=${encodeURIComponent(key)}`;
  }
}
</script>
</body>
</html>
"""
