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
