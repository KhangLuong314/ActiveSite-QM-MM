"""ActiveSite — data-layer MCP server (JSON-RPC over stdin/stdout).

Tools: ``list_sources`` (the active adapter's label and tables) and ``query``
(one read-only SELECT). Routes through ``get_adapter()``: Zetaris when
credentials are set, otherwise catalog-STANDIN (DuckDB). Tool names are kept
stable for IDE configs.
"""
from __future__ import annotations

import json
import re
import sys
from typing import Any, Dict, Optional

from activesite.adapters.zetaris import get_adapter

_FORBIDDEN = re.compile(r"\b(insert|update|delete|drop|alter|create|attach|detach|copy|pragma|install|load|call|export|import|truncate|grant|merge|replace|set)\b", re.I)


def validate_select(sql: str) -> str:
    """Return the SQL if it is exactly one SELECT/WITH statement, else raise ValueError."""
    s = (sql or "").strip().rstrip(";").strip()
    if not s:
        raise ValueError("empty query")
    if ";" in s:
        raise ValueError("only a single statement is allowed")
    if not re.match(r"^(select|with)\b", s, re.I):
        raise ValueError("only SELECT queries are allowed")
    if _FORBIDDEN.search(s):
        raise ValueError("query contains a write or control keyword; the data layer is read-only")
    return s


def _ok(req_id: Any, text: str) -> Dict[str, Any]:
    return {"jsonrpc": "2.0", "id": req_id, "result": {"content": [{"type": "text", "text": text}]}}


def _err(req_id: Any, code: int, message: str) -> Dict[str, Any]:
    return {"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}}


def handle_zetaris_request(adapter: Any, req: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    method = req.get("method", "")
    params = req.get("params", {}) or {}
    req_id = req.get("id")
    # MCP handshake: clients (Cursor, Claude Code) open with `initialize` and refuse servers that lack it.
    # Notifications (no id, e.g. notifications/initialized) get no reply.
    if method.startswith("notifications/"):
        return None
    if method == "initialize":
        return {"jsonrpc": "2.0", "id": req_id, "result": {
            "protocolVersion": params.get("protocolVersion") or "2024-11-05",
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "zetaris-data-catalog", "version": "1.0"}}}
    if method == "ping":
        return {"jsonrpc": "2.0", "id": req_id, "result": {}}
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": req_id, "result": {"tools": [
            {"name": "list_sources", "description": f"Active data adapter ({adapter.label}): label and logical->physical tables",
             "inputSchema": {"type": "object"}},
            {"name": "query", "description": f"Run one read-only SELECT through {adapter.label}",
             "inputSchema": {"type": "object", "required": ["sql"], "properties": {"sql": {"type": "string"}}}},
        ]}}
    if method == "tools/call":
        name = params.get("name")
        args = params.get("arguments", {}) or {}
        if name == "list_sources":
            info = {"label": adapter.label, "tables": dict(adapter.tables), "sources": getattr(adapter, "sources", {})}
            return _ok(req_id, json.dumps(info))
        if name == "query":
            try:
                sql = validate_select(str(args.get("sql", "")))
            except ValueError as exc:
                return _err(req_id, -32602, f"rejected: {exc}")
            try:
                rows = adapter.run_sql(sql)
            except Exception as exc:
                return _err(req_id, -32000, f"{adapter.label}: {type(exc).__name__}: {str(exc)[:300]}")
            return _ok(req_id, json.dumps({"label": adapter.label, "rows": rows}, default=str))
        return _err(req_id, -32601, f"Tool {name} not found")
    return _err(req_id, -32601, f"Method {method} not found")


def run_mcp_server(adapter: Optional[Any] = None) -> None:
    adapter = adapter or get_adapter()
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            resp = handle_zetaris_request(adapter, json.loads(line))
        except Exception as exc:
            resp = _err(None, -32700, str(exc))
        if resp is None:
            continue
        sys.stdout.write(json.dumps(resp, default=str) + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    run_mcp_server()
