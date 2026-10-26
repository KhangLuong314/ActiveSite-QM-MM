"""ActiveSite — Zetaris REST adapter and adapter selection.

``ZetarisAdapter.run_sql`` posts ``{"sql": ...}`` to ``<ZETARIS_REST_URL>/sql-editor/sqls/run``
with a bearer token, the org id and a fresh request id per call, and parses
the reply defensively. ``get_adapter`` returns it when the URL and key are
set, otherwise the DuckDB stand-in; whichever ran is named in the DataScout
trace line and in every card source.
"""
from __future__ import annotations

import os
import uuid
from typing import Any, Dict, List, Optional

import httpx

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
                 timeout: float = 30.0):
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

    def prepare(self, case: Dict[str, Any]) -> None:  # same hook as the stand-in; nothing to pre-register
        return None

    def run_sql(self, sql: str) -> List[Dict[str, Any]]:
        self.last_request_id = str(uuid.uuid4())
        headers = {"Authorization": f"Bearer {self.api_key}", "X-Org-ID": self.org_id,
                   "X-Request-ID": self.last_request_id, "Content-Type": "application/json"}
        r = httpx.post(f"{self.base_url}/sql-editor/sqls/run", json={"sql": sql}, headers=headers, timeout=self.timeout)
        r.raise_for_status()
        return _rows(r.json())


class ResilientCatalog:
    """Zetaris when it answers, the DuckDB stand-in when it does not; the label always says which.

    Sponsor guidance: a service outage during judging must degrade the run, not break it. On first use the
    wrapper probes Zetaris with ``SELECT 1`` (short timeout). If the probe fails, or a later query hits a
    connection error or timeout, every query goes to the stand-in, with table names translated, and the label
    reads e.g. ``catalog-STANDIN (DuckDB) (Zetaris unreachable: ConnectError)``.
    """

    def __init__(self, primary: Optional[Any] = None, fallback_factory: Any = CatalogStandin, probe_timeout: float = 3.0):
        self.primary = primary if primary is not None else ZetarisAdapter()
        self._fallback_factory = fallback_factory
        self.probe_timeout = probe_timeout
        self.active: Optional[Any] = None
        self.reason: Optional[str] = None
        self._case: Optional[Dict[str, Any]] = None

    def _switch(self, exc: BaseException) -> None:
        self.reason = type(exc).__name__
        self.active = self._fallback_factory()
        if self._case is not None and hasattr(self.active, "prepare"):
            self.active.prepare(self._case)

    def _resolve(self) -> Any:
        if self.active is None:
            saved = self.primary.timeout
            self.primary.timeout = self.probe_timeout
            try:
                self.primary.run_sql("SELECT 1")
                self.active = self.primary
            except Exception as exc:  # unreachable, refused, timed out, auth or HTTP error
                self._switch(exc)
            finally:
                self.primary.timeout = saved
        return self.active

    @property
    def label(self) -> str:
        active = self._resolve()
        return active.label if self.reason is None else f"{active.label} (Zetaris unreachable: {self.reason})"

    @property
    def tables(self) -> Dict[str, str]:
        return self._resolve().tables

    def prepare(self, case: Dict[str, Any]) -> None:
        self._case = case
        active = self._resolve()
        if hasattr(active, "prepare"):
            active.prepare(case)

    def run_sql(self, sql: str) -> List[Dict[str, Any]]:
        active = self._resolve()
        if active is not self.primary:
            return active.run_sql(sql)
        try:
            return active.run_sql(sql)
        except (httpx.ConnectError, httpx.TimeoutException, httpx.RemoteProtocolError) as exc:
            primary_tables = dict(self.primary.tables)
            self._switch(exc)
            for key, name in primary_tables.items():   # the query was written for Zetaris's table names
                sql = sql.replace(name, self.active.tables.get(key, name))
            return self.active.run_sql(sql)


def get_adapter() -> Any:
    if os.getenv("ZETARIS_REST_URL") and os.getenv("ZETARIS_API_KEY"):
        return ResilientCatalog()
    return CatalogStandin()
