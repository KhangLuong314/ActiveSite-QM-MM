"""catalog-STANDIN (DuckDB), Zetaris adapter, adapter selection and the read-only MCP query tool."""
import json
import uuid

import httpx

from activesite.adapters import zetaris as zmod
from activesite.adapters.catalog_standin import LABEL, CatalogStandin
from activesite.adapters.zetaris import ResilientCatalog, ZetarisAdapter, get_adapter
from activesite.adapters.zetaris_mcp import handle_zetaris_request, validate_select
from activesite.agent.core import DataScout


def test_standin_builds_three_queries_offline(tmp_path):
    adapter = CatalogStandin(offline=True, cache_dir=tmp_path)
    adapter.prepare({"system": "egfr_erlotinib", "pdb_query": "EGFR kinase erlotinib"})
    out = DataScout(adapter).gather({"system": "egfr_erlotinib", "site": "A"})
    assert out["label"] == LABEL
    assert out["sql"]["q1_expert"].startswith("SELECT * FROM pg.public.lab_runs WHERE system = 'egfr_erlotinib' AND site = 'A'")
    assert "FROM eda_synthetic" in out["sql"]["q2_analogy"] and "ORDER BY abs(total) DESC LIMIT 6" in out["sql"]["q2_analogy"]
    assert out["sql"]["q3_pdb"].startswith("SELECT pdb_id, resolution, title FROM rcsb_entries WHERE system = 'egfr_erlotinib'")
    # offline: Postgres and MinIO are skipped (errors recorded), the RCSB table exists but is empty
    # offline: lab_runs is built in memory from data/reference via seed.lab_rows(), so the expert row exists
    assert out["expert"]["case_id"] == "egfr_erlotinib" and out["expert"]["status"] == "none"
    assert out["analogy"] == [] and out["pdb"] == []
    assert not any(e.startswith("q1_expert") for e in out["errors"]) and any(e.startswith("q2_analogy") for e in out["errors"])
    assert "lab_runs built in memory" in adapter.sources["postgres"]
    assert adapter.sources["postgres"].startswith("skipped") and adapter.sources["minio"].startswith("skipped")
    assert adapter.run_sql("SELECT COUNT(*) AS n FROM rcsb_entries") == [{"n": 0}]


def test_standin_uses_rcsb_cache(tmp_path):
    cache = tmp_path / "rcsb" / "egfr_kinase_erlotinib.json"
    cache.parent.mkdir(parents=True)
    cache.write_text(json.dumps([{"pdb_id": "1M17", "resolution": 2.6, "title": "EGFR/erlotinib", "system": "egfr_erlotinib", "source": "cache"}]))
    adapter = CatalogStandin(offline=True, cache_dir=tmp_path)
    adapter.prepare({"system": "egfr_erlotinib", "pdb_query": "EGFR kinase erlotinib"})
    rows = adapter.run_sql("SELECT pdb_id, resolution FROM rcsb_entries WHERE system = 'egfr_erlotinib' ORDER BY resolution")
    assert rows == [{"pdb_id": "1M17", "resolution": 2.6}]


def test_mcp_query_is_read_only(tmp_path):
    adapter = CatalogStandin(offline=True, cache_dir=tmp_path)
    tools = handle_zetaris_request(adapter, {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}})
    assert [t["name"] for t in tools["result"]["tools"]] == ["list_sources", "query"]
    src = json.loads(handle_zetaris_request(adapter, {"jsonrpc": "2.0", "id": 2, "method": "tools/call",
                                                      "params": {"name": "list_sources", "arguments": {}}})["result"]["content"][0]["text"])
    assert src["label"] == LABEL and src["tables"]["lab_runs"] == "pg.public.lab_runs"
    for bad in ("DROP TABLE lab_runs", "SELECT 1; DROP TABLE lab_runs", "INSERT INTO x VALUES (1)", "ATTACH 'x' AS y",
                "SELECT * FROM x; --", "COPY x TO 'y'", ""):
        resp = handle_zetaris_request(adapter, {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "query", "arguments": {"sql": bad}}})
        assert "error" in resp and "rejected" in resp["error"]["message"], bad
    assert validate_select("  select 1 as n ;") == "select 1 as n"
    good = handle_zetaris_request(adapter, {"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": "query", "arguments": {"sql": "SELECT 1 AS n"}}})
    assert json.loads(good["result"]["content"][0]["text"]) == {"label": LABEL, "rows": [{"n": 1}]}


def test_zetaris_headers_and_parsing(monkeypatch):
    calls = []

    def fake_post(url, json=None, headers=None, timeout=None):
        calls.append((url, json, headers))
        payload = {"columns": [{"name": "system"}, {"name": "qmcharge"}], "rows": [["ippoi_wt", 1]]} if len(calls) == 1 \
            else {"data": [{"a": 1}, {"a": 2}]}
        return httpx.Response(200, json=payload, request=httpx.Request("POST", url))

    monkeypatch.setattr(zmod.httpx, "post", fake_post)
    monkeypatch.setenv("ZETARIS_TABLE_LAB_RUNS", "lab.runs_v2")
    z = ZetarisAdapter(base_url="https://z.example/api/", api_key="tok", org_id="7")
    assert z.label == "zetaris" and z.tables["lab_runs"] == "lab.runs_v2"
    assert z.run_sql("SELECT system, qmcharge FROM lab.runs_v2") == [{"system": "ippoi_wt", "qmcharge": 1}]
    assert z.run_sql("SELECT a FROM t") == [{"a": 1}, {"a": 2}]
    for url, body, headers in calls:
        assert url == "https://z.example/api/sql-editor/sqls/run" and "sql" in body
        assert headers["Authorization"] == "Bearer tok" and headers["X-Org-ID"] == "7"
        uuid.UUID(headers["X-Request-ID"])
    assert calls[0][2]["X-Request-ID"] != calls[1][2]["X-Request-ID"]


def test_get_adapter_selection(monkeypatch):
    monkeypatch.delenv("ZETARIS_REST_URL", raising=False)
    monkeypatch.delenv("ZETARIS_API_KEY", raising=False)
    assert get_adapter().label == LABEL
    monkeypatch.setenv("ZETARIS_REST_URL", "https://z.example")
    monkeypatch.setenv("ZETARIS_API_KEY", "k")
    adapter = get_adapter()   # wrapped: Zetaris when it answers, labelled stand-in when not (test_zetaris_fallback)
    assert isinstance(adapter, ResilientCatalog) and adapter.primary.label == "zetaris"
