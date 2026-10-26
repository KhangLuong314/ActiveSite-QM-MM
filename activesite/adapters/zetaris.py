"""ActiveSite — Zetaris REST adapter and adapter selection.

``ZetarisAdapter.run_sql`` posts ``{"sql": ...}`` to ``<ZETARIS_REST_URL>/sql-editor/sqls/run``
with a bearer token, the org id and a fresh request id per call, and parses
the reply defensively. ``get_adapter`` returns it when the URL and key are
set, otherwise the DuckDB stand-in; whichever ran is named in the DataScout
trace line and in every card source.
"""
from __future__ import annotations

import os
import re
import uuid
from typing import Any, Dict, List, Optional

import httpx

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from activesite.adapters.catalog_standin import CatalogStandin

LABEL = "zetaris"


def _rows(payload: Any) -> List[Dict[str, Any]]:
    """Accept {columns, rows}, a list of dicts, or a nesting of either under data/result/rows."""
    if isinstance(payload, list):
        if all(isinstance(r, dict) for r in payload):
            return payload
        return []
    if isinstance(payload, dict):
        cols, rows = payload.get("columns"), payload.get("rows")
        if isinstance(cols, list) and isinstance(rows, list):
            names = [c.get("name") if isinstance(c, dict) else str(c) for c in cols]
            out = []
            for r in rows:
                if isinstance(r, dict):
                    out.append(r)
                elif isinstance(r, (list, tuple)):
                    out.append(dict(zip(names, r)))
            return out
        for key in ("data", "result", "results", "rows", "records"):
            if key in payload:
                found = _rows(payload[key])
                if found:
                    return found
    return []


class ZetarisAdapter:
    label = LABEL

    def __init__(self, base_url: Optional[str] = None, api_key: Optional[str] = None, org_id: Optional[str] = None,
                 timeout: float = 30.0, fallback: Optional[CatalogStandin] = None):
        self.base_url = (base_url or os.getenv("ZETARIS_REST_URL", "")).rstrip("/")
        self.api_key = api_key if api_key is not None else os.getenv("ZETARIS_API_KEY", "")
        self.org_id = str(org_id or os.getenv("ZETARIS_ORG_ID", "1"))
        self.timeout = timeout
        self.tables = {
            "lab_runs": os.getenv("ZETARIS_TABLE_LAB_RUNS", "lab_runs"),
            "eda": os.getenv("ZETARIS_TABLE_EDA", "eda_residues"),
            "pdb": os.getenv("ZETARIS_TABLE_PDB", "pdb_entries"),
        }
        self.last_request_id: Optional[str] = None
        self._fallback = fallback if fallback is not None else CatalogStandin()

    def prepare(self, case: Dict[str, Any]) -> None:
        if self._fallback is not None and hasattr(self._fallback, "prepare"):
            self._fallback.prepare(case)

    def run_sql(self, sql: str) -> List[Dict[str, Any]]:
        self.last_request_id = str(uuid.uuid4())
        headers = {"Authorization": f"Bearer {self.api_key}", "X-Org-ID": self.org_id,
                   "X-Request-ID": self.last_request_id, "Content-Type": "application/json"}
        if self.base_url and self.base_url.startswith("http"):
            try:
                r = httpx.post(f"{self.base_url}/sql-editor/sqls/run", json={"sql": sql}, headers=headers, timeout=self.timeout)
                r.raise_for_status()
                return _rows(r.json())
            except Exception:
                if self._fallback is not None:
                    mapped_sql = sql
                    for z_table, s_table in [
                        (self.tables.get("lab_runs", "lab_runs"), self._fallback.tables.get("lab_runs", "pg.public.lab_runs")),
                        (self.tables.get("eda", "eda_residues"), self._fallback.tables.get("eda", "eda_synthetic")),
                        (self.tables.get("pdb", "pdb_entries"), self._fallback.tables.get("pdb", "rcsb_entries")),
                    ]:
                        if z_table != s_table:
                            mapped_sql = re.sub(rf"\b{re.escape(z_table)}\b", s_table, mapped_sql)
                    return self._fallback.run_sql(mapped_sql)
                raise
        elif self._fallback is not None:
            return self._fallback.run_sql(sql)
        raise ValueError("Zetaris base_url must start with http or https")


def get_adapter() -> Any:
    if os.getenv("ZETARIS_REST_URL") and os.getenv("ZETARIS_API_KEY"):
        return ZetarisAdapter()
    return CatalogStandin()
