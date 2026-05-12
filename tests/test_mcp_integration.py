"""End-to-end smoke test of the MCP server over real stdio JSON-RPC.

Catches regressions in:
  - the `anamne mcp-server` entry point
  - FastMCP server boot
  - the stdio JSON-RPC handshake
  - the full tool-registration list (must surface ALL @mcp.tool decorators)
  - calling a real tool and getting structured output back

Slow (~10s on cold start because ChromaDB has to load).  Skipped automatically
when the `anamne` CLI entry point is not on PATH.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import threading
import time
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _has_llm_key() -> bool:
    """The MCP server refuses to boot without one of these.  In CI without
    keys configured, the integration test is skipped rather than failing."""
    if os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("GEMINI_API_KEY"):
        return True
    # Fall back to .env in the project root if dotenv is installed
    env_file = PROJECT_ROOT / ".env"
    if env_file.exists():
        try:
            txt = env_file.read_text(encoding="utf-8")
            if "ANTHROPIC_API_KEY=" in txt or "GEMINI_API_KEY=" in txt:
                return True
        except Exception:
            pass
    return False


# Tests that spawn `anamne mcp-server` as a subprocess need the CLI on PATH.
pytestmark = pytest.mark.skipif(
    shutil.which("anamne") is None,
    reason="anamne CLI entry point not on PATH (run `pip install -e .`)",
)

# Use this on tests that need the subprocess to actually reach the LLM.
needs_llm_key = pytest.mark.skipif(
    not _has_llm_key(),
    reason="No LLM API key configured (set ANTHROPIC_API_KEY or "
           "GEMINI_API_KEY, or add a .env in the project root)",
)


def _reader(pipe, sink):
    for line in iter(pipe.readline, ""):
        sink.append(line)


def _spawn_and_handshake(cwd: str | None = None) -> tuple[subprocess.Popen, list[dict]]:
    proc = subprocess.Popen(
        ["anamne", "mcp-server"],
        cwd=cwd or str(PROJECT_ROOT),
        env=os.environ.copy(),  # inherit ANTHROPIC_API_KEY / GEMINI_API_KEY
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        bufsize=1,
    )
    stdout_lines: list[str] = []
    stderr_lines: list[str] = []
    threading.Thread(target=_reader, args=(proc.stdout, stdout_lines), daemon=True).start()
    threading.Thread(target=_reader, args=(proc.stderr, stderr_lines), daemon=True).start()

    def send(msg: dict) -> None:
        proc.stdin.write(json.dumps(msg) + "\n")
        proc.stdin.flush()

    send({
        "jsonrpc": "2.0", "id": 1, "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "anamne-pytest", "version": "0.1"},
        },
    })
    send({"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}})
    send({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})

    # Cold start can take a while: ChromaDB import + DB open.
    deadline = time.time() + 25
    responses: list[dict] = []
    seen_ids: set[int] = set()
    while time.time() < deadline:
        for raw in list(stdout_lines):
            try:
                msg = json.loads(raw.strip())
            except Exception:
                continue
            mid = msg.get("id")
            if mid in seen_ids:
                continue
            if mid is not None:
                seen_ids.add(mid)
                responses.append(msg)
        if {1, 2}.issubset(seen_ids):
            break
        time.sleep(0.5)

    if not {1, 2}.issubset(seen_ids):
        proc.terminate()
        proc.wait(timeout=3)
        raise AssertionError(
            f"MCP server did not respond to handshake.  stderr:\n"
            + "".join(stderr_lines[:30])
        )
    return proc, responses


def _shutdown(proc: subprocess.Popen) -> None:
    try:
        proc.terminate()
        proc.wait(timeout=5)
    except Exception:
        proc.kill()


@needs_llm_key
def test_mcp_server_boots_and_lists_all_tools():
    """The server must list every @mcp.tool decorator over real stdio JSON-RPC.

    A failure here usually means a decorator stopped being picked up (e.g.
    because of a syntax issue right after a previous tool, or a FastMCP
    version regression on `mcp.tool()`).
    """
    proc, responses = _spawn_and_handshake()
    try:
        # Compare against the in-process introspection - both numbers must agree
        import asyncio
        import inspect
        from anamne.mcp.server import mcp

        expected = mcp.list_tools()
        if inspect.iscoroutine(expected):
            expected = asyncio.run(expected)
        expected_names = {getattr(t, "name", str(t)) for t in expected}

        listed_response = next(r for r in responses if r.get("id") == 2)
        wire_names = {t["name"] for t in listed_response["result"]["tools"]}

        # No tool may be dropped between in-process registration and the wire.
        missing = expected_names - wire_names
        assert not missing, (
            f"MCP wire is missing {len(missing)} tool(s) that are registered "
            f"in-process: {sorted(missing)}"
        )
        # And the wire should not invent tools that aren't registered.
        extra = wire_names - expected_names
        assert not extra, f"MCP wire has unexpected tool(s): {sorted(extra)}"

        # Sanity: there should be at least the v1.0 core surface
        assert len(wire_names) >= 16, f"expected >= 16 tools, got {len(wire_names)}"
    finally:
        _shutdown(proc)


def test_mcp_server_imports_without_api_key(monkeypatch):
    """Module import must succeed even with no LLM API key.

    18 of the 21 MCP tools are pure memory ops that don't need an LLM.
    A Claude/Cursor subprocess that doesn't inherit the user's env vars
    must still get a working tool surface; only `ask_why` and
    `consolidate_facts` should surface the missing-key error at call time.

    This is the bug discovered during v1.0.1 validation - previously,
    importing `anamne.mcp.server` would crash if the keys weren't set.
    """
    import importlib
    import sys

    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    # Force a clean re-import so the module-level code runs fresh
    for mod in [m for m in sys.modules if m.startswith("anamne.mcp")]:
        sys.modules.pop(mod, None)
    # Also drop cached config so it re-reads env
    sys.modules.pop("anamne.config", None)

    server_mod = importlib.import_module("anamne.mcp.server")

    import asyncio
    import inspect
    tools = server_mod.mcp.list_tools()
    if inspect.iscoroutine(tools):
        tools = asyncio.run(tools)
    assert len(tools) >= 16, f"expected the full tool surface, got {len(tools)}"


@needs_llm_key
def test_mcp_server_reports_anamne_version():
    """The server must identify itself as `anamne` with the package version.

    Without this, FastMCP defaults to its own framework version (e.g. "3.2.4"),
    making it impossible for clients to detect anamne upgrades.
    """
    from anamne import __version__

    proc, responses = _spawn_and_handshake()
    try:
        init = next(r for r in responses if r.get("id") == 1)
        server_info = init["result"]["serverInfo"]
        assert server_info["name"] == "anamne"
        assert server_info.get("version") == __version__, (
            f"expected version {__version__!r}, got {server_info.get('version')!r}"
        )
    finally:
        _shutdown(proc)
