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
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
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
        elif path == "/api/graph":
            limit = int(qs.get("limit", [200])[0])
            facts = self.store.list_facts(limit=limit, tags=None)
            # Build bipartite graph: fact nodes + tag nodes (tags on >=2 facts)
            from collections import defaultdict as _dd
            tag_facts: dict = _dd(list)
            for f in facts:
                for t in (f.get("tags") or []):
                    tag_facts[t].append(f["id"])
            multi_tags = {t for t, fids in tag_facts.items() if len(fids) >= 2}
            nodes = []
            for f in facts:
                if any(t in multi_tags for t in (f.get("tags") or [])):
                    nodes.append({
                        "id": f["id"],
                        "type": "fact",
                        "label": f["fact"][:50] + ("..." if len(f["fact"]) > 50 else ""),
                        "full": f["fact"],
                        "tags": f.get("tags") or [],
                        "activation": round(self.store.activation_score(f["id"]), 4),
                    })
            for t in sorted(multi_tags):
                nodes.append({
                    "id": f"tag:{t}",
                    "type": "tag",
                    "label": t,
                    "full": f"#{t}  ({len(tag_facts[t])} facts)",
                    "tags": [],
                    "activation": 0,
                })
            fact_ids = {n["id"] for n in nodes if n["type"] == "fact"}
            edges = [
                {"source": fid, "target": f"tag:{t}"}
                for t in multi_tags
                for fid in tag_facts[t]
                if fid in fact_ids
            ]
            self._send_json({"nodes": nodes, "edges": edges})
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

    # ThreadingHTTPServer handles concurrent connections. Single-threaded
    # HTTPServer would hang the whole UI if any one connection got stuck
    # (e.g. browsers make 4-6 parallel /api/* requests when loading the page).
    server = ThreadingHTTPServer((host, port), _Handler)
    url = f"http://{host}:{port}"

    print(f"\n  ANAMNE UI  ->  {url}\n  Press Ctrl+C to stop.\n")

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
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
  :root {
    --bg: #08080d;
    --bg-2: #0c0c14;
    --surface: #13131c;
    --surface-2: #1a1a26;
    --surface-hover: #20202e;
    --border: #24243a;
    --border-soft: #1c1c2c;
    --text: #ecedf1;
    --text-strong: #ffffff;
    --muted: #7c7c8a;
    --muted-2: #5a5a68;

    /* Three layer accents - one per memory layer.
       Scratchpad = violet (calm, durable, "memory itself")
       Working    = mint   (fresh, active, transient)
       Episodic   = amber  (warm, historical, archival)
    */
    --scratchpad: #a78bfa;
    --scratchpad-glow: rgba(167, 139, 250, 0.18);
    --scratchpad-glow-strong: rgba(167, 139, 250, 0.35);
    --working: #34d399;
    --working-glow: rgba(52, 211, 153, 0.18);
    --working-glow-strong: rgba(52, 211, 153, 0.35);
    --episodic: #fbbf24;
    --episodic-glow: rgba(251, 191, 36, 0.18);
    --episodic-glow-strong: rgba(251, 191, 36, 0.35);

    /* Default --accent = scratchpad (violet). Switches per active tab.
       Everything that uses var(--accent) auto-recolors when you change tab. */
    --accent: var(--scratchpad);
    --accent-2: #8b5cf6;
    --accent-glow: var(--scratchpad-glow);
    --accent-glow-strong: var(--scratchpad-glow-strong);

    --green: var(--working);
    --green-soft: rgba(52, 211, 153, 0.14);
    --yellow: var(--episodic);
    --yellow-soft: rgba(251, 191, 36, 0.14);
    --red: #fb7185;
    --red-soft: rgba(251, 113, 133, 0.14);
    --purple: #c084fc;
    --purple-soft: rgba(192, 132, 252, 0.14);
    --orange: #fb923c;
    --orange-soft: rgba(251, 146, 60, 0.14);
    --shadow-glow: 0 0 0 1px var(--accent-glow), 0 8px 24px -8px var(--accent-glow);
  }

  /* Active-tab tinting: when JS sets body[data-layer="working"] etc,
     --accent shifts to that layer's colour. All accent uses auto-adapt. */
  body[data-layer="working"] {
    --accent: var(--working);
    --accent-glow: var(--working-glow);
    --accent-glow-strong: var(--working-glow-strong);
  }
  body[data-layer="episodic"] {
    --accent: var(--episodic);
    --accent-glow: var(--episodic-glow);
    --accent-glow-strong: var(--episodic-glow-strong);
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  html, body { height: 100%; }
  body {
    background: var(--bg);
    background-image:
      radial-gradient(ellipse 800px 600px at 20% -10%, rgba(167, 139, 250, 0.08), transparent 60%),
      radial-gradient(ellipse 600px 400px at 90% 100%, rgba(52, 211, 153, 0.04), transparent 60%);
    background-attachment: fixed;
    color: var(--text);
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    font-size: 14px;
    line-height: 1.55;
    -webkit-font-smoothing: antialiased;
    text-rendering: optimizeLegibility;
  }
  a { color: var(--accent); text-decoration: none; transition: color .15s; }
  a:hover { color: #c4b5fd; }

  /* ----- Header ----- */
  header {
    background: linear-gradient(180deg, var(--bg-2), var(--bg));
    border-bottom: 1px solid var(--border-soft);
    padding: 18px 32px;
    display: flex;
    align-items: center;
    gap: 20px;
    backdrop-filter: blur(8px);
    position: sticky;
    top: 0;
    z-index: 5;
  }
  header h1 {
    font-size: 17px;
    font-weight: 700;
    color: var(--text-strong);
    letter-spacing: -.01em;
    display: flex;
    align-items: center;
    gap: 8px;
  }
  header h1::before {
    content: '';
    display: inline-block;
    width: 10px; height: 10px;
    border-radius: 3px;
    background: linear-gradient(135deg, var(--accent), var(--green));
    box-shadow: 0 0 12px var(--accent-glow-strong);
  }
  header .stats { display: flex; gap: 10px; margin-left: auto; }
  .stat {
    text-align: center;
    background: var(--surface);
    border: 1px solid var(--border-soft);
    border-radius: 10px;
    padding: 9px 18px;
    min-width: 96px;
    transition: all .2s;
    position: relative;
    overflow: hidden;
  }
  .stat::after {
    content: '';
    position: absolute;
    inset: 0;
    border-radius: 10px;
    background: linear-gradient(180deg, transparent, var(--accent-glow));
    opacity: 0;
    transition: opacity .2s;
    pointer-events: none;
  }
  .stat:hover { border-color: var(--border); transform: translateY(-1px); }
  .stat:hover::after { opacity: 1; }

  /* Each header stat card is permanently colored by its memory layer.
     The user learns the three-layer color system at a glance, always. */
  .stat[data-layer="scratchpad"] .n { color: var(--scratchpad); }
  .stat[data-layer="scratchpad"]::after { background: linear-gradient(180deg, transparent, var(--scratchpad-glow)); }
  .stat[data-layer="scratchpad"]:hover { border-color: var(--scratchpad); box-shadow: 0 0 0 1px var(--scratchpad-glow); }
  .stat[data-layer="episodic"] .n { color: var(--episodic); }
  .stat[data-layer="episodic"]::after { background: linear-gradient(180deg, transparent, var(--episodic-glow)); }
  .stat[data-layer="episodic"]:hover { border-color: var(--episodic); box-shadow: 0 0 0 1px var(--episodic-glow); }
  .stat[data-layer="working"] .n { color: var(--working); }
  .stat[data-layer="working"]::after { background: linear-gradient(180deg, transparent, var(--working-glow)); }
  .stat[data-layer="working"]:hover { border-color: var(--working); box-shadow: 0 0 0 1px var(--working-glow); }
  .stat .n {
    font-size: 22px;
    font-weight: 700;
    color: var(--text-strong);
    letter-spacing: -.02em;
    font-feature-settings: "tnum";
  }
  .stat .l {
    font-size: 10px;
    color: var(--muted);
    text-transform: uppercase;
    letter-spacing: .08em;
    font-weight: 500;
    margin-top: 2px;
  }

  /* ----- Layout ----- */
  .main { display: grid; grid-template-columns: 232px 1fr; min-height: calc(100vh - 71px); }
  nav {
    background: var(--bg-2);
    border-right: 1px solid var(--border-soft);
    padding: 20px 12px;
    display: flex;
    flex-direction: column;
    gap: 2px;
  }
  nav button {
    display: flex; align-items: center; gap: 10px;
    width: 100%;
    padding: 9px 14px;
    background: none;
    border: none;
    color: var(--muted);
    font-family: inherit;
    font-size: 13px;
    font-weight: 500;
    text-align: left;
    cursor: pointer;
    border-radius: 8px;
    transition: all .15s;
    position: relative;
  }
  nav button:hover { background: var(--surface); color: var(--text); }
  nav button.active {
    background: var(--surface);
    color: var(--text-strong);
  }
  nav button.active::before {
    content: '';
    position: absolute;
    left: -12px;
    top: 50%;
    transform: translateY(-50%);
    width: 3px; height: 22px;
    background: var(--accent);
    border-radius: 0 3px 3px 0;
    box-shadow: 0 0 12px var(--accent-glow-strong);
  }
  .content { padding: 32px 40px; overflow: auto; max-width: 100%; }

  /* ----- Toolbar ----- */
  .toolbar {
    display: flex;
    align-items: center;
    gap: 10px;
    margin-bottom: 24px;
    flex-wrap: wrap;
  }
  .toolbar input, .toolbar select {
    background: var(--surface);
    border: 1px solid var(--border-soft);
    color: var(--text);
    padding: 9px 14px;
    border-radius: 8px;
    font-family: inherit;
    font-size: 13px;
    outline: none;
    transition: all .15s;
  }
  .toolbar input { width: 320px; }
  .toolbar input::placeholder { color: var(--muted-2); }
  .toolbar input:focus, .toolbar select:focus {
    border-color: var(--accent);
    background: var(--surface-2);
    box-shadow: 0 0 0 3px var(--accent-glow);
  }
  .toolbar label { color: var(--muted); font-size: 12px; display: inline-flex; align-items: center; gap: 6px; }

  /* ----- Tables ----- */
  table {
    width: 100%;
    border-collapse: collapse;
    background: var(--surface);
    border: 1px solid var(--border-soft);
    border-radius: 12px;
    overflow: hidden;
  }
  th {
    background: var(--bg-2);
    color: var(--muted);
    font-size: 10px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: .08em;
    padding: 12px 16px;
    text-align: left;
    border-bottom: 1px solid var(--border-soft);
    position: sticky;
    top: 0;
  }
  td {
    padding: 13px 16px;
    border-bottom: 1px solid var(--border-soft);
    vertical-align: top;
  }
  tr:last-child td { border-bottom: none; }
  tr { transition: background .12s; }
  tr:hover td { background: var(--surface-2); }
  .id {
    font-family: 'JetBrains Mono', 'SF Mono', Consolas, monospace;
    font-size: 11px;
    color: var(--muted);
    font-feature-settings: "tnum";
  }
  .fact-text { max-width: 560px; color: var(--text); }
  .tag {
    /* Per-tag color from the inline --tag-h variable set by JS (hash of tag name).
       Fallback to the active accent hue when --tag-h is missing. */
    --tag-h: 258;
    display: inline-block;
    background: hsla(var(--tag-h), 65%, 60%, 0.14);
    color: hsl(var(--tag-h), 80%, 75%);
    border: 1px solid hsla(var(--tag-h), 65%, 60%, 0.25);
    border-radius: 5px;
    padding: 2px 8px;
    font-size: 11px;
    font-weight: 500;
    margin: 2px 3px 2px 0;
    transition: all .12s;
  }
  .tag:hover {
    background: hsla(var(--tag-h), 65%, 60%, 0.22);
    border-color: hsl(var(--tag-h), 65%, 65%);
  }
  .act {
    font-family: 'JetBrains Mono', monospace;
    font-size: 12px;
    color: var(--green);
  }

  /* ----- Badges ----- */
  .badge {
    display: inline-block;
    border-radius: 5px;
    padding: 2px 8px;
    font-size: 10px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: .04em;
  }
  .badge-created { background: var(--green-soft); color: var(--green); }
  .badge-content_updated { background: var(--yellow-soft); color: var(--yellow); }
  .badge-tags_updated { background: var(--accent-glow); color: var(--accent); }
  .badge-forgotten { background: var(--red-soft); color: var(--red); }
  .badge-merged_into { background: var(--purple-soft); color: var(--purple); }

  /* ----- States ----- */
  .empty {
    text-align: center;
    color: var(--muted);
    padding: 64px 24px;
    font-size: 14px;
    background: var(--surface);
    border: 1px dashed var(--border);
    border-radius: 12px;
  }
  .spinner {
    color: var(--muted);
    font-size: 13px;
    padding: 48px;
    text-align: center;
  }
  .spinner::before {
    content: '';
    display: inline-block;
    width: 14px; height: 14px;
    border: 2px solid var(--border);
    border-top-color: var(--accent);
    border-radius: 50%;
    margin-right: 10px;
    vertical-align: middle;
    animation: spin .8s linear infinite;
  }
  @keyframes spin { to { transform: rotate(360deg); } }

  /* ----- Panels (working memory cards) ----- */
  .panel {
    background: var(--surface);
    border: 1px solid var(--border-soft);
    border-radius: 12px;
    padding: 18px 22px;
    margin-bottom: 14px;
    transition: border-color .15s;
  }
  .panel:hover { border-color: var(--border); }
  .panel h3 {
    font-size: 11px;
    color: var(--muted);
    text-transform: uppercase;
    letter-spacing: .08em;
    margin-bottom: 12px;
    font-weight: 600;
  }
  .wm-item { border-bottom: 1px solid var(--border-soft); padding: 10px 0; }
  .wm-item:last-child { border: none; }
  .wm-note { font-size: 14px; color: var(--text); }
  .wm-meta { font-size: 11px; color: var(--muted); margin-top: 4px; font-family: 'JetBrains Mono', monospace; }
  .hist-row td { font-size: 12px; }

  /* ----- Modal ----- */
  #overlay {
    display: none;
    position: fixed;
    inset: 0;
    background: rgba(8, 8, 13, 0.75);
    backdrop-filter: blur(6px);
    z-index: 10;
    align-items: center;
    justify-content: center;
  }
  #overlay.open { display: flex; }
  #modal {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 14px;
    padding: 28px;
    width: 680px;
    max-height: 80vh;
    overflow: auto;
    box-shadow: 0 24px 64px -12px rgba(0, 0, 0, 0.6);
  }
  #modal h2 {
    font-size: 15px;
    margin-bottom: 18px;
    color: var(--text-strong);
    font-weight: 600;
  }
  #modal .close {
    float: right;
    cursor: pointer;
    color: var(--muted);
    font-size: 20px;
    line-height: 1;
    transition: color .12s;
  }
  #modal .close:hover { color: var(--text); }

  /* ----- Repo tag ----- */
  .repo-tag {
    background: var(--orange-soft);
    color: var(--orange);
    border-radius: 5px;
    padding: 2px 8px;
    font-size: 11px;
    font-weight: 500;
  }

  /* ----- Fact Graph ----- */
  #graph-wrap {
    width: 100%;
    height: calc(100vh - 200px);
    min-height: 520px;
    background: var(--bg-2);
    background-image:
      radial-gradient(circle at 30% 30%, rgba(167, 139, 250, 0.05), transparent 50%),
      radial-gradient(circle at 70% 80%, rgba(52, 211, 153, 0.04), transparent 50%);
    border: 1px solid var(--border-soft);
    border-radius: 12px;
    overflow: hidden;
    position: relative;
  }
  #graph-svg { width: 100%; height: 100%; }
  #graph-tip {
    position: absolute;
    background: var(--surface-2);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 10px 14px;
    font-size: 12px;
    max-width: 320px;
    pointer-events: none;
    display: none;
    z-index: 5;
    line-height: 1.5;
    box-shadow: 0 8px 24px -8px rgba(0, 0, 0, 0.5);
  }
  .graph-legend {
    display: flex;
    gap: 22px;
    align-items: center;
    margin-bottom: 14px;
    font-size: 12px;
    color: var(--muted);
  }
  .graph-legend span { display: inline-flex; align-items: center; gap: 7px; }
  .legend-dot {
    width: 10px; height: 10px;
    border-radius: 50%;
    display: inline-block;
    box-shadow: 0 0 8px currentColor;
  }
  .legend-sq {
    width: 10px; height: 10px;
    border-radius: 3px;
    display: inline-block;
  }

  /* ----- Scrollbar ----- */
  ::-webkit-scrollbar { width: 10px; height: 10px; }
  ::-webkit-scrollbar-track { background: transparent; }
  ::-webkit-scrollbar-thumb { background: var(--border); border-radius: 5px; }
  ::-webkit-scrollbar-thumb:hover { background: var(--muted-2); }
</style>
</head>
<body>
<header>
  <h1>ANAMNE</h1>
  <span style="color:var(--muted);font-size:12px;font-weight:500;letter-spacing:.02em">brain-inspired memory dashboard</span>
  <div class="stats">
    <div class="stat" data-layer="scratchpad"><div class="n" id="s-facts">—</div><div class="l">Scratchpad</div></div>
    <div class="stat" data-layer="episodic"><div class="n" id="s-decisions">—</div><div class="l">Episodic</div></div>
    <div class="stat" data-layer="working"><div class="n" id="s-working">—</div><div class="l">Working</div></div>
  </div>
</header>
<div class="main">
  <nav>
    <button class="active" onclick="showTab('facts', this)">📋  Scratchpad Facts</button>
    <button onclick="showTab('search', this)">🔍  Search</button>
    <button onclick="showTab('working', this)">⚡  Working Memory</button>
    <button onclick="showTab('repos', this)">📦  Indexed Repos</button>
    <button onclick="showTab('graph', this)">🕸️  Fact Graph</button>
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

// Which memory layer does each tab belong to?  Drives the per-layer
// accent colour - --accent shifts on the body when the user switches tabs.
const _tabLayer = {
  facts: 'scratchpad',
  search: 'scratchpad',  // search is over scratchpad
  working: 'working',
  repos: 'episodic',     // indexed repos drive the episodic store
  graph: 'scratchpad',   // graph is over scratchpad facts
};

function showTab(tab, btn) {
  currentTab = tab;
  document.body.dataset.layer = _tabLayer[tab] || 'scratchpad';
  document.querySelectorAll('nav button').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  if (tab === 'facts') loadFacts();
  else if (tab === 'search') loadSearch();
  else if (tab === 'working') loadWorking();
  else if (tab === 'repos') loadRepos();
  else if (tab === 'graph') loadGraph();
}

function fmtDate(iso) {
  if (!iso) return '—';
  return iso.slice(0, 16).replace('T', ' ');
}

// Hash a tag name into a stable HSL hue (0-359).  Each tag therefore renders
// with a consistent unique colour across the whole dashboard.
function tagHue(s) {
  let h = 0;
  for (let i = 0; i < s.length; i++) {
    h = ((h << 5) - h + s.charCodeAt(i)) | 0;
  }
  return Math.abs(h) % 360;
}

function tagHtml(tags) {
  if (!tags || !tags.length) return '<span style="color:var(--muted)">—</span>';
  return tags.map(t => `<span class="tag" style="--tag-h:${tagHue(t)}">${escHtml(t)}</span>`).join('');
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
      <td class="fact-text">${f.pinned ? '<span title="Pinned - protected from auto-consolidation" style="color:var(--green);margin-right:4px">&#128204;</span>' : ''}${escHtml(f.fact)}</td>
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

// ---- Fact Graph ----
let _graphRAF = null;

async function loadGraph() {
  const c = document.getElementById('content');
  c.innerHTML = `
    <div class="graph-legend">
      <span><span class="legend-dot" style="background:var(--accent)"></span> Scratchpad fact</span>
      <span><span class="legend-sq" style="background:var(--orange)"></span> Tag (shared by 2+ facts)</span>
      <span style="margin-left:auto;color:var(--muted)">Hover for details &nbsp;·&nbsp; Click fact for history &nbsp;·&nbsp; Drag to reposition</span>
    </div>
    <div id="graph-wrap">
      <div id="graph-tip"></div>
      <svg id="graph-svg"></svg>
    </div>`;

  const data = await api('/api/graph');
  if (!data.nodes || data.nodes.length === 0) {
    document.getElementById('graph-wrap').innerHTML =
      '<div class="empty" style="padding:64px">No tagged facts yet — add facts with tags to see the graph.</div>';
    return;
  }

  const wrap = document.getElementById('graph-wrap');
  const svg = document.getElementById('graph-svg');
  const tip = document.getElementById('graph-tip');
  let W = wrap.clientWidth || 900, H = wrap.clientHeight || 560;

  // Init node positions randomly around center
  const ns = data.nodes.map(n => ({
    ...n,
    x: W/2 + (Math.random()-.5)*300,
    y: H/2 + (Math.random()-.5)*300,
    vx: 0, vy: 0,
    r: n.type === 'fact' ? 7 : 10,
  }));
  const idIdx = Object.fromEntries(ns.map((n,i) => [n.id, i]));
  const es = data.edges
    .map(e => ({ s: idIdx[e.source], t: idIdx[e.target] }))
    .filter(e => e.s !== undefined && e.t !== undefined);

  // Force constants
  const K_REP = 1200, K_SPRING = 0.06, REST = 90, DAMP = 0.82, GRAV = 0.0018;

  function tick() {
    // Repulsion between all pairs
    for (let i = 0; i < ns.length; i++) {
      for (let j = i+1; j < ns.length; j++) {
        const dx = ns[j].x - ns[i].x, dy = ns[j].y - ns[i].y;
        const d2 = dx*dx + dy*dy + 1;
        const f = K_REP / d2;
        const d = Math.sqrt(d2);
        ns[i].vx -= f*dx/d; ns[i].vy -= f*dy/d;
        ns[j].vx += f*dx/d; ns[j].vy += f*dy/d;
      }
    }
    // Spring along edges
    for (const e of es) {
      const a = ns[e.s], b = ns[e.t];
      const dx = b.x - a.x, dy = b.y - a.y;
      const d = Math.sqrt(dx*dx + dy*dy) || 1;
      const f = (d - REST) * K_SPRING;
      const fx = f*dx/d, fy = f*dy/d;
      a.vx += fx; a.vy += fy;
      b.vx -= fx; b.vy -= fy;
    }
    // Gravity toward center + integrate + clamp
    for (const n of ns) {
      n.vx += (W/2 - n.x)*GRAV; n.vy += (H/2 - n.y)*GRAV;
      n.vx *= DAMP; n.vy *= DAMP;
      n.x += n.vx; n.y += n.vy;
      n.x = Math.max(n.r+2, Math.min(W-n.r-2, n.x));
      n.y = Math.max(n.r+2, Math.min(H-n.r-2, n.y));
    }
  }

  // SVG namespaced element helper
  const SVG_NS = 'http://www.w3.org/2000/svg';
  function el(tag, attrs) {
    const e = document.createElementNS(SVG_NS, tag);
    for (const [k,v] of Object.entries(attrs)) e.setAttribute(k, v);
    return e;
  }

  // Build SVG elements once
  const edgeEls = es.map(() => el('line', {stroke:'#30363d', 'stroke-width':'1.2'}));
  const nodeEls = ns.map(n => {
    if (n.type === 'fact') {
      return el('circle', {r: n.r, fill:'var(--accent)', opacity:'0.85', cursor:'pointer', style:'transition:opacity .1s'});
    } else {
      const s = n.r*2; // square side
      return el('rect', {width:s, height:s, rx:'3', fill:'var(--orange)', opacity:'0.85', cursor:'pointer'});
    }
  });
  const labelEls = ns.map(n => {
    const t = el('text', {
      'font-size': n.type === 'tag' ? '11' : '10',
      fill: n.type === 'tag' ? 'var(--orange)' : 'var(--muted)',
      'pointer-events': 'none',
      'text-anchor': 'middle',
    });
    t.textContent = n.type === 'tag' ? '#'+n.label : '';
    return t;
  });

  svg.innerHTML = '';
  const gEdge = el('g', {}); edgeEls.forEach(e => gEdge.appendChild(e)); svg.appendChild(gEdge);
  const gNode = el('g', {}); nodeEls.forEach(e => gNode.appendChild(e)); svg.appendChild(gNode);
  const gLabel = el('g', {}); labelEls.forEach(e => gLabel.appendChild(e)); svg.appendChild(gLabel);

  // Tooltip + hover
  nodeEls.forEach((ne, i) => {
    ne.addEventListener('mouseenter', (ev) => {
      ne.setAttribute('opacity','1');
      const n = ns[i];
      tip.innerHTML = n.type === 'tag'
        ? `<b style="color:var(--orange)">#${escHtml(n.label)}</b><br>${escHtml(n.full)}`
        : `<span style="color:var(--accent);font-size:11px">${n.id}</span><br>${escHtml(n.full)}<br>` +
          (n.tags.length ? `<span style="color:var(--muted)">${n.tags.map(t=>'#'+escHtml(t)).join(' ')}</span>` : '');
      tip.style.display = 'block';
    });
    ne.addEventListener('mousemove', (ev) => {
      const bx = wrap.getBoundingClientRect();
      let lx = ev.clientX - bx.left + 14, ly = ev.clientY - bx.top + 14;
      if (lx + 310 > W) lx = ev.clientX - bx.left - 320;
      tip.style.left = lx+'px'; tip.style.top = ly+'px';
    });
    ne.addEventListener('mouseleave', () => { ne.setAttribute('opacity','0.85'); tip.style.display='none'; });

    // Drag + click (click opens history for fact nodes)
    let dragging = false, movedPx = 0;
    ne.addEventListener('mousedown', (ev) => {
      dragging = true; movedPx = 0; ev.preventDefault();
    });
    document.addEventListener('mousemove', (ev) => {
      if (!dragging) return;
      movedPx++;
      const bx = wrap.getBoundingClientRect();
      ns[i].x = ev.clientX - bx.left; ns[i].y = ev.clientY - bx.top;
      ns[i].vx = 0; ns[i].vy = 0;
    });
    document.addEventListener('mouseup', (ev) => {
      if (dragging && movedPx < 4 && ns[i].type === 'fact') {
        // Treat as click: open history modal
        showHistory(ns[i].id);
      }
      dragging = false;
    });
  });

  function render() {
    edgeEls.forEach((le, i) => {
      const a = ns[es[i].s], b = ns[es[i].t];
      le.setAttribute('x1',a.x); le.setAttribute('y1',a.y);
      le.setAttribute('x2',b.x); le.setAttribute('y2',b.y);
    });
    nodeEls.forEach((ne, i) => {
      const n = ns[i];
      if (n.type === 'fact') {
        ne.setAttribute('cx', n.x); ne.setAttribute('cy', n.y);
      } else {
        const s = n.r*2;
        ne.setAttribute('x', n.x-n.r); ne.setAttribute('y', n.y-n.r);
      }
    });
    labelEls.forEach((le, i) => {
      const n = ns[i];
      le.setAttribute('x', n.x);
      le.setAttribute('y', n.y + n.r + 11);
    });
  }

  if (_graphRAF) cancelAnimationFrame(_graphRAF);
  let frame = 0;
  function loop() {
    tick(); render();
    frame++;
    if (frame < 400) _graphRAF = requestAnimationFrame(loop);
    else { tick(); render(); } // settle
  }
  loop();

  // Re-layout on resize
  window.addEventListener('resize', () => {
    W = wrap.clientWidth || 900; H = wrap.clientHeight || 560;
  }, {once: true});
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
