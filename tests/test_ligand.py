"""Ligand loop without Docker: prep.* and run_single_point monkeypatched with small dicts."""
import json
from pathlib import Path

import pytest

from activesite.agent import ligand as L
from activesite.agent import orchestrator
from activesite.chem import prep
from activesite.memory.hmem import MemoryStoreService

EGFR = Path("data/reference/egfr/1m17.pdb")
ABL = Path("data/reference/abl/2hyy.pdb")
pytestmark = pytest.mark.skipif(not (EGFR.exists() and ABL.exists()), reason="reference PDBs missing")


def _pose(shift=0.3, closest=3.1, contacts=None):
    return {"centroid_shift": shift, "rmsd": 0.5, "ligand_heavy_atoms": 29,
            "closest_protein_heavy_atom": {"atom": "MET769@N", "ligand_atom": "N1", "distance": closest},
            "contacts": contacts if contacts is not None else [{"ligand_atom": "N1", "partner": "MET769@N", "distance": 2.95}],
            "cutoff": 3.5, "numbering": "crystal", "coords": "min.rst7"}


@pytest.fixture
def fake_prep(monkeypatch):
    """Container stages replaced by small dicts; pure stages (chain, extract, amine, contacts) stay real."""
    state = {"overrides": [], "pose_min": _pose(), "pose_built": _pose(shift=0.1), "qm": {"ok": True}, "qm_calls": 0,
             "net_charge": 0}
    monkeypatch.setattr(prep, "prep_available", lambda image=prep.PREP_IMAGE: True)
    monkeypatch.setattr(L.sander, "docker_available", lambda image=None: True)
    monkeypatch.setattr(prep, "protonate", lambda work, ph: {
        "ph": ph, "pkas": {"HIS361": 6.9}, "pka_table": {("HIS", 361): 6.9}, "states": {361: "HID", 246: "HIE"},
        "gap_warnings": [], "seconds": 1.0, "log": "x"})
    monkeypatch.setattr(prep, "review_uncertain", lambda work, prot, ph, cation: {
        "overrides": list(state["overrides"]), "uncertain_his": ["HIS361 pKa 6.90"], "cation_atom": cation, "note": "sensitivity"})
    monkeypatch.setattr(prep, "ligand_parameters", lambda work, smiles, atom, cache=None: {
        "heavy_atoms": 29, "protonated": atom, "atoms_with_h": 52, "net_charge": state["net_charge"], "smiles": smiles,
        "charge_sum": float(state["net_charge"]), "charge_residual_spread": 0.0002, "ligand_atoms": 52, "cached": True,
        "cache_key": "abc", "seconds": 0.1, "mol2": "ligand.mol2", "frcmod": "ligand.frcmod"})
    monkeypatch.setattr(prep, "build_complex", lambda work, prot, overrides: {
        "parm7": str(Path(work) / "complex.parm7"), "rst7": str(Path(work) / "complex.rst7"), "total_charge": -1.0,
        "tleap_errors": 0, "tleap_warnings": 3, "renum": {}, "overrides_applied": [(o["resnum"], o["from"], o["to"]) for o in overrides],
        "seconds": 2.0})
    monkeypatch.setattr(prep, "minimise", lambda work, steps=500: {
        "first": {"nstep": 1, "energy": -1000.0, "rms": 5.0, "gmax": 80.0}, "last": {"nstep": steps, "energy": -1200.0, "rms": 0.3, "gmax": 4.2},
        "steps": steps, "seconds": 3.0, "rst7": str(Path(work) / "min.rst7")})
    monkeypatch.setattr(prep, "built_pose", lambda work, coords, renum: state["pose_min"] if str(coords).endswith("min.rst7") else state["pose_built"])

    def fake_sp(parm7, coords, mask, charge, workdir, theory="PM6", timeout_s=300, solvent="pme", image=None):
        state["qm_calls"] += 1
        assert mask == ":LIG" and solvent == "gb" and str(coords).endswith("min.rst7")
        if state["qm"]["ok"]:
            return {"ok": True, "qm_escf_kcal": -321.0, "total_energy_kcal": -4567.0, "link_atoms": 0, "odd_electrons": None,
                    "errors": [], "wall_time_s": 12.0, "exit_code": 0, "qm_resp_charge_sum": float(charge), "workdir": str(workdir)}
        return {"ok": False, "qm_escf_kcal": None, "total_energy_kcal": None, "link_atoms": 0, "odd_electrons": None,
                "errors": ["SCF failed"], "wall_time_s": 1.0, "exit_code": 1, "workdir": str(workdir)}

    monkeypatch.setattr(L, "run_single_point", fake_sp)
    return state


def _run(tmp_path, case_id, **kw):
    return orchestrator.run_case(case_id, hmem_db=tmp_path / "h.sqlite", ledger_path=tmp_path / "l.jsonl",
                                 workroot=tmp_path / "runs", log_dir=tmp_path / "logs", sample_mode=False, echo=False, **kw)


def test_routing_and_cards_egfr(tmp_path, fake_prep):
    st = _run(tmp_path, "egfr_erlotinib")
    assert st["kind"] == "ligand" and st["qm_ok"] is True and st["blocked"] == [] and fake_prep["qm_calls"] == 1
    assert st["chain"] == "A" and st["qmcharge"] == 0 and st["qm_escf_kcal"] == -321.0
    cards = {c.decision_id: c for c in st["_cards"]}
    assert "DEC_CHAIN_A" in cards and cards["DEC_CHAIN_A"].evidence["source"].startswith("REMARK 465/470")
    assert "DEC_PROTONATION_PDB2PQR" in cards and "DEC_LIGAND_NEUTRAL" in cards
    assert "DEC_LIGAND_PARAMETERS" in cards and "(cached)" in cards["DEC_LIGAND_PARAMETERS"].choice
    assert "DEC_QM_REGION_LIGAND" in cards and "DEC_SOLVENT_GB" in cards
    for name in ("ligand_charge_sum", "pocket_built", "pocket_min", "complex_integer_charge", "minimisation_relaxed"):
        assert f"DEC_CHECK_{name.upper()}" in cards and cards[f"DEC_CHECK_{name.upper()}"].choice.startswith("passed")
    assert cards["DEC_BINDING_MODE"].choice == "1/1 published contacts present" and "MET769 at 2.95" in cards["DEC_BINDING_MODE"].rationale
    assert cards["DEC_NEGATIVE_CONTROL_THR766"].choice.endswith("True")
    assert not any(k.startswith("DEC_HIS_OVERRIDE") for k in cards) and "DEC_STRUCTURE_SOURCE" not in cards
    assert st["validation"]["recovered"] == {"MET769": 2.95} and st["validation"]["expected_absent"] == {"THR766": True}
    agents = {json.loads(l)["agent_name"] for l in Path(st["trace"]).read_text().splitlines()}
    assert {"Planner", "DataScout", "LigandSetup", "LigandCritic", "Runner", "Explainer", "Orchestrator"} <= agents
    assert "converged" in Path(st["report"]).read_text()
    assert MemoryStoreService(tmp_path / "h.sqlite", tmp_path / "l.jsonl").all() == []   # no overrides -> nothing to remember


def test_pocket_failure_blocks_qmmm(tmp_path, fake_prep):
    fake_prep["pose_min"] = _pose(shift=1.8, closest=5.2)
    st = _run(tmp_path, "egfr_erlotinib")
    assert st["blocked"] == ["pocket_min"] and st["qm_ok"] is False and fake_prep["qm_calls"] == 0
    assert st["qm_escf_kcal"] is None and "blocked by pocket_min" in st["errors"][0]
    rows = [json.loads(l) for l in Path(st["trace"]).read_text().splitlines()]
    assert any(r["action"] == "blocked" and r["status"] == "error" for r in rows)
    assert "FAILED" in Path(st["report"]).read_text() and "`null`" in Path(st["report"]).read_text()
    cards = {c.decision_id: c for c in st["_cards"]}
    assert cards["DEC_CHECK_POCKET_MIN"].choice.startswith("flagged") and cards["DEC_CHECK_POCKET_MIN"].confidence == 0.0


def test_memory_write_conditions_abl(tmp_path, fake_prep):
    fake_prep["net_charge"] = 1
    fake_prep["overrides"] = [{"resnum": 361, "from": "HID", "to": "HIE", "pka": 6.9, "ph": 7.4,
                               "d_ND1_cation": 4.1, "d_NE2_cation": 6.0, "evidence": "HIS361: ND1 4.10 Å from N51 -> HIE"}]
    store = MemoryStoreService(tmp_path / "h.sqlite", tmp_path / "l.jsonl")

    # 1. QM failed -> nothing remembered
    fake_prep["qm"] = {"ok": False}
    st = _run(tmp_path, "abl_imatinib_a")
    assert st["qm_ok"] is False and st["memory_written"] is None and store.all() == []
    assert st["qmcharge"] == 1 and st["chain"] in ("A", "B", "C", "D")
    cards = {c.decision_id: c for c in st["_cards"]}
    assert "DEC_HIS_OVERRIDE_361" in cards and "sensitivity run advised" in cards["DEC_HIS_OVERRIDE_361"].choice
    assert cards["DEC_HIS_OVERRIDE_361"].confidence < 0.5
    assert any(k.startswith("DEC_LIGAND_PROTONATION_N") for k in cards)

    # 2. QM ok, override present, nothing recalled -> one working-layer memory per override
    fake_prep["qm"] = {"ok": True}
    st = _run(tmp_path, "abl_imatinib_a")
    assert st["qm_ok"] is True and st["memory_used"] is False and len(st["memory_written"]) == 1
    mems = store.all()
    assert len(mems) == 1 and mems[0]["layer"] == "working" and mems[0]["confidence"] == 0.7
    assert set(mems[0]["tags"]) == {"protonation", "his-near-cation"} and mems[0]["extra"]["rule"] == "his_near_cation_neutral"

    # 3. Same situation with the memory present -> recalled, not re-written
    st = _run(tmp_path, "abl_imatinib_a")
    assert st["memory_used"] is True and st["memory_written"] is None and len(store.all()) == 1
    assert [e["action"] for e in store.read_ledger()] == ["create", "read"]


def test_requested_chain_and_sample_mode(tmp_path, fake_prep):
    case = json.loads(Path("cases/abl_imatinib_a.json").read_text())
    case["chain"] = "C"
    st = orchestrator.run_case(case, hmem_db=tmp_path / "h.sqlite", ledger_path=tmp_path / "l.jsonl",
                               workroot=tmp_path / "runs", log_dir=tmp_path / "logs", sample_mode=False, echo=False)
    assert st["chain"] == "C" and st["_setup"]["chain_source"] == "requested"
    st = orchestrator.run_case("egfr_erlotinib", hmem_db=tmp_path / "h2.sqlite", ledger_path=tmp_path / "l2.jsonl",
                               workroot=tmp_path / "runs2", log_dir=tmp_path / "logs2", sample_mode=True, echo=False)
    assert st["blocked"] == ["prep_available"] and "SAMPLE_MODE" in st["prep_skipped"] and st["qm_ok"] is False
    assert fake_prep["qm_calls"] == 1  # only the first run reached QM/MM
