/* BRAWLVERSE API on Cloudflare Workers + D1.
 * Mirrors server/app.py. Anti-fraud v1: one vote per device per round,
 * per-IP rate limit (D1-backed), device id SHA-256 hashed.
 */

const CHOICES = new Set(["heavy", "dodge", "guard"]);
const RATE_LIMIT = 20, RATE_WINDOW_S = 60;
const ALLOW_ORIGIN = "https://zjutimes2015.github.io";

const ADMIN_HTML = `<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>BOOKER ADMIN — BRAWLVERSE</title>
<style>body{background:#0d0d0d;color:#eee;font-family:system-ui;max-width:900px;margin:0 auto;padding:20px}
h1{color:#fc0;letter-spacing:2px}.card{background:#161616;border:1px solid #333;border-radius:10px;padding:16px;margin:14px 0}
button{background:#fc0;border:0;border-radius:6px;padding:8px 16px;font-weight:700;cursor:pointer;margin:4px}
button.ghost{background:#333;color:#eee}input{background:#222;color:#eee;border:1px solid #444;border-radius:6px;padding:8px;margin:4px}
.bar{height:14px;background:#fc0;border-radius:4px}.row{display:flex;gap:10px;align-items:center;flex-wrap:wrap}.small{color:#888;font-size:12px}</style>
</head><body><h1>BOOKER ADMIN</h1>
<div class="card"><div class="row"><input id="token" type="password" placeholder="Admin token" style="flex:1">
<button onclick="load()">Connect</button></div><p class="small">Token = ADMIN_TOKEN secret on the Worker.</p></div>
<div id="bouts"></div>
<script>
let TOKEN='';
async function api(path,opts={}){opts.headers=Object.assign({'X-Admin-Token':TOKEN,'Content-Type':'application/json'},opts.headers||{});
const r=await fetch(path,opts);if(!r.ok)throw new Error(await r.text());return r.json();}
async function load(){TOKEN=document.getElementById('token').value;
const bouts=await api('/api/bouts').catch(e=>alert('Auth failed: '+e.message));if(!bouts)return;
const box=document.getElementById('bouts');box.innerHTML='';
for(const b of bouts){const t=await api('/api/votes/tally?bout_id='+b.id+'&round_no='+b.round_no).catch(()=>null);
const el=document.createElement('div');el.className='card';
const bars=t?Object.entries(t.tally).map(([k,v])=>{const p=t.total?Math.round(v/t.total*100):0;
return '<div>'+k.toUpperCase()+' — '+v+' ('+p+'%)<div class="bar" style="width:'+p+'%"></div></div>';}).join(''):'';
el.innerHTML='<h3>'+b.title+' <span class="small">['+b.id+'] R'+b.round_no+' '+(b.voting_open?'🟢 OPEN':'🔴 CLOSED')+'</span></h3><p>'+b.fighter_a+' vs '+b.fighter_b+'</p>'+bars+'<div class="row"><button onclick="toggleBout(\\''+b.id+'\\','+!b.voting_open+')">'+(b.voting_open?'Close voting':'Open voting')+'</button><button class="ghost" onclick="nextRound(\\''+b.id+'\\','+(b.round_no+1)+')">→ Round '+(b.round_no+1)+'</button></div>';
box.appendChild(el);}
const add=document.createElement('div');add.className='card';
add.innerHTML='<h3>+ New bout</h3><div class="row"><input id="nb_id" placeholder="id (qf5)"><input id="nb_title" placeholder="title"><input id="nb_a" placeholder="fighter A"><input id="nb_b" placeholder="fighter B"><button onclick="addBout()">Create</button></div>';
box.appendChild(add);}
async function toggleBout(id,open){await api('/api/admin/bouts/'+id,{method:'PATCH',body:JSON.stringify({voting_open:open})});load();}
async function nextRound(id,r){await api('/api/admin/bouts/'+id,{method:'PATCH',body:JSON.stringify({round_no:r,voting_open:true})});load();}
async function addBout(){const g=i=>document.getElementById(i).value;
await api('/api/admin/bouts',{method:'POST',body:JSON.stringify({id:g('nb_id'),title:g('nb_title'),fighter_a:g('nb_a'),fighter_b:g('nb_b'),voting_open:false})});load();}
</script></body></html>`;

function json(data, status = 200, cors = true) {
  const h = { "content-type": "application/json" };
  if (cors) { h["access-control-allow-origin"] = ALLOW_ORIGIN; h["vary"] = "Origin"; }
  return new Response(JSON.stringify(data), { status, headers: h });
}
function err(msg, status) { return json({ error: msg }, status); }

async function sha256hex(s) {
  const d = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(s));
  return [...new Uint8Array(d)].map(b => b.toString(16).padStart(2, "0")).join("").slice(0, 32);
}

async function checkRate(db, ip) {
  const cutoff = Date.now() / 1000 - RATE_WINDOW_S;
  await db.prepare("DELETE FROM rate_hits WHERE ts < ?").bind(cutoff).run();
  const row = await db.prepare("SELECT COUNT(*) AS n FROM rate_hits WHERE ip = ?").bind(ip).first();
  if (row && row.n >= RATE_LIMIT) return false;
  await db.prepare("INSERT INTO rate_hits (ip, ts) VALUES (?, ?)").bind(ip, Date.now() / 1000).run();
  return true;
}

export default {
  async fetch(req, env) {
    const url = new URL(req.url);
    const db = env.DB;

    if (req.method === "OPTIONS") {
      return new Response(null, { headers: {
        "access-control-allow-origin": ALLOW_ORIGIN,
        "access-control-allow-methods": "GET,POST,PATCH,OPTIONS",
        "access-control-allow-headers": "Content-Type,X-Admin-Token",
        "access-control-max-age": "86400" } });
    }

    if (url.pathname === "/admin" || url.pathname === "/admin/") {
      return new Response(ADMIN_HTML, { headers: { "content-type": "text/html" } });
    }
    if (url.pathname === "/api/health") return json({ ok: true });

    if (url.pathname === "/api/bouts" && req.method === "GET") {
      const { results } = await db.prepare("SELECT * FROM bouts ORDER BY created_at").all();
      return json(results.map(r => ({ ...r, voting_open: !!r.voting_open })));
    }

    if (url.pathname === "/api/votes" && req.method === "POST") {
      let v; try { v = await req.json(); } catch { return err("bad json", 400); }
      const choice = String(v.choice || "").trim().toLowerCase();
      if (!CHOICES.has(choice)) return err("choice must be heavy|dodge|guard", 400);
      if (!v.bout_id || !v.round_no || !v.device_id || String(v.device_id).length < 8)
        return err("bout_id, round_no, device_id required", 400);
      const ip = req.headers.get("cf-connecting-ip") || "unknown";
      if (!(await checkRate(db, ip))) return err("rate limited: slow down", 429);
      const bout = await db.prepare("SELECT * FROM bouts WHERE id = ?").bind(v.bout_id).first();
      if (!bout) return err("bout not found", 404);
      if (!bout.voting_open) return err("voting is closed for this bout", 409);
      const dh = await sha256hex(String(v.device_id));
      const ipUa = await sha256hex(ip + "|" + (req.headers.get("user-agent") || ""));
      const now = Date.now() / 1000;
      await db.prepare(
        `INSERT INTO votes (bout_id, round_no, choice, device_hash, ip, ip_ua, created_at, updated_at)
         VALUES (?, ?, ?, ?, ?, ?, ?, ?)
         ON CONFLICT (bout_id, round_no, device_hash)
         DO UPDATE SET choice = excluded.choice, updated_at = excluded.updated_at`
      ).bind(v.bout_id, v.round_no, choice, dh, ip, ipUa, now, now).run();
      return json({ ok: true, bout_id: v.bout_id, round_no: v.round_no, choice });
    }

    if (url.pathname === "/api/votes/tally" && req.method === "GET") {
      const bout_id = url.searchParams.get("bout_id"), round_no = Number(url.searchParams.get("round_no") || 1);
      const { results } = await db.prepare(
        "SELECT choice, COUNT(*) AS n FROM votes WHERE bout_id = ? AND round_no = ? GROUP BY choice"
      ).bind(bout_id, round_no).all();
      const tally = { heavy: 0, dodge: 0, guard: 0 };
      for (const r of results) tally[r.choice] = r.n;
      return json({ bout_id, round_no, tally, total: tally.heavy + tally.dodge + tally.guard });
    }

    // ---- admin ----
    const token = req.headers.get("x-admin-token");
    const needAdmin = url.pathname.startsWith("/api/admin/");
    if (needAdmin && token !== env.ADMIN_TOKEN) return err("bad admin token", 403);

    if (url.pathname === "/api/admin/votes" && req.method === "GET") {
      const bout_id = url.searchParams.get("bout_id");
      const q = bout_id
        ? db.prepare("SELECT * FROM votes WHERE bout_id = ? ORDER BY updated_at DESC LIMIT 500").bind(bout_id)
        : db.prepare("SELECT * FROM votes ORDER BY updated_at DESC LIMIT 500");
      const { results } = await q.all();
      return json(results);
    }
    if (url.pathname === "/api/admin/bouts" && req.method === "POST") {
      let b; try { b = await req.json(); } catch { return err("bad json", 400); }
      if (!b.id || !b.title || !b.fighter_a || !b.fighter_b) return err("id,title,fighter_a,fighter_b required", 400);
      await db.prepare(
        "INSERT OR REPLACE INTO bouts (id,title,fighter_a,fighter_b,round_no,voting_open,created_at) VALUES (?,?,?,?,?,?,?)"
      ).bind(b.id, b.title, b.fighter_a, b.fighter_b, b.round_no || 1, b.voting_open ? 1 : 0, Date.now() / 1000).run();
      return json({ ok: true, id: b.id });
    }
    const m = url.pathname.match(/^\/api\/admin\/bouts\/([\w-]+)$/);
    if (m && req.method === "PATCH") {
      let p; try { p = await req.json(); } catch { return err("bad json", 400); }
      const sets = [], vals = [];
      if (p.title !== undefined) { sets.push("title = ?"); vals.push(p.title); }
      if (p.round_no !== undefined) { sets.push("round_no = ?"); vals.push(p.round_no); }
      if (p.voting_open !== undefined) { sets.push("voting_open = ?"); vals.push(p.voting_open ? 1 : 0); }
      if (!sets.length) return err("nothing to update", 400);
      vals.push(m[1]);
      const r = await db.prepare(`UPDATE bouts SET ${sets.join(",")} WHERE id = ?`).bind(...vals).run();
      if (!r.meta.changes) return err("bout not found", 404);
      return json({ ok: true, id: m[1] });
    }
    return err("not found", 404);
  }
};
