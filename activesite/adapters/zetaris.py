"""ActiveSite — Zetaris REST adapter and adapter selection.

``ZetarisAdapter.run_sql`` posts ``{"select": ..., "pageLimit": ...}`` to ``<ZETARIS_REST_URL>/query/sql/start``
(the documented Zetaris query API, verified against a local Zetaris platform 2.4.3) with a bearer token, the org
id and a fresh request id per call, then pages through ``/query/sql/page`` and closes the query. The token is
either ``ZETARIS_API_KEY`` or an id token from ``GET /auth/login`` with ``ZETARIS_USER``/``ZETARIS_PASSWORD``
(refreshed once on 401). Zetaris returns every value as text, so known numeric columns are converted back.
``get_adapter`` returns it when the URL and a credential are set, otherwise the DuckDB stand-in; whichever ran is
named in the DataScout trace line and in every card source.
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


NUMERIC_COLUMNS = {"qmcharge": int, "total": float, "resolution": float}
PAGE_LIMIT = 100   # the API's maximum


def _typed(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Zetaris returns every value as a string; convert the columns DataScout compares as numbers."""
    for r in rows:
        for col, cast in NUMERIC_COLUMNS.items():
            v = r.get(col)
            if isinstance(v, str):
                try:
                    r[col] = cast(float(v)) if cast is int else cast(v)
                except ValueError:
                    r[col] = None if v.strip() in ("", "null", "NULL") else v
    return rows


class ZetarisAdapter:
    label = LABEL

    def __init__(self, base_url: Optional[str] = None, api_key: Optional[str] = None, org_id: Optional[str] = None,
                 timeout: float = 30.0, user: Optional[str] = None, password: Optional[str] = None):
        self.base_url = (base_url or os.getenv("ZETARIS_REST_URL", "")).rstrip("/")
        self.api_key = api_key if api_key is not None else os.getenv("ZETARIS_API_KEY", "")
        self.user = user if user is not None else os.getenv("ZETARIS_USER", "")
        self.password = password if password is not None else os.getenv("ZETARIS_PASSWORD", "")
        self.org_id = str(org_id or os.getenv("ZETARIS_ORG_ID", "1"))
        self.timeout = timeout
        self.tables = {
            # `or`, not a getenv default: an empty ZETARIS_TABLE_* line in .env must still get the default name
            "lab_runs": os.getenv("ZETARIS_TABLE_LAB_RUNS") or "ACTIVESITE.expert_runs",
            "eda": os.getenv("ZETARIS_TABLE_EDA") or "ACTIVESITE.eda_synthetic",
            "pdb": os.getenv("ZETARIS_TABLE_PDB") or "ACTIVESITE.rcsb_entries",
        }
        self.last_request_id: Optional[str] = None
        self._token: Optional[str] = None

    def prepare(self, case: Dict[str, Any]) -> None:  # same hook as the stand-in; nothing to pre-register
        return None

    def _headers(self) -> Dict[str, str]:
        self.last_request_id = str(uuid.uuid4())
        return {"X-Org-ID": self.org_id, "X-Request-ID": self.last_request_id, "Content-Type": "application/json"}

    def _bearer(self, refresh: bool = False) -> str:
        if not (self.user and self.password):
            return self.api_key
        if self._token is None or refresh:
            r = httpx.get(f"{self.base_url}/auth/login", auth=(self.user, self.password), headers=self._headers(),
                          timeout=self.timeout)
            r.raise_for_status()
            self._token = r.json()["idToken"]
        return self._token

    def _call(self, method: str, path: str, **kw: Any) -> httpx.Response:
        for attempt in (0, 1):
            headers = {**self._headers(), "Authorization": f"Bearer {self._bearer(refresh=attempt == 1)}"}
            r = httpx.request(method, f"{self.base_url}{path}", headers=headers, timeout=self.timeout, **kw)
            if r.status_code != 401 or not (self.user and self.password):
                break
        r.raise_for_status()
        return r

    def run_sql(self, sql: str) -> List[Dict[str, Any]]:
        first = self._call("POST", "/query/sql/start", json={"select": sql, "pageLimit": PAGE_LIMIT}).json()
        rows = _rows(first.get("records", first) if isinstance(first, dict) else first)
        token = first.get("queryToken") if isinstance(first, dict) else None
        pages = int(first.get("totalPages") or 1) if isinstance(first, dict) else 1
        for n in range(2, pages + 1):
            page = self._call("GET", "/query/sql/page",
                              params={"queryToken": token, "pageLimit": PAGE_LIMIT, "pageNumber": n}).json()
            rows.extend(_rows(page.get("records", [])))
        if token:
            try:
                self._call("DELETE", f"/query/sql/close/{token}")
            except httpx.HTTPError:
                pass   # closing frees server memory; a failed close must not lose the rows
        return _typed(rows)


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
    has_login = os.getenv("ZETARIS_USER") and os.getenv("ZETARIS_PASSWORD")
    if os.getenv("ZETARIS_REST_URL") and (os.getenv("ZETARIS_API_KEY") or has_login):
        return ResilientCatalog()
    return CatalogStandin()
