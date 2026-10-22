"""ActiveSite — Data Catalog MCP Adapter.

User-facing name: ``catalog-STANDIN (DuckDB)``. This is a local DuckDB stand-in
for the Zetaris federated catalog; it becomes a real Zetaris connection only once
``ZETARIS_REST_URL`` / ``ZETARIS_API_KEY`` are configured (a later prompt).
Class names and MCP tool names are kept stable for that migration.
"""
from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional
import duckdb
from pydantic import BaseModel, Field

from activesite.adapters.scout import DataScout

logger = logging.getLogger(__name__)


CATALOG_DISPLAY_NAME = "catalog-STANDIN (DuckDB)"


class ZetarisCatalog:
    """Local DuckDB stand-in for the Zetaris federated catalog (``catalog-STANDIN (DuckDB)``)."""

    display_name = CATALOG_DISPLAY_NAME

    def __init__(self, db_path: str = ":memory:"):
        self.con = duckdb.connect(db_path)
        self.scout = DataScout()
        self._init_catalog_tables()

    def _init_catalog_tables(self) -> None:
        """Create and populate catalog tables for benchmark cases and reference structures."""
        self.con.execute(
            """
            CREATE TABLE IF NOT EXISTS benchmark_cases (
                case_id VARCHAR PRIMARY KEY,
                kind VARCHAR,
                system VARCHAR,
                site VARCHAR,
                question VARCHAR,
                pdb VARCHAR,
                ligand VARCHAR,
                ph DOUBLE,
                min_steps INTEGER
            );
            """
        )

        # Populate with existing benchmark cases
        for case_name in self.scout.list_benchmark_cases():
            try:
                data = self.scout.load_benchmark_case(case_name)
                self.con.execute(
                    """
                    INSERT OR REPLACE INTO benchmark_cases VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    [
                        data.get("id", case_name),
                        data.get("kind", "enzyme"),
                        data.get("system", case_name),
                        data.get("site", "A"),
                        data.get("question", ""),
                        data.get("pdb", data.get("parm7", "")),
                        data.get("ligand", ""),
                        data.get("ph", 7.4),
                        data.get("min_steps", 500),
                    ],
                )
            except Exception as exc:
                logger.warning("Failed to index case %s into catalog: %s", case_name, exc)

    def query_catalog(self, query: str) -> List[Dict[str, Any]]:
        """Execute a SQL query against the local stand-in catalog."""
        res = self.con.execute(query)
        columns = [desc[0] for desc in res.description]
        rows = res.fetchall()
        return [dict(zip(columns, row)) for row in rows]

    def search_cases(self, keyword: str) -> List[Dict[str, Any]]:
        """Search benchmark cases by system name, ligand, or question."""
        sql = """
            SELECT * FROM benchmark_cases
            WHERE lower(system) LIKE lower(?)
               OR lower(ligand) LIKE lower(?)
               OR lower(question) LIKE lower(?)
        """
        pattern = f"%{keyword}%"
        return self.query_catalog_with_params(sql, [pattern, pattern, pattern])

    def query_catalog_with_params(self, sql: str, params: list) -> List[Dict[str, Any]]:
        res = self.con.execute(sql, params)
        columns = [desc[0] for desc in res.description]
        rows = res.fetchall()
        return [dict(zip(columns, row)) for row in rows]


def handle_zetaris_request(catalog: ZetarisCatalog, req: Dict[str, Any]) -> Dict[str, Any]:
    method = req.get("method", "")
    params = req.get("params", {})
    req_id = req.get("id")

    if method == "tools/list":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "tools": [
                    {
                        "name": "search_catalog",
                        "description": f"Search PDB structures, ligands, and benchmark cases in {CATALOG_DISPLAY_NAME}",
                        "inputSchema": {
                            "type": "object",
                            "required": ["keyword"],
                            "properties": {"keyword": {"type": "string"}},
                        },
                    },
                    {
                        "name": "sql_query",
                        "description": f"Execute DuckDB SQL over {CATALOG_DISPLAY_NAME}",
                        "inputSchema": {
                            "type": "object",
                            "required": ["query"],
                            "properties": {"query": {"type": "string"}},
                        },
                    },
                    {
                        "name": "resolve_structure",
                        "description": "Fetch or locate PDB structure metadata and ligand components",
                        "inputSchema": {
                            "type": "object",
                            "required": ["pdb_id"],
                            "properties": {"pdb_id": {"type": "string"}},
                        },
                    },
                ]
            },
        }

    elif method == "tools/call":
        tool_name = params.get("name")
        args = params.get("arguments", {})

        if tool_name == "search_catalog":
            results = catalog.search_cases(args.get("keyword", ""))
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {"content": [{"type": "text", "text": json.dumps(results)}]},
            }
        elif tool_name == "sql_query":
            results = catalog.query_catalog(args.get("query", ""))
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {"content": [{"type": "text", "text": json.dumps(results)}]},
            }
        elif tool_name == "resolve_structure":
            meta = catalog.scout.resolve_pdb(args.get("pdb_id", ""))
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {"content": [{"type": "text", "text": json.dumps(meta.model_dump())}]},
            }

    return {
        "jsonrpc": "2.0",
        "id": req_id,
        "error": {"code": -32601, "message": f"Method {method} not found"},
    }


def run_mcp_server() -> None:
    catalog = ZetarisCatalog()
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
            resp = handle_zetaris_request(catalog, req)
            sys.stdout.write(json.dumps(resp) + "\n")
            sys.stdout.flush()
        except Exception as exc:
            err_resp = {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": str(exc)}}
            sys.stdout.write(json.dumps(err_resp) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    run_mcp_server()
