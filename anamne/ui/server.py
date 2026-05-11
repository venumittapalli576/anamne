"""
ANAMNE local Web UI — read-only browser dashboard for all memory layers.

Starts a tiny HTTP server on localhost (default :8765).
No external dependencies beyond the stdlib — uses Python's built-in
http.server + JSON API endpoints.  The frontend is a single inline HTML
page with vanilla JS; no npm, no bundler.
"""

from __future__ import annotations

import json
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse


# ------------------------------------------------------------------ #
# HTTP handler                                                          #
# ------------------------------------------------------------------ #

class _Handler(BaseHTTPRequestHandler):
    """Handles GET requests: / returns the dashboard HTML, /api/* return JSON."""

    store: Any = None  # injected at startup

    def log_message(self, fmt, *args):  # silence the default access log
        pass

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"
        qs = parse_qs(parsed.query)

        if path == "/":
            self._send_html(_DASHBOARD_HTML)
        elif path == "/api/facts":
            limit = int(qs.get("limit", [100])[0])
            tag = qs.get("tag", [None])[0]
            tags = [tag] if tag else None
            facts = self.store.list_facts(limit=limit, tags=tags)
            # Enrich with activation score
            for f in facts:
                f["activation"] = round(self.store.activation_score(f["id"]), 4)
            self._send_json(facts)
        elif path == "/api/working":
            self._send_json(self.store.working_active())
        elif path == "/api/stats":
            self._send_json({
                "facts": self.store.fact_count(),
                "decisions": self.store.count(),
                "working": len(self.store.working_active()),
                "repos": self.store.all_repos(),
            })
        elif path.startswith("/api/history/"):
            fact_id = path.split("/")[-1]
            self._send_json(self.store.get_fact_history(fact_id))
        elif path == "/api/search":
            q = qs.get("q", [""])[0]
            limit = int(qs.get("limit", [20])[0])
            results = self.store.search_facts_ranked(q, limit=limit) if q else []
            for f in results:
                f["activation"] = round(self.store.activation_score(f["id"]), 4)
            self._send_json(results)
        else:
            self.send_response(404)
            self.end_headers()

    def _send_json(self, data):
        body = json.dumps(data, default=str).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _send_html(self, html: str):
        body = html.encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


# ------------------------------------------------------------------ #
# Entry point                                                           #
# ------------------------------------------------------------------ #

def run_ui(host: str = "127.0.0.1", port: int = 8765, open_browser: bool = True) -> None:
    """Start the local Web UI server.  Blocks until Ctrl+C."""
    from anamne.store.graph import DecisionStore

    store = DecisionStore()

    # Inject store into handler class (simple approach for single-threaded server)
    _Handler.store = store

    server = HTTPServer((host, port), _Handler)
    url = f"http://{host}:{port}"

    print(f"\n  ANAMNE UI  →  {url}\n  Press Ctrl+C to stop.\n")

    if open_browser:
        # Open after a short delay so the server is ready
        threading.Timer(0.5, webbrowser.open, args=[url]).start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


# ------------------------------------------------------------------ #
# Self-contained dashboard HTML (inline — zero external deps)          #
# ------------------------------------------------------------------ #

_DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>ANAMNE — Memory Dashboard</title>
<style>
  :root {
    --bg: #0d1117; --surface: #161b22; --border: #30363d;
    --text: #e6edf3; --muted: #8b949e; --accent: #58a6ff;
    --green: #3fb950; --yellow: #d29922; --red: #f85149;
    --purple: #bc8cff; --orange: #ffa657;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { background: var(--bg); color: var(--text); font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; font-size: 14px; line-height: 1.5; }
  a { color: var(--accent); text-decoration: none; }
  header { background: var(--surface); border-bottom: 1px solid var(--border); padding: 12px 24px; display: flex; align-items: center; gap: 16px; }
  header h1 { font-size: 18px; font-weight: 700; color: var(--accent); letter-spacing: 1px; }
  header .stats { display: flex; gap: 20px; margin-left: auto; }
  .stat { text-align: center; }
  .stat .n { font-size: 22px; font-weight: 700; color: var(--text); }
  .stat .l { font-size: 11px; color: var(--muted); text-transform: uppercase; }
  .main { display: grid; grid-template-columns: 220px 1fr; min-height: calc(100vh - 57px); }
  nav { background: var(--surface); border-right: 1px solid var(--border); padding: 16px 0; }
  nav button { display: block; width: 100%; padding: 9px 20px; background: none; border: none; color: var(--muted); font-size: 13px; text-align: left; cursor: pointer; transition: all .15s; }
  nav button:hover, nav button.active { background: rgba(88,166,255,.08); color: var(--accent); }
  .content { padding: 24px; overflow: auto; }
  .toolbar { display: flex; align-items: center; gap: 10px; margin-bottom: 16px; flex-wrap: wrap; }
  .toolbar input { background: var(--surface); border: 1px solid var(--border); color: var(--text); padding: 7px 12px; border-radius: 6px; font-size: 13px; width: 280px; outline: none; }
  .toolbar input:focus { border-color: var(--accent); }
  .toolbar select { background: var(--surface); border: 1px solid var(--border); color: var(--text); padding: 7px 10px; border-radius: 6px; font-size: 13px; outline: none; }
  .toolbar label { color: var(--muted); font-size: 12px; }
  table { width: 100%; border-collapse: collapse; }
  th { background: var(--surface); color: var(--muted); font-size: 11px; text-transform: uppercase; letter-spacing: .5px; padding: 8px 12px; text-align: left; border-bottom: 1px solid var(--border); position: sticky; top: 0; }
  td { padding: 10px 12px; border-bottom: 1px solid var(--border); vertical-align: top; }
  tr:hover td { background: rgba(255,255,255,.02); }
  .id { font-family: monospace; font-size: 12px; color: var(--muted); }
  .fact-text { max-width: 520px; }
  .tag { display: inline-block; background: rgba(88,166,255,.15); color: var(--accent); border-radius: 4px; padding: 1px 7px; font-size: 11px; margin: 1px 2px; }
  .act { font-family: monospace; font-size: 12px; }
  .badge { display: inline-block; border-radius: 4px; padding: 1px 7px; font-size: 11px; font-weight: 600; }
  .badge-created { background: rgba(63,185,80,.15); color: var(--green); }
  .badge-content_updated { background: rgba(210,153,34,.15); color: var(--yellow); }
  .badge-tags_updated { background: rgba(88,166,255,.15); color: var(--accent); }
  .badge-forgotten { background: rgba(248,81,73,.15); color: var(--red); }
  .badge-merged_into { background: rgba(188,140,255,.15); color: var(--purple); }
  .empty { text-align: center; color: var(--muted); padding: 48px; font-size: 15px; }
  .panel { background: var(--surface); border: 1px solid var(--border); border-radius: 8px; padding: 16px 20px; margin-bottom: 16px; }
  .panel h3 { font-size: 13px; color: var(--muted); text-transform: uppercase; letter-spacing: .5px; margin-bottom: 10px; }
  .wm-item { border-bottom: 1px solid var(--border); padding: 8px 0; }
  .wm-item:last-child { border: none; }
  .wm-note { font-size: 14px; }
  .wm-meta { font-size: 11px; color: var(--muted); margin-top: 3px; }
  .hist-row td { font-size: 12px; }
  #overlay { display: none; position: fixed; inset: 0; background: rgba(0,0,0,.6); z-index: 10; align-items: center; justify-content: center; }
  #overlay.open { display: flex; }
  #modal { background: var(--surface); border: 1px solid var(--border); border-radius: 10px; padding: 24px; width: 660px; max-height: 80vh; overflow: auto; }
  #modal h2 { font-size: 15px; margin-bottom: 14px; color: var(--accent); }
  #modal .close { float: right; cursor: pointer; color: var(--muted); font-size: 18px; }
  .spinner { color: var(--muted); font-size: 13px; padding: 32px; text-align: center; }
  .repo-tag { background: rgba(255,166,87,.12); color: var(--orange); border-radius: 4px; padding: 1px 7px; font-size: 11px; }
</style>
</head>
<body>
<header>
  <h1>⚡ ANAMNE</h1>
  <span style="color:var(--muted);font-size:12px">Brain-inspired memory dashboard</span>
  <div class="stats">
    <div class="stat"><div class="n" id="s-facts">—</div><div class="l">Scratchpad</div></div>
    <div class="stat"><div class="n" id="s-decisions">—</div><div class="l">Episodic</div></div>
    <div class="stat"><div class="n" id="s-working">—</div><div class="l">Working</div></div>
  </div>
</header>
<div class="main">
  <nav>
    <button class="active" onclick="showTab('facts', this)">📋  Scratchpad Facts</button>
    <button onclick="showTab('search', this)">🔍  Search</button>
    <button onclick="showTab('working', this)">⚡  Working Memory</button>
    <button onclick="showTab('repos', this)">📦  Indexed Repos</button>
  </nav>
  <div class="content" id="content">
    <div class="spinner">Loading…</div>
  </div>
</div>
<div id="overlay" onclick="closeModal(event)">
  <div id="modal"></div>
</div>
<script>
const API = '';
let currentTab = 'facts';

async function api(path) {
  const r = await fetch(API + path);
  return r.json();
}

function showTab(tab, btn) {
  currentTab = tab;
  document.querySelectorAll('nav button').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  if (tab === 'facts') loadFacts();
  else if (tab === 'search') loadSearch();
  else if (tab === 'working') loadWorking();
  else if (tab === 'repos') loadRepos();
}

function fmtDate(iso) {
  if (!iso) return '—';
  return iso.slice(0, 16).replace('T', ' ');
}

function tagHtml(tags) {
  if (!tags || !tags.length) return '<span style="color:var(--muted)">—</span>';
  return tags.map(t => `<span class="tag">${t}</span>`).join('');
}

// ---- Scratchpad Facts ----
let allFacts = [];

async function loadFacts() {
  document.getElementById('content').innerHTML = `
    <div class="toolbar">
      <input id="ft-filter" placeholder="Filter facts…" oninput="filterFacts()" />
      <label>Tag: <select id="ft-tag" onchange="filterFacts()"><option value="">All</option></select></label>
      <span style="color:var(--muted);font-size:12px;margin-left:auto" id="ft-count"></span>
    </div>
    <table>
      <thead><tr>
        <th>ID</th><th>Fact</th><th>Tags</th>
        <th>Created</th><th>ACT-R</th><th></th>
      </tr></thead>
      <tbody id="facts-body"><tr><td colspan="6" class="spinner">Loading…</td></tr></tbody>
    </table>`;

  allFacts = await api('/api/facts?limit=500');

  // Populate tag dropdown
  const allTags = [...new Set(allFacts.flatMap(f => f.tags || []))].sort();
  const sel = document.getElementById('ft-tag');
  allTags.forEach(t => { const o = document.createElement('option'); o.value = t; o.textContent = t; sel.appendChild(o); });

  filterFacts();
}

function filterFacts() {
  const q = (document.getElementById('ft-filter')?.value || '').toLowerCase();
  const tag = document.getElementById('ft-tag')?.value || '';
  let rows = allFacts;
  if (q) rows = rows.filter(f => f.fact.toLowerCase().includes(q) || f.id.includes(q));
  if (tag) rows = rows.filter(f => (f.tags || []).includes(tag));

  document.getElementById('ft-count').textContent = `${rows.length} fact${rows.length !== 1 ? 's' : ''}`;
  const tbody = document.getElementById('facts-body');
  if (!tbody) return;
  if (!rows.length) { tbody.innerHTML = '<tr><td colspan="6" class="empty">No facts found.</td></tr>'; return; }

  tbody.innerHTML = rows.map(f => `
    <tr>
      <td class="id">${f.id}</td>
      <td class="fact-text">${escHtml(f.fact)}</td>
      <td>${tagHtml(f.tags)}</td>
      <td style="color:var(--muted);font-size:12px">${fmtDate(f.created_at)}</td>
      <td class="act">${f.activation > 0 ? f.activation.toFixed(3) : '<span style="color:var(--muted)">—</span>'}</td>
      <td><a href="#" onclick="showHistory('${f.id}');return false" style="font-size:12px">history</a></td>
    </tr>`).join('');
}

// ---- Search ----
function loadSearch() {
  document.getElementById('content').innerHTML = `
    <div class="toolbar">
      <input id="sq" placeholder="Search scratchpad (hybrid: substring + semantic)…"
             style="width:400px" onkeydown="if(event.key==='Enter')doSearch()" />
      <button onclick="doSearch()" style="background:var(--accent);color:#000;border:none;padding:7px 14px;border-radius:6px;cursor:pointer;font-size:13px">Search</button>
    </div>
    <table>
      <thead><tr><th>ID</th><th>Fact</th><th>Tags</th><th>ACT-R</th></tr></thead>
      <tbody id="search-body"><tr><td colspan="4" class="empty">Type a query and press Enter.</td></tr></tbody>
    </table>`;
}

async function doSearch() {
  const q = document.getElementById('sq').value.trim();
  if (!q) return;
  document.getElementById('search-body').innerHTML = '<tr><td colspan="4" class="spinner">Searching…</td></tr>';
  const results = await api(`/api/search?q=${encodeURIComponent(q)}`);
  const tbody = document.getElementById('search-body');
  if (!results.length) { tbody.innerHTML = '<tr><td colspan="4" class="empty">No results.</td></tr>'; return; }
  tbody.innerHTML = results.map(f => `
    <tr>
      <td class="id">${f.id}</td>
      <td class="fact-text">${escHtml(f.fact)}</td>
      <td>${tagHtml(f.tags)}</td>
      <td class="act">${f.activation > 0 ? f.activation.toFixed(3) : '—'}</td>
    </tr>`).join('');
}

// ---- Working Memory ----
async function loadWorking() {
  const items = await api('/api/working');
  const c = document.getElementById('content');
  if (!items.length) { c.innerHTML = '<div class="empty">Working memory is empty.</div>'; return; }
  c.innerHTML = `<div class="panel"><h3>Active working memory (${items.length})</h3>` +
    items.map(w => `
      <div class="wm-item">
        <div class="wm-note">${escHtml(w.note)}</div>
        <div class="wm-meta">id: ${w.id} &nbsp;·&nbsp; created: ${fmtDate(w.created_at)} &nbsp;·&nbsp; expires: ${fmtDate(w.expires_at)}</div>
      </div>`).join('') + '</div>';
}

// ---- Repos ----
async function loadRepos() {
  const stats = await api('/api/stats');
  const repos = stats.repos || [];
  const c = document.getElementById('content');
  c.innerHTML = `<div class="panel"><h3>Indexed repositories (${repos.length})</h3>` +
    (repos.length
      ? repos.map(r => `<div style="padding:6px 0;border-bottom:1px solid var(--border)"><span class="repo-tag">📦</span> ${escHtml(r)}</div>`).join('')
      : '<div class="empty" style="padding:16px">No repositories indexed yet. Run: <code>anamne index &lt;repo&gt;</code></div>'
    ) + '</div>';
}

// ---- History modal ----
async function showHistory(factId) {
  const overlay = document.getElementById('overlay');
  const modal = document.getElementById('modal');
  modal.innerHTML = `<span class="close" onclick="closeModal()">✕</span><h2>History — ${factId}</h2><div class="spinner">Loading…</div>`;
  overlay.classList.add('open');

  const hist = await api(`/api/history/${factId}`);
  if (!hist.length) {
    modal.innerHTML = `<span class="close" onclick="closeModal()">✕</span><h2>History — ${factId}</h2><p style="color:var(--muted);padding:16px">No history recorded yet.</p>`;
    return;
  }
  const rows = hist.map(h => `
    <tr class="hist-row">
      <td style="color:var(--muted);white-space:nowrap">${fmtDate(h.changed_at)}</td>
      <td><span class="badge badge-${h.change_type}">${h.change_type}</span></td>
      <td style="max-width:320px">${escHtml(h.content)}</td>
      <td>${tagHtml(h.tags)}</td>
      <td class="id">${h.merged_into || ''}</td>
    </tr>`).join('');
  modal.innerHTML = `
    <span class="close" onclick="closeModal()">✕</span>
    <h2>History — ${factId}</h2>
    <table>
      <thead><tr><th>When</th><th>Change</th><th>Content</th><th>Tags</th><th>Merged→</th></tr></thead>
      <tbody>${rows}</tbody>
    </table>`;
}

function closeModal(e) {
  if (e && e.target !== document.getElementById('overlay')) return;
  document.getElementById('overlay').classList.remove('open');
}

function escHtml(s) {
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

// ---- Init ----
async function init() {
  const stats = await api('/api/stats');
  document.getElementById('s-facts').textContent = stats.facts;
  document.getElementById('s-decisions').textContent = stats.decisions;
  document.getElementById('s-working').textContent = stats.working;
  loadFacts();
}

init();
</script>
</body>
</html>
"""
