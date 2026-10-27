"""PDB search, fetch and bundled examples, with httpx mocked (no network)."""
import httpx
import pytest
from fastapi.testclient import TestClient

from activesite.adapters import pdb_search
from activesite.server import main

GQL = {"data": {"entries": [
    {"rcsb_id": "4ZAU", "struct": {"title": "EGFR kinase in complex with AZD9291"}, "rcsb_entry_info": {"resolution_combined": [2.8]},
     "polymer_entities": [{"rcsb_entity_source_organism": [{"scientific_name": "Homo sapiens"}]}],
     "nonpolymer_entities": [{"nonpolymer_comp": {"chem_comp": {"id": "YY3", "name": "osimertinib"}}},
                             {"nonpolymer_comp": {"chem_comp": {"id": "SO4", "name": "SULFATE ION"}}},
                             {"nonpolymer_comp": {"chem_comp": {"id": "MG", "name": "MAGNESIUM ION"}}}]},
    {"rcsb_id": "1M17", "struct": {"title": "EGFR with erlotinib"}, "rcsb_entry_info": {"resolution_combined": [2.6]},
     "polymer_entities": [], "nonpolymer_entities": None}]}}
TINY = ("ATOM      1  N   ALA A   1       1.000   0.000   0.000  1.00  0.00           N\n"
        "ATOM      2  CA  ALA A   1       2.400   0.000   0.000  1.00  0.00           C\n"
        "HETATM    3  C1  YY3 A 901       2.000   2.000   1.000  1.00  0.00           C\n"
        "HETATM    4  N1  YY3 A 901       2.800   2.600   1.400  1.00  0.00           N\nEND\n")


def _resp(status=200, json=None, content=b""):
    req = httpx.Request("GET", "https://example.test")
    if json is not None:
        return httpx.Response(status, json=json, request=req)
    return httpx.Response(status, content=content, request=req)


@pytest.fixture(autouse=True)
def isolate(tmp_path, monkeypatch):
    monkeypatch.setenv("ACTIVESITE_UPLOADS_DIR", str(tmp_path / "uploads"))
    pdb_search._cache.clear()


@pytest.fixture
def client():
    return TestClient(main.app)


def test_search_classifies_ligands_metals_and_additives(monkeypatch, client):
    calls = []

    def post(url, json=None, timeout=None):
        calls.append(url)
        if url == pdb_search.RCSB_SEARCH:
            assert json["query"]["parameters"]["value"] == "osimertinib"
            return _resp(json={"result_set": [{"identifier": "4ZAU"}, {"identifier": "1M17"}]})
        return _resp(json=GQL)

    monkeypatch.setattr(pdb_search.httpx, "post", post)
    data = client.get("/api/pdb/search", params={"q": "  osimertinib\x07 "}).json()
    first = data["results"][0]
    assert data["query"] == "osimertinib"
    assert first == {"pdb_id": "4ZAU", "title": "EGFR kinase in complex with AZD9291", "organism": "Homo sapiens", "resolution": 2.8,
                     "ligands": [{"id": "YY3", "name": "osimertinib"}], "metals": [{"id": "MG", "name": "MAGNESIUM ION"}],
                     "verified_case": "egfr_osimertinib"}
    assert data["results"][1]["ligands"] == [] and data["results"][1]["organism"] is None and data["results"][1]["verified_case"] is None
    client.get("/api/pdb/search", params={"q": "OSIMERTINIB"})
    assert len(calls) == 2                       # second query served from cache


def test_repo_case_entry_is_pinned_first_when_the_query_names_its_drug(monkeypatch, client):
    sent = {}

    def post(url, json=None, timeout=None):
        if url == pdb_search.RCSB_SEARCH:
            return _resp(json={"result_set": [{"identifier": i} for i in ("4CSV", "3FW1", "2HYY")]})
        sent["ids"] = json["variables"]["ids"]
        return _resp(json={"data": {"entries": [{"rcsb_id": i, "struct": {"title": i}} for i in json["variables"]["ids"]]}})

    monkeypatch.setattr(pdb_search.httpx, "post", post)
    rows = client.get("/api/pdb/search", params={"q": "imatinib"}).json()["results"]
    assert sent["ids"] == ["2HYY", "4CSV", "3FW1"]                       # no duplicate, pinned first
    assert rows[0]["pdb_id"] == "2HYY" and rows[0]["verified_case"] == "abl_imatinib_a"
    assert pdb_search._verified_pins("lactate dehydrogenase") == {}


def test_search_validation_and_no_hits(monkeypatch, client):
    assert client.get("/api/pdb/search", params={"q": "x" * 81}).status_code == 422
    assert client.get("/api/pdb/search", params={"q": "\x00\x01 "}).status_code == 422
    monkeypatch.setattr(pdb_search.httpx, "post", lambda *a, **k: _resp(204))
    assert client.get("/api/pdb/search", params={"q": "nothing like this"}).json()["results"] == []


def test_network_failure_is_one_plain_sentence(monkeypatch, client):
    def boom(*a, **k):
        raise httpx.ConnectError("offline")

    monkeypatch.setattr(pdb_search.httpx, "post", boom)
    monkeypatch.setattr(pdb_search.httpx, "get", boom)
    r = client.get("/api/pdb/search", params={"q": "imatinib"})
    assert r.status_code == 503 and r.json()["detail"] == pdb_search.UNREACHABLE
    r = client.post("/api/structures/fetch", json={"pdb_id": "4ZAU"})
    assert r.status_code == 503 and r.json()["detail"] == pdb_search.UNREACHABLE


def test_fetch_registers_like_an_upload(monkeypatch, client):
    urls = []

    def get(url, timeout=None, follow_redirects=None):
        urls.append(url)
        return _resp(content=TINY.encode())

    monkeypatch.setattr(pdb_search.httpx, "get", get)
    rec = client.post("/api/structures/fetch", json={"pdb_id": "4zau"}).json()
    assert urls == ["https://files.rcsb.org/download/4ZAU.pdb"]
    assert rec["pdb_id"] == "4ZAU" and rec["source"] == "RCSB PDB" and rec["name"] == "4ZAU"
    assert [lig["resname"] for lig in rec["ligands"]] == ["YY3"]
    assert client.get(f"/api/structures/{rec['structure_id']}/file").status_code == 200
    assert any(r["structure_id"] == rec["structure_id"] and r["pdb_id"] == "4ZAU" for r in client.get("/api/structures").json())


@pytest.mark.parametrize("bad", ["", "ZAU4", "4ZA", "4ZAU5", "../etc", "4ZA/"])
def test_fetch_rejects_bad_ids_without_network(monkeypatch, client, bad):
    monkeypatch.setattr(pdb_search.httpx, "get", lambda *a, **k: pytest.fail("no request for a bad id"))
    assert client.post("/api/structures/fetch", json={"pdb_id": bad}).status_code == 422


def test_fetch_unknown_id_is_404_and_falls_back_to_cif(monkeypatch, client):
    seen = []
    monkeypatch.setattr(pdb_search.httpx, "get", lambda url, **k: (seen.append(url), _resp(404))[1])
    assert client.post("/api/structures/fetch", json={"pdb_id": "9ZZZ"}).status_code == 404
    assert seen == ["https://files.rcsb.org/download/9ZZZ.pdb", "https://files.rcsb.org/download/9ZZZ.cif"]


def test_bundled_example_needs_no_client_file(client):
    rec = client.post("/api/structures/example", json={"example": "egfr_1m17"}).json()
    assert rec["source"] == "bundled example" and "AQ4" in [lig["resname"] for lig in rec["ligands"]]
    assert client.post("/api/structures/example", json={"example": "../../etc/passwd"}).status_code == 404
