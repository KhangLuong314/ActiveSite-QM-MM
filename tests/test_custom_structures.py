"""Bring your own structure: upload parsing, validation, path safety, mutation, SMILES lookup, custom sample runs."""
import functools
import json
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from activesite.adapters import chemcomp
from activesite.agent import custom
from activesite.agent.orchestrator import run_case
from activesite.chem import uploads
from activesite.memory.meterless import MeterlessHMEM
from activesite.server import main as server

FIXTURE = Path(__file__).parent / "fixtures" / "egfr_1m17_pocket.pdb"
AQ4_SMILES = "COCCOc1cc2ncnc(Nc3cccc(c3)C#C)c2cc1OCCOC"


def _het(serial, name, resname, chain, resi, x, y, z, element):
    return (f"HETATM{serial:>5d} {name:<4s} {resname:>3s} {chain}{resi:>4d}    {x:8.3f}{y:8.3f}{z:8.3f}  1.00 20.00"
            f"          {element:>2s}")


def _fixture_text(extra=()):
    lines = [line for line in FIXTURE.read_text().splitlines() if line != "END"]
    return "\n".join(lines + list(extra)) + "\nEND\n"


def _thr766_og1():
    for line in FIXTURE.read_text().splitlines():
        if line.startswith("ATOM") and line[17:20] == "THR" and int(line[22:26]) == 766 and line[12:16].strip() == "OG1":
            return float(line[30:38]), float(line[38:46]), float(line[46:54])
    raise AssertionError("fixture lost Thr766 OG1")


@pytest.fixture(autouse=True)
def _uploads(tmp_path, monkeypatch):
    monkeypatch.setenv("ACTIVESITE_UPLOADS_DIR", str(tmp_path / "uploads"))
    monkeypatch.setenv("ACTIVESITE_CACHE_DIR", str(tmp_path / "cache"))


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "hmem", MeterlessHMEM(db_path=tmp_path / "h.sqlite", ledger_path=tmp_path / "l.jsonl"))
    monkeypatch.setattr(server, "run_case", functools.partial(run_case, workroot=tmp_path / "runs", log_dir=tmp_path))
    monkeypatch.setattr(custom, "lookup_smiles", lambda r: (AQ4_SMILES, f"RCSB chemcomp {r} (mocked)"))
    monkeypatch.setattr(server, "build_custom_case",
                        lambda spec: custom.build_custom_case(spec, lookup=lambda r: (AQ4_SMILES, f"RCSB chemcomp {r} (mocked)")))
    server.runs.clear()
    return TestClient(server.app)


def _upload(client, text=None, filename="egfr.pdb", name=None):
    files = {"file": (filename, (text if text is not None else FIXTURE.read_text()).encode(), "chemical/x-pdb")}
    return client.post("/api/structures/upload", files=files, data={"name": name} if name else {})


# ---------------------------------------------------------------- parsing
def test_upload_summary_on_real_fixture(client):
    r = _upload(client)
    assert r.status_code == 200, r.text
    rec = r.json()
    assert uploads.ID_RE.match(rec["structure_id"]) and rec["format"] == "pdb" and rec["name"] == "egfr"
    assert rec["chains"] == [{"id": "A", "n_residues": 13}]
    assert rec["ligands"] == [{"resname": "AQ4", "chain": "A", "resi": 999, "n_heavy_atoms": 29}]
    assert rec["metals"] == [] and rec["n_atoms"] > 100
    assert not any(lg["resname"] == "HOH" for lg in rec["ligands"])
    assert client.get("/api/structures").json()[0]["structure_id"] == rec["structure_id"]
    f = client.get(f"/api/structures/{rec['structure_id']}/file")
    assert f.status_code == 200 and "AQ4" in f.text and f.headers["x-content-type-options"] == "nosniff"


def test_additives_and_metals_are_not_ligands(client):
    extra = [_het(9001, "S", "SO4", "A", 1001, 1.0, 2.0, 3.0, "S"), _het(9002, "O1", "SO4", "A", 1001, 1.5, 2.0, 3.0, "O"),
             _het(9003, "C1", "GOL", "A", 1002, 9.0, 9.0, 9.0, "C"), _het(9004, "MG", "MG", "A", 1003, 20.0, 20.0, 20.0, "MG"),
             _het(9005, "CL", "CL", "A", 1004, 30.0, 30.0, 30.0, "CL")]
    rec = _upload(client, _fixture_text(extra)).json()
    assert [lg["resname"] for lg in rec["ligands"]] == ["AQ4"]
    assert rec["metals"] == [{"resname": "MG", "element": "Mg", "chain": "A", "resi": 1003}]
    assert {a["resname"] for a in rec["additives"]} == {"SO4", "GOL", "CL"}
    assert any("additives" in w for w in rec["warnings"])


def test_mmcif_is_converted_to_pdb(client):
    cif = """data_test
loop_
_atom_site.group_PDB
_atom_site.id
_atom_site.type_symbol
_atom_site.label_atom_id
_atom_site.label_alt_id
_atom_site.label_comp_id
_atom_site.auth_asym_id
_atom_site.auth_seq_id
_atom_site.pdbx_PDB_ins_code
_atom_site.Cartn_x
_atom_site.Cartn_y
_atom_site.Cartn_z
_atom_site.occupancy
_atom_site.B_iso_or_equiv
_atom_site.auth_atom_id
_atom_site.auth_comp_id
_atom_site.pdbx_PDB_model_num
ATOM 1 N N . GLY A 5 ? 1.000 2.000 3.000 1.00 10.0 N GLY 1
ATOM 2 C CA . GLY A 5 ? 2.000 2.000 3.000 1.00 10.0 CA GLY 1
HETATM 3 C C1 . LIG A 101 ? 5.000 5.000 5.000 1.00 10.0 C1 LIG 1
HETATM 4 O "O5'" . LIG A 101 ? 6.000 5.000 5.000 1.00 10.0 "O5'" LIG 1
#
"""
    rec = _upload(client, cif, filename="model.cif").json()
    assert rec["format"] == "cif" and rec["runnable"] is True
    assert rec["ligands"] == [{"resname": "LIG", "chain": "A", "resi": 101, "n_heavy_atoms": 2}]
    text = client.get(f"/api/structures/{rec['structure_id']}/file").text
    assert "O5'" in text and text.count("HETATM") == 2


# ---------------------------------------------------------- input safety
def test_extension_size_and_content_rejection(client, monkeypatch):
    assert _upload(client, filename="evil.sh").status_code == 415
    assert _upload(client, filename="x.pdb.exe").status_code == 415
    assert _upload(client, "", filename="x.pdb").status_code == 422
    assert _upload(client, "HELLO\nWORLD\n", filename="x.pdb").status_code == 422
    assert _upload(client, "ATOM      1  N   GLY A   x      1.0 bad\n", filename="x.pdb").status_code == 422
    monkeypatch.setattr(uploads, "MAX_BYTES", 1000)
    assert _upload(client).status_code == 413


def test_path_safety(client, tmp_path):
    rec = _upload(client, filename="../../etc/passwd.pdb", name="../../x").json()
    assert "/" not in rec["name"] and ".." not in rec["name"].split("_")[0]
    stored = list((tmp_path / "uploads").iterdir())
    assert [p.name for p in stored] == [rec["structure_id"]]
    assert sorted(p.name for p in stored[0].iterdir()) == ["meta.json", "original.pdb", "structure.pdb"]
    for bad in ("..%2F..%2Fetc", "abc", "0" * 31 + "g", rec["structure_id"].upper()):
        assert client.get(f"/api/structures/{bad}/file").status_code in (400, 404)
    assert client.get(f"/api/structures/{'0' * 32}/file").status_code == 404
    with pytest.raises(uploads.UploadError):
        uploads.structure_dir("../" + rec["structure_id"])


# --------------------------------------------------------------- mutation
def test_mutate_validation(client):
    sid = _upload(client).json()["structure_id"]
    assert client.post(f"/api/structures/{sid}/mutate", json={"mutations": ["A:Y766M"]}).status_code == 422  # wild type is THR
    assert client.post(f"/api/structures/{sid}/mutate", json={"mutations": ["A:T766X"]}).status_code == 422
    assert client.post(f"/api/structures/{sid}/mutate", json={"mutations": ["A:T766T"]}).status_code == 422
    assert client.post(f"/api/structures/{sid}/mutate", json={"mutations": ["B:T766M"]}).status_code == 422
    assert client.post(f"/api/structures/{sid}/mutate", json={"mutations": ["A:T766M; rm -rf /"]}).status_code == 422
    assert client.post(f"/api/structures/{sid}/mutate", json={"mutations": []}).status_code == 422


def test_mutate_metal_coordinating_guard(client):
    x, y, z = _thr766_og1()
    sid = _upload(client, _fixture_text([_het(9004, "MG", "MG", "A", 1003, x + 2.1, y, z, "MG")])).json()["structure_id"]
    r = client.post(f"/api/structures/{sid}/mutate", json={"mutations": ["A:T766M"]})
    assert r.status_code == 422 and "coordinates metal" in r.json()["detail"]
    r = client.post(f"/api/structures/{sid}/mutate", json={"mutations": ["A:T766M"], "force": True})
    assert r.status_code == 200 and r.json()["applied"][0]["metal_coordinating"] is True


def test_mutate_removes_side_chain_beyond_cb_and_keeps_backbone(client):
    sid = _upload(client, name="EGFR wt").json()["structure_id"]
    r = client.post(f"/api/structures/{sid}/mutate", json={"mutations": ["A:T766M", "A:L768G"]})
    assert r.status_code == 200, r.text
    rec = r.json()
    assert rec["parent_id"] == sid and "no rotamer search" in rec["method"].lower()
    assert [(a["chain"], a["resi"], a["from"], a["to"]) for a in rec["applied"]] == [("A", 766, "T", "M"), ("A", 768, "L", "G")]
    atoms = uploads.read_atoms(client.get(f"/api/structures/{rec['structure_id']}/file").text)
    names = lambda n: sorted(a["name"] for a in atoms if a["resnum"] == n)  # noqa: E731
    assert {a["resname"] for a in atoms if a["resnum"] == 766} == {"MET"}
    assert names(766) == ["C", "CA", "CB", "N", "O"]  # OG1/CG2 gone, CB kept
    assert names(768) == ["C", "CA", "N", "O"]        # X->GLY drops CB too
    assert names(769) == sorted(a["name"] for a in uploads.read_atoms(FIXTURE.read_text()) if a["resnum"] == 769)
    assert rec["ligands"][0]["resname"] == "AQ4" and rec["name"].startswith("EGFR wt")


# ----------------------------------------------------------- SMILES lookup
def test_smiles_lookup_with_mocked_rcsb(tmp_path):
    doc = {"pdbx_chem_comp_descriptor": [
        {"type": "SMILES", "program": "ACDLabs", "descriptor": "wrong"},
        {"type": "SMILES_CANONICAL", "program": "CACTVS", "descriptor": AQ4_SMILES}],
        "rcsb_chem_comp_descriptor": {"SMILES": "fallback"}}
    seen = []

    def handler(request):
        seen.append(str(request.url))
        return httpx.Response(200, json=doc) if request.url.path.endswith("/AQ4") else httpx.Response(404)

    smiles, source = chemcomp.lookup_smiles("AQ4", transport=httpx.MockTransport(handler))
    assert smiles == AQ4_SMILES and "RCSB chemcomp AQ4" in source
    assert seen == ["https://data.rcsb.org/rest/v1/core/chemcomp/AQ4"]
    smiles2, source2 = chemcomp.lookup_smiles("AQ4", transport=httpx.MockTransport(handler))  # cache hit
    assert smiles2 == AQ4_SMILES and "[cached]" in source2 and len(seen) == 1
    with pytest.raises(LookupError, match="give the ligand SMILES"):
        chemcomp.lookup_smiles("ZZQ", transport=httpx.MockTransport(handler))
    with pytest.raises(LookupError):
        chemcomp.lookup_smiles("../A")

    def down(request):
        raise httpx.ConnectError("offline")
    with pytest.raises(LookupError, match="give the ligand SMILES"):
        chemcomp.lookup_smiles("STI", transport=httpx.MockTransport(down))


# --------------------------------------------------------- custom runs
def test_custom_run_sample_mode_is_proposal_only(client):
    sid = _upload(client, name="my EGFR").json()["structure_id"]
    mid = client.post(f"/api/structures/{sid}/mutate", json={"mutations": ["A:T766M"]}).json()["structure_id"]
    r = client.post("/run", json={"custom": {"structure_id": mid, "ligand_resname": "AQ4"}, "sample_mode": True})
    assert r.status_code == 200, r.text
    st = r.json()
    assert st["qm_escf_kcal"] is None and st["total_energy_kcal"] is None and st["qm_ok"] is False
    assert st["engine_label"] == custom.PROPOSAL_LABEL and st["chain"] == "A"
    assert st["custom"]["mutations"] == ["A:T766M"] and "RCSB chemcomp AQ4" in st["custom"]["smiles_source"]
    cards = json.loads(Path(st["cards"]).read_text())
    ids = [c["decision_id"] for c in cards]
    assert ids[:2] == ["DEC_CUSTOM_STRUCTURE", "DEC_MUTATION_A_T766M"] and "DEC_LIGAND_SMILES_SOURCE" in ids
    assert "your uploaded structure my EGFR" in cards[0]["choice"] and "no rotamer search" in cards[1]["choice"]
    engine = next(c for c in cards if c["decision_id"] == "DEC_CUSTOM_ENGINE")
    assert engine["choice"].startswith(custom.PROPOSAL_LABEL) and engine["evidence"]["qm_escf_kcal"] is None
    assert "DEC_CHAIN_A" in ids and "DEC_BINDING_MODE" not in ids
    report = Path(st["report"]).read_text()
    assert custom.PROPOSAL_LABEL in report and "your uploaded structure" in report and "ESCF `null`" in report


def test_custom_run_stream_and_errors(client):
    sid = _upload(client).json()["structure_id"]
    r = client.post("/api/run", json={"custom": {"structure_id": sid, "ligand_smiles": AQ4_SMILES}, "sample_mode": True})
    assert r.status_code == 200 and r.json()["custom"]["smiles_source"] == "user" and r.json()["custom"]["ligand_resname"] == "AQ4"
    events = []
    with client.stream("GET", f"/api/stream/{r.json()['stream_id']}") as s:
        name = None
        for line in s.iter_lines():
            if line.startswith("event: "):
                name = line[7:]
            elif line.startswith("data: "):
                events.append((name, json.loads(line[6:])))
                if name in ("result", "error"):
                    break
    assert events[-1][0] == "result" and events[-1][1]["stats"]["qm_escf_kcal"] is None
    assert events[-1][1]["stats"]["engine_label"] == custom.PROPOSAL_LABEL

    bad = [({"structure_id": "nope"}, 400), ({"structure_id": "0" * 32}, 404),
           ({"structure_id": sid, "ligand_resname": "HOH"}, 422), ({"structure_id": sid, "ligand_resname": "aq4;"}, 422),
           ({"structure_id": sid, "ligand_resname": "AQ4", "chain": "AB"}, 422),
           ({"structure_id": sid, "ligand_resname": "AQ4", "ligand_smiles": "C;rm -rf /"}, 422),
           ({"structure_id": sid, "ligand_resname": "AQ4", "ph": 20}, 422)]
    for spec, code in bad:
        assert client.post("/api/run", json={"custom": spec, "sample_mode": True}).status_code == code, spec


def test_metal_only_upload_is_refused_honestly(client):
    lines = [line for line in FIXTURE.read_text().splitlines() if "AQ4" not in line and line != "END"]
    text = "\n".join(lines + [_het(9004, "MG", "MG", "A", 1003, 1.0, 1.0, 1.0, "MG")]) + "\nEND\n"
    sid = _upload(client, text).json()["structure_id"]
    r = client.post("/api/run", json={"custom": {"structure_id": sid, "metal_resi": 1003}, "sample_mode": True})
    assert r.status_code == 422 and "QM-region proposal not supported yet" in r.json()["detail"]


def test_smiles_lookup_failure_asks_for_smiles(client, monkeypatch):
    def fail(r):
        raise LookupError(f"RCSB has no chemical component {r}; give the ligand SMILES")
    monkeypatch.setattr(server, "build_custom_case", lambda spec: custom.build_custom_case(spec, lookup=fail))
    sid = _upload(client).json()["structure_id"]
    r = client.post("/api/run", json={"custom": {"structure_id": sid, "ligand_resname": "AQ4"}, "sample_mode": True})
    assert r.status_code == 422 and "ligand_smiles" in r.json()["detail"]
