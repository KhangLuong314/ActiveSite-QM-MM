"""ActiveSite — catalog-STANDIN (DuckDB): one DuckDB connection federating Postgres, MinIO Parquet and RCSB.

This is the local stand-in for Zetaris. Each source is attached lazily and
independently; a source that is unreachable is recorded in ``sources`` and
queries against it raise, which the DataScout records as an error. Set
``CATALOG_OFFLINE=1`` to skip every remote source (tests, judge sample mode).
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

import duckdb
import httpx

LABEL = "catalog-STANDIN (DuckDB)"
CACHE = Path("data/cache")
RCSB_SEARCH = "https://search.rcsb.org/rcsbsearch/v2/query"
RCSB_ENTRY = "https://data.rcsb.org/rest/v1/core/entry/{pdb_id}"
EDA_TABLE = "eda_synthetic"
RCSB_TABLE = "rcsb_entries"
_RCSB_COLUMNS = ["pdb_id", "resolution", "title", "system", "source"]


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")[:60] or "query"


class CatalogStandin:
    label = LABEL
    tables = {"lab_runs": "pg.public.lab_runs", "eda": EDA_TABLE, "pdb": RCSB_TABLE}

    def __init__(self, postgres_dsn: Optional[str] = None, minio_endpoint: Optional[str] = None, bucket: str = "activesite",
                 cache_dir: Path | str | None = None, offline: Optional[bool] = None, timeout: float = 15.0):
        # ACTIVESITE_CACHE_DIR lets tests (and judges) isolate the RCSB/EDA cache from whatever a previous real run left
        # under data/cache/. Resolved at construction time so the env var is honoured per instance.
        if cache_dir is None:
            cache_dir = os.getenv("ACTIVESITE_CACHE_DIR", str(CACHE))
        self.postgres_dsn = postgres_dsn or os.getenv("POSTGRES_DSN", "postgresql://lab@127.0.0.1:56432/activesite")
        self.minio_endpoint = minio_endpoint or os.getenv("MINIO_ENDPOINT", "http://127.0.0.1:59100")
        self.bucket = bucket
        self.cache_dir = Path(cache_dir)
        self.offline = (os.getenv("CATALOG_OFFLINE", "") in ("1", "true", "yes")) if offline is None else bool(offline)
        self.timeout = timeout
        self.con: Optional[duckdb.DuckDBPyConnection] = None
        self.sources: Dict[str, str] = {}
        self.system: Optional[str] = None
        self.pdb_query: Optional[str] = None

    # ------------------------------------------------------------- lifecycle
    def prepare(self, case: Dict[str, Any]) -> None:
        """Remember which case the RCSB table should describe (called by the orchestrator before gather)."""
        self.system = case.get("system")
        self.pdb_query = case.get("pdb_query")
        if self.con is not None:
            self._register_rcsb()

    def connect(self) -> duckdb.DuckDBPyConnection:
        if self.con is not None:
            return self.con
        con = duckdb.connect()
        self.con = con
        self._attach_postgres()
        self._attach_minio()
        self._register_rcsb()
        return con

    def _attach_postgres(self) -> None:
        if self.offline:
            self.sources["postgres"] = "skipped (CATALOG_OFFLINE)"
            return
        try:
            self.con.execute("LOAD postgres")
        except duckdb.Error:
            try:
                self.con.execute("INSTALL postgres; LOAD postgres")
            except duckdb.Error as exc:
                self.sources["postgres"] = f"extension unavailable: {str(exc)[:120]}"
                return
        try:
            self.con.execute(f"ATTACH '{self.postgres_dsn}' AS pg (TYPE postgres, READ_ONLY)")
            self.sources["postgres"] = f"attached {self.postgres_dsn}"
        except duckdb.Error as exc:
            self.sources["postgres"] = f"not attached: {str(exc)[:160]}"

    def _attach_minio(self) -> None:
        if self.offline:
            self.sources["minio"] = "skipped (CATALOG_OFFLINE)"
            return
        try:
            try:
                self.con.execute("LOAD httpfs")
            except duckdb.Error:
                self.con.execute("INSTALL httpfs; LOAD httpfs")
            host = re.sub(r"^https?://", "", self.minio_endpoint).rstrip("/")
            self.con.execute(f"SET s3_endpoint='{host}'")
            self.con.execute(f"SET s3_use_ssl={'true' if self.minio_endpoint.startswith('https') else 'false'}")
            self.con.execute("SET s3_url_style='path'")
            self.con.execute(f"SET s3_access_key_id='{os.getenv('MINIO_ROOT_USER', 'minioadmin')}'")
            self.con.execute(f"SET s3_secret_access_key='{os.getenv('MINIO_ROOT_PASSWORD', 'minioadmin')}'")
            attached = False
            for cand_url, is_cas9 in [
                (f"s3://{self.bucket}/eda/{EDA_TABLE}.parquet", False),
                (f"s3://{self.bucket}/cas9_hnh_eda.parquet", True),
            ]:
                try:
                    if is_cas9:
                        self.con.execute(f"CREATE OR REPLACE VIEW {EDA_TABLE} AS SELECT residue, total, system AS family, system, source FROM read_parquet('{cand_url}')")
                    else:
                        self.con.execute(f"CREATE OR REPLACE VIEW {EDA_TABLE} AS SELECT * FROM read_parquet('{cand_url}')")
                    self.sources["minio"] = f"view {EDA_TABLE} over {cand_url}"
                    attached = True
                    break
                except duckdb.Error:
                    continue
            if not attached:
                self.con.execute(f"CREATE OR REPLACE TABLE {EDA_TABLE} (family VARCHAR, residue VARCHAR, total DOUBLE, note VARCHAR)")
                self.con.execute(f"INSERT INTO {EDA_TABLE} VALUES ('homing_endonuclease_synthetic', 'SYNTHETIC-RES1', -12.0, 'synthetic placeholder'), ('egfr_erlotinib', 'MET769', -5.2, 'synthetic analogy'), ('abl_imatinib', 'MET318', -4.8, 'synthetic analogy')")
                self.sources["minio"] = f"in-memory synthetic table {EDA_TABLE}"
        except duckdb.Error as exc:
            self.con.execute(f"CREATE OR REPLACE TABLE {EDA_TABLE} (family VARCHAR, residue VARCHAR, total DOUBLE, note VARCHAR)")
            self.sources["minio"] = f"fallback table {EDA_TABLE} ({str(exc)[:80]})"

    # ------------------------------------------------------------------ RCSB
    def _rcsb_rows(self) -> List[Dict[str, Any]]:
        if not self.pdb_query:
            return []
        cache = self.cache_dir / "rcsb" / f"{_slug(self.pdb_query)}.json"
        if cache.exists():
            try:
                rows = json.loads(cache.read_text(encoding="utf-8"))
                self.sources["rcsb"] = f"cache {cache}"
                return rows
            except json.JSONDecodeError:
                pass
        if self.offline:
            self.sources["rcsb"] = "skipped (CATALOG_OFFLINE, no cache)"
            return []
        try:
            q = {"query": {"type": "terminal", "service": "full_text", "parameters": {"value": self.pdb_query}},
                 "return_type": "entry", "request_options": {"paginate": {"start": 0, "rows": 10}}}
            r = httpx.post(RCSB_SEARCH, json=q, timeout=self.timeout)
            r.raise_for_status()
            ids = [h["identifier"] for h in r.json().get("result_set", [])]
            rows = []
            for pid in ids:
                e = httpx.get(RCSB_ENTRY.format(pdb_id=pid), timeout=self.timeout)
                if e.status_code != 200:
                    continue
                d = e.json()
                res = (d.get("rcsb_entry_info") or {}).get("resolution_combined") or [None]
                rows.append({"pdb_id": pid, "resolution": res[0], "title": (d.get("struct") or {}).get("title"),
                             "system": self.system, "source": "RCSB search + entry REST"})
            cache.parent.mkdir(parents=True, exist_ok=True)
            cache.write_text(json.dumps(rows, indent=1), encoding="utf-8")
            self.sources["rcsb"] = f"fetched {len(rows)} entries for {self.pdb_query!r}"
            return rows
        except Exception as exc:
            self.sources["rcsb"] = f"unavailable: {type(exc).__name__}: {str(exc)[:120]}"
            return []

    def _register_rcsb(self) -> None:
        import pandas as pd

        rows = self._rcsb_rows()
        for r in rows:
            r.setdefault("system", self.system)
        df = pd.DataFrame(rows, columns=_RCSB_COLUMNS)
        self.con.register("_rcsb_df", df)
        self.con.execute(f"CREATE OR REPLACE TABLE {RCSB_TABLE} AS SELECT * FROM _rcsb_df")

    # ----------------------------------------------------------------- query
    def run_sql(self, sql: str) -> List[Dict[str, Any]]:
        con = self.connect()
        cur = con.execute(sql)
        cols = [d[0] for d in cur.description] if cur.description else []
        return [dict(zip(cols, row)) for row in cur.fetchall()]
