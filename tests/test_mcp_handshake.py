"""Both MCP servers must complete the standard client handshake (Cursor / Claude Code send this first)."""
import io
import json

from activesite.adapters import zetaris_mcp
from activesite.adapters.catalog_standin import CatalogStandin
from activesite.memory import meterless_mcp

OPENING = [
    {"jsonrpc": "2.0", "id": 0, "method": "initialize",
     "params": {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "cursor", "version": "x"}}},
    {"jsonrpc": "2.0", "method": "notifications/initialized"},
    {"jsonrpc": "2.0", "id": 1, "method": "ping"},
    {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
]


def _run(run_server, monkeypatch, *args):
    monkeypatch.setattr("sys.stdin", io.StringIO("".join(json.dumps(m) + "\n" for m in OPENING)))
    out = io.StringIO()
    monkeypatch.setattr("sys.stdout", out)
    run_server(*args)
    return [json.loads(line) for line in out.getvalue().splitlines()]


def _check(replies, server_name, tool):
    # one reply per request with an id; the notification gets none
    assert [r["id"] for r in replies] == [0, 1, 2]
    init = replies[0]["result"]
    assert init["protocolVersion"] == "2025-06-18"
    assert "tools" in init["capabilities"] and init["serverInfo"]["name"] == server_name
    assert replies[1]["result"] == {}
    assert tool in [t["name"] for t in replies[2]["result"]["tools"]]


def test_zetaris_mcp_handshake(tmp_path, monkeypatch):
    replies = _run(zetaris_mcp.run_mcp_server, monkeypatch, CatalogStandin(offline=True, cache_dir=tmp_path))
    _check(replies, "zetaris-data-catalog", "query")


def test_meterless_mcp_handshake(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)   # MeterlessHMEM keeps its ledger under the working directory
    replies = _run(meterless_mcp.run_mcp_server, monkeypatch)
    _check(replies, "meterless-memory", "query_memory")
