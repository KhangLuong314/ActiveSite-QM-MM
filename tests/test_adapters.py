"""Unit tests for DataScout and the catalog-STANDIN (DuckDB) MCP adapter."""
import pytest
from pathlib import Path
from activesite.adapters.scout import DataScout
from activesite.adapters.zetaris_mcp import ZetarisCatalog, handle_zetaris_request


def test_scout_list_and_load_cases():
    scout = DataScout()
    cases = scout.list_benchmark_cases()
    assert "egfr_erlotinib" in cases
    assert "ippoi_site_a" in cases

    egfr_case = scout.load_benchmark_case("egfr_erlotinib")
    assert egfr_case["id"] == "egfr_erlotinib"
    assert egfr_case["ligand"] == "AQ4"
    assert egfr_case["ph"] == 7.4


def test_scout_resolve_local_pdb():
    scout = DataScout()
    # Resolve EGFR 1M17 pdb from local reference
    meta = scout.resolve_pdb("1m17")
    assert meta.identifier == "1M17"
    assert meta.is_offline_cached is True
    assert meta.local_pdb_path is not None
    assert "AQ4" in meta.ligands or len(meta.ligands) > 0


def test_zetaris_catalog_sql_query():
    catalog = ZetarisCatalog()
    # Query case count
    res = catalog.query_catalog("SELECT COUNT(*) AS total FROM benchmark_cases")
    assert len(res) == 1
    assert res[0]["total"] >= 4

    # Search cases
    matches = catalog.search_cases("erlotinib")
    assert len(matches) >= 1
    assert matches[0]["ligand"] == "AQ4"


def test_zetaris_mcp_handler():
    catalog = ZetarisCatalog()

    # Tool list
    req_list = {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}
    resp = handle_zetaris_request(catalog, req_list)
    assert "result" in resp
    assert any(t["name"] == "search_catalog" for t in resp["result"]["tools"])
    assert catalog.display_name == "catalog-STANDIN (DuckDB)"
    assert all("catalog-STANDIN (DuckDB)" in t["description"]
               for t in resp["result"]["tools"] if t["name"] in ("search_catalog", "sql_query"))

    # Search tool call
    req_call = {
        "jsonrpc": "2.0",
        "id": 2,
        "method": "tools/call",
        "params": {"name": "search_catalog", "arguments": {"keyword": "imatinib"}},
    }
    resp_call = handle_zetaris_request(catalog, req_call)
    assert "result" in resp_call
    assert "abl_imatinib" in resp_call["result"]["content"][0]["text"]
