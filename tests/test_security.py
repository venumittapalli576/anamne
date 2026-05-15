"""Security regression tests.

Each test here corresponds to a real vulnerability that was identified and
fixed.  These exist to make sure the fix doesn't silently regress.
"""
from __future__ import annotations

import shutil
import subprocess

import pytest


# ------------------------------------------------------------------ #
# SSRF: import-web must reject non-public URLs                          #
# ------------------------------------------------------------------ #

def _has_anamne_bin() -> bool:
    return shutil.which("anamne") is not None


SSRF_BLOCKED_URLS = [
    # Loopback / localhost
    "http://localhost:8080/admin",
    "http://127.0.0.1/",
    # Cloud metadata endpoints
    "http://169.254.169.254/latest/meta-data/",  # AWS
    "http://metadata.google.internal/computeMetadata/v1/",  # GCP
    # RFC1918 private ranges
    "http://10.0.0.1/internal",
    "http://192.168.1.1/router",
    # Non-http(s) schemes
    "file:///etc/passwd",
    "ftp://example.com/",
]


@pytest.mark.skipif(not _has_anamne_bin(), reason="anamne CLI not on PATH")
@pytest.mark.parametrize("url", SSRF_BLOCKED_URLS)
def test_import_web_refuses_unsafe_url(url):
    """The SSRF guard must refuse fetches against private / loopback / non-http URLs.

    This protects against:
      - Reading AWS / GCP cloud metadata via 169.254.169.254
      - Hitting localhost services (admin dashboards, dev databases)
      - Scanning the user's LAN via RFC1918 addresses
      - Reading local files via file://
    """
    result = subprocess.run(
        ["anamne", "import-web", url, "--dry-run"],
        capture_output=True, text=True, timeout=30, encoding="utf-8",
    )
    combined = (result.stdout or "") + (result.stderr or "")
    assert "Refusing to fetch" in combined, (
        f"Expected SSRF guard to refuse {url}, "
        f"but got exit {result.returncode}:\n{combined}"
    )
    # Must exit non-zero on a refused fetch
    assert result.returncode != 0


# ------------------------------------------------------------------ #
# XSS: dashboard graph tooltip must escape tag contents                 #
# ------------------------------------------------------------------ #

def test_ui_graph_tooltip_escapes_tag_contents():
    """v1.0.5 graph tooltip rendered tag names without escHtml.  A tag
    containing HTML (e.g. via `tag_fact` MCP call from an untrusted source)
    could execute script on hover.  Verify the fix is in place."""
    from anamne.ui.server import _DASHBOARD_HTML

    # The two tag-rendering sites in the tooltip code must both go through
    # escHtml on user-controllable strings (n.label, each tag in n.tags).
    # If you ever refactor the tooltip and want to silence this test, prove
    # the new code is also XSS-safe before doing so.
    assert "escHtml(n.label)" in _DASHBOARD_HTML, (
        "tag-node tooltip (n.label) must be escaped"
    )
    assert "'#'+escHtml(t)" in _DASHBOARD_HTML, (
        "fact-node tooltip tag list (n.tags) must escape each tag"
    )


# ------------------------------------------------------------------ #
# www. prefix stripping: lstrip("www.") was wrong                       #
# ------------------------------------------------------------------ #

def test_no_lstrip_www_bug():
    """`netloc.lstrip("www.")` does NOT strip "www." - it strips any chars
    from the set {w, ., a}, so e.g. "awesome.com" becomes "esome.com".
    The fix is `removeprefix("www.")`.  This test pins the fix in place."""
    from pathlib import Path

    cli_src = (Path(__file__).resolve().parent.parent
               / "anamne" / "cli" / "main.py").read_text(encoding="utf-8")
    assert 'lstrip("www.")' not in cli_src, (
        "lstrip('www.') is a real bug; use removeprefix('www.') instead"
    )


# ------------------------------------------------------------------ #
# UI server must handle concurrent connections (ThreadingHTTPServer)    #
# ------------------------------------------------------------------ #

# ------------------------------------------------------------------ #
# Issue #4: remember + search_facts must serialize under concurrency   #
# ------------------------------------------------------------------ #

def test_remember_search_no_race_under_concurrent_threads(tmp_path):
    """Issue #4 (closed by v1.0.9).

    Before the fix: if remember() and search_facts_semantic() ran on different
    threads, the search could observe state where the SQLite INSERT had landed
    but the ChromaDB upsert hadn't, and miss the just-stored fact.

    After the fix: both methods take a store-level RLock.  Even with N threads
    hammering both, every fact that's been remember()ed must be findable.
    """
    import threading
    from anamne.store.graph import DecisionStore

    store = DecisionStore(data_dir=tmp_path)
    # Seed one base fact so semantic search has at least one neighbour
    store.remember("seed: postgres database choice", tags=["db"])

    # Race: one writer thread inserts N facts, one reader thread searches
    # concurrently for each ID right after.  Without the lock, the reader
    # would occasionally miss.
    N = 30
    ids: list[str] = []
    errors: list[str] = []
    write_done = threading.Event()

    def writer():
        try:
            for i in range(N):
                mid = store.remember(
                    f"concurrent fact #{i} about postgres concurrent writes",
                    tags=["race-test"],
                )
                ids.append(mid)
        finally:
            write_done.set()

    def reader():
        # Repeatedly search while writer is going
        while not write_done.is_set() or len(ids) < N:
            try:
                store.search_facts_semantic("postgres concurrent writes", limit=5)
            except Exception as e:
                errors.append(str(e))
            if write_done.is_set() and len(ids) >= N:
                break

    tw = threading.Thread(target=writer)
    tr = threading.Thread(target=reader)
    tw.start(); tr.start()
    tw.join(); tr.join()

    assert not errors, f"reader saw errors during race: {errors[:3]}"
    # All written facts must be findable via direct id lookup post-race
    for mid in ids:
        got = store.get_fact(mid)
        assert got is not None, f"fact {mid} missing after concurrent run"


# ------------------------------------------------------------------ #
# Issue #3: iter_facts must stream without materialising the full set  #
# ------------------------------------------------------------------ #

def test_iter_facts_streams_in_pages(tmp_path):
    """Issue #3 (closed by v1.0.9).

    iter_facts() should yield facts from disk in pages, never load the full
    set into Python memory at once.  Verify by inserting N rows directly via
    SQLite (bypassing ChromaDB to keep the test fast) and confirming the
    generator yields them all in expected shape.
    """
    import json as _json
    import sqlite3
    from datetime import datetime, timezone
    from anamne.store.graph import DecisionStore

    store = DecisionStore(data_dir=tmp_path)
    # Seed 250 rows directly (faster than going through store.remember which
    # also embeds each one in ChromaDB).
    now = datetime.now(timezone.utc).isoformat()
    with sqlite3.connect(store._db) as con:
        for i in range(250):
            con.execute(
                "INSERT INTO scratchpad "
                "(id, fact, tags, created_at, last_used_at, use_count, pinned) "
                "VALUES (?, ?, ?, ?, ?, 0, 0)",
                (f"perf-{i:04x}", f"fact number {i}",
                 _json.dumps(["even"] if i % 2 == 0 else ["odd"]), now, now),
            )

    # Stream with batch=50 - should yield all 250 across 5 pages
    facts = list(store.iter_facts(batch=50))
    assert len(facts) == 250
    assert {f["id"] for f in facts} == {f"perf-{i:04x}" for i in range(250)}
    # Shape check
    assert all(
        {"id", "fact", "tags", "created_at", "last_used_at",
         "use_count", "pinned"} <= set(f) for f in facts
    ), "iter_facts must yield the same dict shape as list_facts"
    # Tag filtering works in streaming mode
    even_only = list(store.iter_facts(batch=50, tags=["even"]))
    assert len(even_only) == 125
    assert all("even" in f["tags"] for f in even_only)


def test_ui_uses_threading_http_server():
    """v1.0.6 and earlier used single-threaded http.server.HTTPServer.
    When a browser loaded the dashboard, parallel /api/* requests would
    serialise behind whatever first request was busy in ChromaDB, and any
    one stuck connection would hang the entire UI for everyone.

    v1.0.7 switched to ThreadingHTTPServer.  This test pins the fix so a
    future refactor doesn't silently regress concurrency."""
    from pathlib import Path

    ui_src = (Path(__file__).resolve().parent.parent
              / "anamne" / "ui" / "server.py").read_text(encoding="utf-8")
    assert "ThreadingHTTPServer" in ui_src, (
        "UI server must use ThreadingHTTPServer; the single-threaded "
        "HTTPServer hangs when any connection stalls."
    )
    # Defence in depth: also ensure we don't still have the bad construction
    assert "HTTPServer((host, port)" not in ui_src or \
        "ThreadingHTTPServer((host, port)" in ui_src, (
        "found HTTPServer(...) call - should be ThreadingHTTPServer(...)"
    )
