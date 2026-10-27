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

    def fake_request(method, url, json=None, params=None, headers=None, timeout=None):
        calls.append((method, url, json, params, headers))
        if url.endswith("/query/sql/start"):
            body = {"records": [{"system": "ippoi_wt", "qmcharge": "1"}] if "qmcharge" in json["select"] else
                    [{"a": "1"}], "pageNumber": 1, "pageLimit": 100, "totalCount": 2,
                    "totalPages": 1 if "qmcharge" in json["select"] else 2, "queryToken": "qt"}
        elif url.endswith("/query/sql/page"):
            body = {"records": [{"a": "2"}], "pageNumber": 2, "totalCount": 2, "totalPages": 2, "queryToken": "qt"}
        else:
            body = {}
        return httpx.Response(200, json=body, request=httpx.Request(method, url))

    monkeypatch.setattr(zmod.httpx, "request", fake_request)
    monkeypatch.setenv("ZETARIS_TABLE_LAB_RUNS", "lab.runs_v2")
    z = ZetarisAdapter(base_url="https://z.example/api/", api_key="tok", org_id="7")
    assert z.label == "zetaris" and z.tables["lab_runs"] == "lab.runs_v2" and z.tables["eda"] == "ACTIVESITE.eda_synthetic"
    # Zetaris returns text; qmcharge comes back as an int so the expert comparison is exact
    assert z.run_sql("SELECT system, qmcharge FROM lab.runs_v2") == [{"system": "ippoi_wt", "qmcharge": 1}]
    assert z.run_sql("SELECT a FROM t") == [{"a": "1"}, {"a": "2"}]          # page 2 fetched and appended
    starts = [c for c in calls if c[1].endswith("/query/sql/start")]
    assert [c[2] for c in starts] == [{"select": "SELECT system, qmcharge FROM lab.runs_v2", "pageLimit": 100},
                                      {"select": "SELECT a FROM t", "pageLimit": 100}]
    assert any(c[0] == "GET" and c[1].endswith("/query/sql/page") and c[3]["pageNumber"] == 2 for c in calls)
    assert any(c[0] == "DELETE" and c[1] == "https://z.example/api/query/sql/close/qt" for c in calls)
    for _, url, _, _, headers in calls:
        assert url.startswith("https://z.example/api/")
        assert headers["Authorization"] == "Bearer tok" and headers["X-Org-ID"] == "7"
        uuid.UUID(headers["X-Request-ID"])
    assert len({c[4]["X-Request-ID"] for c in calls}) == len(calls)
    monkeypatch.setenv("ZETARIS_TABLE_LAB_RUNS", "")          # an empty .env line still gets the default table
    assert ZetarisAdapter(base_url="https://z").tables["lab_runs"] == "ACTIVESITE.expert_runs"


def test_zetaris_login_token_is_cached_and_refreshed_once_on_401(monkeypatch):
    logins, seen = [], []

    def fake_get(url, auth=None, headers=None, timeout=None):
        logins.append(auth)
        return httpx.Response(200, json={"idToken": f"jwt{len(logins)}", "refreshToken": "r"},
                              request=httpx.Request("GET", url))

    def fake_request(method, url, json=None, params=None, headers=None, timeout=None):
        seen.append(headers["Authorization"])
        code = 401 if headers["Authorization"] == "Bearer jwt1" and len(seen) == 2 else 200
        return httpx.Response(code, json={"records": [{"x": "1"}], "totalPages": 1},
                              request=httpx.Request(method, url))

    monkeypatch.setattr(zmod.httpx, "get", fake_get)
    monkeypatch.setattr(zmod.httpx, "request", fake_request)
    z = ZetarisAdapter(base_url="http://z/api/v1.0", api_key="", user="admin@example.com", password="pw")
    assert z.run_sql("SELECT 1") == [{"x": "1"}]       # login once
    assert z.run_sql("SELECT 2") == [{"x": "1"}]       # token expired -> one re-login, then retried
    assert logins == [("admin@example.com", "pw")] * 2
    assert seen == ["Bearer jwt1", "Bearer jwt1", "Bearer jwt2"]


def test_get_adapter_selection(monkeypatch):
    monkeypatch.delenv("ZETARIS_REST_URL", raising=False)
    monkeypatch.delenv("ZETARIS_API_KEY", raising=False)
    assert get_adapter().label == LABEL
    monkeypatch.setenv("ZETARIS_REST_URL", "https://z.example")
    monkeypatch.setenv("ZETARIS_API_KEY", "k")
    adapter = get_adapter()   # wrapped: Zetaris when it answers, labelled stand-in when not (test_zetaris_fallback)
    assert isinstance(adapter, ResilientCatalog) and adapter.primary.label == "zetaris"
