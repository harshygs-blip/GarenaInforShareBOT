"""Monitoring web dashboard and aiohttp API handlers for Garena Bot."""

import asyncio
import os
import threading

from aiohttp import web

import db

MONITORING_KEY = os.environ.get("MONITORING_KEY", "admin123")

# ─── Auth ────────────────────────────────────────────────────────────────────

def _auth(req: web.Request) -> bool:
    return req.rel_url.query.get("key") == MONITORING_KEY

# ─── Handlers ────────────────────────────────────────────────────────────────

async def _root(req: web.Request) -> web.Response:
    key = req.rel_url.query.get("key") or MONITORING_KEY
    raise web.HTTPFound(f"/monitor?key={key}")


async def _dashboard(req: web.Request) -> web.Response:
    if not _auth(req):
        return web.Response(
            status=403,
            content_type="text/html",
            text="<h2 style='font-family:sans-serif;color:#ef4444;padding:40px'>"
                 "403 — Invalid or missing monitoring key.</h2>",
        )
    return web.Response(text=DASHBOARD_HTML, content_type="text/html")


async def _api_data(req: web.Request) -> web.Response:
    if not _auth(req):
        return web.json_response({"error": "forbidden"}, status=403)
    feature = req.rel_url.query.get("feature") or None
    result  = req.rel_url.query.get("result")  or None
    search  = req.rel_url.query.get("search")  or None
    return web.json_response({
        "activities": db.get_activities(limit=500, feature=feature, result=result, search=search),
        "stats":      db.get_stats(),
        "alerts":     db.get_alerts(),
    })


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
        web.get("/",               _root),
        web.get("/monitor",        _dashboard),
        web.get("/api/data",       _api_data),
        web.post("/api/flag/{id}", _api_flag),
    ]


def start_polling_monitor(port: int = 8081) -> None:
    """Start monitoring in a background thread (for local polling mode)."""
    if not MONITORING_KEY:
        print("[Monitor] MONITORING_KEY not set — dashboard disabled.")
        return

    def _run() -> None:
        async def _main() -> None:
            app = web.Application()
            app.router.add_get("/",               _root)
            app.router.add_get("/monitor",        _dashboard)
            app.router.add_get("/api/data",       _api_data)
            app.router.add_post("/api/flag/{id}", _api_flag)
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
<title>Garena Bot Monitor</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
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
.wrap{position:relative;z-index:1;max-width:1440px;margin:0 auto;padding:0 24px 64px}

/* ── Header ── */
header{display:flex;align-items:center;justify-content:space-between;padding:24px 0 28px;border-bottom:1px solid var(--b);margin-bottom:28px}
.logo{display:flex;align-items:center;gap:12px}
.logo-icon{width:42px;height:42px;border-radius:11px;background:linear-gradient(135deg,var(--cyan),var(--purple));display:flex;align-items:center;justify-content:center;font-size:22px}
.logo-name{font-size:18px;font-weight:700;letter-spacing:-.5px}
.logo-name span{color:var(--cyan)}
.logo-sub{font-size:11px;color:var(--tdd);margin-top:2px}
.live-badge{display:flex;align-items:center;gap:8px;background:var(--s);border:1px solid var(--b);border-radius:8px;padding:7px 13px;font-size:12px;color:var(--td)}
.dot{width:7px;height:7px;border-radius:50%;background:var(--green);animation:pulse 2s infinite}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.3}}

/* ── Card ── */
.card{background:var(--s);border:1px solid var(--b);border-radius:16px;padding:22px;backdrop-filter:blur(12px);transition:border-color .2s}
.card:hover{border-color:var(--b2)}

/* ── Stats ── */
.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:14px;margin-bottom:24px}
.sc{padding:18px 20px;position:relative;overflow:hidden;border-radius:16px}
.sc::after{content:'';position:absolute;top:0;left:0;right:0;height:2px;border-radius:2px 2px 0 0}
.sc.c::after{background:linear-gradient(90deg,var(--cyan),transparent)}
.sc.p::after{background:linear-gradient(90deg,var(--purple),transparent)}
.sc.g::after{background:linear-gradient(90deg,var(--green),transparent)}
.sc.o::after{background:linear-gradient(90deg,var(--orange),transparent)}
.sc.b::after{background:linear-gradient(90deg,var(--blue),transparent)}
.sc.r::after{background:linear-gradient(90deg,var(--red),transparent)}
.sl{font-size:10px;text-transform:uppercase;letter-spacing:1px;color:var(--tdd);margin-bottom:8px}
.sv{font-size:30px;font-weight:700;line-height:1}
.sv.c{color:var(--cyan)}.sv.p{color:var(--purple)}.sv.g{color:var(--green)}
.sv.o{color:var(--orange)}.sv.b{color:var(--blue)}.sv.r{color:var(--red)}
.ss{font-size:11px;color:var(--td);margin-top:5px}

/* ── Alerts ── */
.alerts-wrap{margin-bottom:24px;display:none}
.alerts-wrap.on{display:block}
.ah{font-size:13px;font-weight:600;margin-bottom:10px;display:flex;align-items:center;gap:7px}
.ai{padding:9px 13px;border-radius:8px;font-size:13px;line-height:1.55;margin-bottom:7px}
.ai.danger{background:rgba(239,68,68,.1);border:1px solid rgba(239,68,68,.3)}
.ai.warning{background:rgba(245,158,11,.1);border:1px solid rgba(245,158,11,.3)}

/* ── Charts ── */
.charts{display:grid;grid-template-columns:1fr 2fr;gap:16px;margin-bottom:24px}
@media(max-width:768px){.charts{grid-template-columns:1fr}}
.ct{font-size:12px;font-weight:600;color:var(--td);margin-bottom:14px;text-transform:uppercase;letter-spacing:.5px}

/* ── Toolbar ── */
.toolbar{display:flex;align-items:center;gap:10px;margin-bottom:14px;flex-wrap:wrap}
.toolbar h2{font-size:14px;font-weight:600;flex:1;min-width:100px}
input,select{
  background:var(--s);border:1px solid var(--b);border-radius:8px;
  color:var(--t);padding:7px 11px;font-size:12px;font-family:inherit;
  outline:none;transition:border-color .2s
}
input:focus,select:focus{border-color:var(--cyan)}
input{width:190px}
select option{background:#1a1a2e}

/* ── Table ── */
.tw{overflow-x:auto;border-radius:10px}
table{width:100%;border-collapse:collapse;font-size:12.5px}
thead th{
  padding:9px 11px;text-align:left;font-size:10.5px;font-weight:600;
  text-transform:uppercase;letter-spacing:.5px;color:var(--tdd);
  border-bottom:1px solid var(--b);background:rgba(255,255,255,.02);white-space:nowrap
}
tbody tr{border-bottom:1px solid rgba(255,255,255,.03);transition:background .15s}
tbody tr:hover{background:rgba(255,255,255,.03)}
tbody tr.fr{background:rgba(239,68,68,.06)}
td{padding:9px 11px;vertical-align:middle}

/* ── Badges ── */
.badge{display:inline-flex;align-items:center;padding:3px 7px;border-radius:5px;font-size:10.5px;font-weight:600;white-space:nowrap}
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
.rp{color:var(--tdd)}

.flag-btn{background:none;border:none;cursor:pointer;font-size:14px;padding:3px 6px;border-radius:6px;transition:background .15s;color:var(--tdd)}
.flag-btn:hover{background:var(--s2);color:var(--red)}
.flag-btn.on{color:var(--red)}

.code{font-family:monospace;font-size:11.5px;color:var(--td)}
.ts{font-size:11px;color:var(--tdd);white-space:nowrap}
.nd{text-align:center;padding:40px;color:var(--tdd);font-size:13px}
.spin-wrap{text-align:center;padding:50px}
.spin{display:inline-block;width:28px;height:28px;border:3px solid var(--b);border-top-color:var(--cyan);border-radius:50%;animation:sp .8s linear infinite}
@keyframes sp{to{transform:rotate(360deg)}}

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
      <div class="logo-name">Garena <span>Monitor</span></div>
      <div class="logo-sub">Bot Security Dashboard</div>
    </div>
  </div>
  <div class="live-badge">
    <span class="dot"></span>
    Live &mdash; refresh in <span id="cd">30</span>s
  </div>
</header>

<!-- Stats -->
<div class="stats" id="stats">
  <div class="card sc c"><div class="sl">Total Operations</div><div class="sv c" id="s0">—</div></div>
  <div class="card sc p"><div class="sl">Unique Users</div><div class="sv p" id="s1">—</div></div>
  <div class="card sc g"><div class="sl">Unique Emails</div><div class="sv g" id="s2">—</div></div>
  <div class="card sc o"><div class="sl">Today</div><div class="sv o" id="s3">—</div></div>
  <div class="card sc b"><div class="sl">Success Rate</div><div class="sv b" id="s4">—</div></div>
  <div class="card sc r"><div class="sl">Security Alerts</div><div class="sv r" id="s5">—</div></div>
</div>

<!-- Alerts -->
<div class="card alerts-wrap" id="awrap">
  <div class="ah">⚠️ Security Alerts</div>
  <div id="alist"></div>
</div>

<!-- Charts -->
<div class="charts">
  <div class="card"><div class="ct">📊 By Feature</div><div style="position:relative;height:220px"><canvas id="cc"></canvas></div></div>
  <div class="card"><div class="ct">📈 Last 7 Days Activity</div><div style="position:relative;height:220px"><canvas id="lc"></canvas></div></div>
</div>

<!-- Activity Log -->
<div class="card">
  <div class="toolbar">
    <h2>📋 Activity Log</h2>
    <input id="srch" type="text" placeholder="Search email / user…">
    <select id="ff">
      <option value="">All Features</option>
      <option value="add">Add Email</option>
      <option value="check">Check Email</option>
      <option value="platform">Platform</option>
      <option value="cancel">Cancel Email</option>
      <option value="revoke">Revoke Token</option>
      <option value="unbind">Unbind Email</option>
      <option value="change">Change Bind</option>
      <option value="bf">Brute Force</option>
    </select>
    <select id="rf2">
      <option value="">All Results</option>
      <option value="success">✅ Success</option>
      <option value="failed">❌ Failed</option>
      <option value="pending">⏳ Pending</option>
    </select>
    <span id="row-count" style="font-size:12px;color:var(--tdd);margin-left:auto"></span>
  </div>
  <div class="tw">
    <table>
      <thead><tr>
        <th>#</th><th>Time</th><th>User</th><th>Feature</th>
        <th>Email</th><th>Token</th><th>Result</th><th>Flag</th>
      </tr></thead>
      <tbody id="tb"><tr><td colspan="8" class="spin-wrap"><div class="spin"></div></td></tr></tbody>
    </table>
  </div>
</div>

</div><!-- /wrap -->
<div class="cbar"><div class="cfill" id="cf" style="width:100%"></div></div>

<script>
const KEY = new URLSearchParams(location.search).get('key')||'';
const API  = `/api/data?key=${KEY}`;
const FLAGAPI = id => `/api/flag/${id}?key=${KEY}`;
const INTERVAL = 30;

const FL = {add:'Add Email',check:'Check Email',platform:'Platform',cancel:'Cancel Email',revoke:'Revoke Token',unbind:'Unbind Email',change:'Change Bind',bf:'Brute Force'};
const FC = {add:'#00f5ff',check:'#10b981',platform:'#a855f7',cancel:'#f97316',revoke:'#ef4444',unbind:'#eab308',change:'#3b82f6',bf:'#ec4899'};

let ALL=[], cc=null, lc=null, timer=INTERVAL;

async function load(){
  try{
    const r=await fetch(API); const d=await r.json();
    ALL=d.activities||[];
    renderStats(d.stats||{});
    renderAlerts(d.alerts||[]);
    renderCharts(d.stats||{});
    renderTable();
  }catch(e){console.error(e)}
}

function renderStats(s){
  document.getElementById('s0').textContent=s.total??'—';
  document.getElementById('s1').textContent=s.unique_users??'—';
  document.getElementById('s2').textContent=s.unique_emails??'—';
  document.getElementById('s3').textContent=s.today??'—';
  document.getElementById('s4').textContent=s.success_rate!=null?s.success_rate+'%':'—';
}

function renderAlerts(al){
  document.getElementById('s5').textContent=al.length;
  const w=document.getElementById('awrap');
  if(!al.length){w.classList.remove('on');return}
  w.classList.add('on');
  document.getElementById('alist').innerHTML=al.map(a=>
    `<div class="ai ${a.level}">${a.icon} ${a.msg}</div>`).join('');
}

function renderCharts(s){
  const bf=s.by_feature||{};
  const fts=Object.keys(bf), cnts=fts.map(f=>bf[f]), cols=fts.map(f=>FC[f]||'#475569');
  if(cc)cc.destroy();
  cc=new Chart(document.getElementById('cc').getContext('2d'),{
    type:'doughnut',
    data:{labels:fts.map(f=>FL[f]||f),datasets:[{data:cnts,backgroundColor:cols,borderWidth:0,hoverOffset:8}]},
    options:{responsive:true,maintainAspectRatio:false,cutout:'68%',
      plugins:{legend:{position:'right',labels:{color:'#94a3b8',font:{size:10},padding:10,boxWidth:10}}}}
  });
  const days=(s.last_7_days||[]).map(d=>d.date), dcts=(s.last_7_days||[]).map(d=>d.count);
  if(lc)lc.destroy();
  lc=new Chart(document.getElementById('lc').getContext('2d'),{
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
  const srch=document.getElementById('srch').value.toLowerCase();
  const ff=document.getElementById('ff').value;
  const rf=document.getElementById('rf2').value;
  let rows=ALL.filter(r=>{
    if(ff&&r.feature!==ff)return false;
    if(rf&&r.result!==rf)return false;
    if(srch){
      const h=`${r.email||''} ${r.username||''} ${r.user_id||''}`.toLowerCase();
      if(!h.includes(srch))return false;
    }
    return true;
  });
  document.getElementById('row-count').textContent=`${rows.length} rows`;
  const tb=document.getElementById('tb');
  if(!rows.length){tb.innerHTML='<tr><td colspan="8" class="nd">No records found</td></tr>';return}
  tb.innerHTML=rows.map(r=>{
    const rc=r.result==='success'?'rs':r.result==='failed'?'rf':'rp';
    const ts=(r.ts||'').replace('T',' ');
    const flagOn=r.flagged?'on':'';
    const flagIcon=r.flagged?'🚩':'⚑';
    return`<tr class="${r.flagged?'fr':''}" id="row-${r.id}">
      <td class="code" style="color:var(--tdd)">${r.id}</td>
      <td class="ts">${ts}</td>
      <td>
        <div style="font-weight:500">${r.username?'@'+r.username:'ID:'+r.user_id}</div>
        <div style="font-size:10px;color:var(--tdd)">${r.first_name||''}</div>
      </td>
      <td><span class="badge b-${r.feature}">${FL[r.feature]||r.feature}</span></td>
      <td class="code">${r.email||'<span style="color:var(--tdd)">—</span>'}</td>
      <td class="code">${r.token_hint||'<span style="color:var(--tdd)">—</span>'}</td>
      <td class="${rc}">${r.result||'—'}</td>
      <td><button class="flag-btn ${flagOn}" onclick="doFlag(${r.id})" title="${r.flagged?'Unflag':'Flag'}">${flagIcon}</button></td>
    </tr>`;
  }).join('');
}

async function doFlag(id){
  try{
    const r=await fetch(FLAGAPI(id),{method:'POST'});
    const d=await r.json();
    const e=ALL.find(a=>a.id===id);
    if(e)e.flagged=d.flagged?1:0;
    renderTable();
  }catch(e){console.error(e)}
}

function tick(){
  timer--;
  document.getElementById('cd').textContent=timer;
  document.getElementById('cf').style.width=(timer/INTERVAL*100)+'%';
  if(timer<=0){timer=INTERVAL;load()}
}

document.getElementById('srch').addEventListener('input',renderTable);
document.getElementById('ff').addEventListener('change',renderTable);
document.getElementById('rf2').addEventListener('change',renderTable);

load();
setInterval(tick,1000);
</script>
</body>
</html>
"""
