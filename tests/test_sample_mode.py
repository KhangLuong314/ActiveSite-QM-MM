"""Sample mode replays cached engine output and cached preparation; a missing cache is reported, never faked."""
import json
import shutil
from pathlib import Path

import pytest

from activesite.agent import orchestrator
from activesite.chem import prep
from activesite.sample import CACHED_LABEL, cached_engine_result

FIX = Path(__file__).parent / "fixtures"
REF = Path("data/reference/qmmm_dft")
pytestmark = pytest.mark.skipif(not (REF / "step3_pbcsetup.parm7").exists(), reason="reference files missing")


def _write_sample(root: Path, case: str, charge: int, fixture: str, attempt: int | None = None):
    text = (FIX / fixture).read_text().replace("qmcharge=1,", f"qmcharge={charge},").replace("qmcharge=0,", f"qmcharge={charge},")
    for d in ([root / case / f"charge{charge:+d}"] + ([root / case / f"attempt{attempt}"] if attempt is not None else [])):
        d.mkdir(parents=True, exist_ok=True)
        (d / "sp.out").write_text(text)


def test_missing_cache_is_reported(tmp_path, monkeypatch):
    monkeypatch.setenv("ACTIVESITE_SAMPLE_DIR", str(tmp_path / "empty"))
    r = cached_engine_result("ippoi_site_a", 0, 0)
    assert r["ok"] is False and r["cached"] is False and r["qm_escf_kcal"] is None
    assert "no cached sample output for qmcharge +0" in r["errors"][0]


def test_cached_output_must_match_requested_charge(tmp_path, monkeypatch):
    monkeypatch.setenv("ACTIVESITE_SAMPLE_DIR", str(tmp_path))
    (tmp_path / "ippoi_site_b" / "attempt0").mkdir(parents=True)
    (tmp_path / "ippoi_site_b" / "attempt0" / "sp.out").write_text((FIX / "sander_ok.out").read_text())  # echoes qmcharge=1
    assert cached_engine_result("ippoi_site_b", 0, 0)["cached"] is False       # charge 0 requested, cache is for +1
    assert cached_engine_result("ippoi_site_b", 0, 1)["cached"] is True


def test_metal_sample_mode_cold_then_warm(tmp_path, monkeypatch):
    root = tmp_path / "sample"
    monkeypatch.setenv("ACTIVESITE_SAMPLE_DIR", str(root))
    _write_sample(root, "ippoi_site_a", 0, "sander_odd.out", attempt=0)
    _write_sample(root, "ippoi_site_a", 1, "sander_ok.out", attempt=1)
    _write_sample(root, "ippoi_site_b", 1, "sander_ok.out")
    kw = dict(hmem_db=tmp_path / "h.sqlite", ledger_path=tmp_path / "l.jsonl", workroot=tmp_path / "runs", log_dir=tmp_path / "logs",
              sample_mode=True, echo=False)
    cold = orchestrator.run_case("ippoi_site_a", **kw)
    assert cold["engine_label"] == CACHED_LABEL and cold["qm_ok"] is True and cold["retries"] == 1
    assert cold["qmcharge"] == 1 and cold["memory_written"] and cold["qm_escf_kcal"] == pytest.approx(-1442.3127)
    rows = [json.loads(l) for l in Path(cold["trace"]).read_text().splitlines()]
    assert sum(1 for r in rows if r["action"] == "cached_engine_output") == 2
    report = Path(cold["report"]).read_text()
    assert "converged" in report
    warm = orchestrator.run_case("ippoi_site_b", **kw)
    assert warm["engine_label"] == CACHED_LABEL and warm["retries"] == 0 and warm["memory_used"] is True


def test_metal_sample_mode_without_cache_is_honest(tmp_path, monkeypatch):
    monkeypatch.setenv("ACTIVESITE_SAMPLE_DIR", str(tmp_path / "none"))
    st = orchestrator.run_case("ippoi_site_a", hmem_db=tmp_path / "h.sqlite", ledger_path=tmp_path / "l.jsonl",
                               workroot=tmp_path / "runs", log_dir=tmp_path / "logs", sample_mode=True, echo=False)
    assert st["engine_label"] == "engine unavailable" and st["qm_ok"] is False and st["retries"] == 0
    assert "SAMPLE_MODE" in st["errors"][0] and "no cached sample output" in st["errors"][0]


def test_ligand_sample_mode_uses_cached_prep(tmp_path, monkeypatch):
    root = tmp_path / "sample"
    monkeypatch.setenv("ACTIVESITE_SAMPLE_DIR", str(root))
    monkeypatch.setattr(prep, "prep_available", lambda image=prep.PREP_IMAGE: False)
    prep_dir = root / "egfr_erlotinib" / "prep"
    prep_dir.mkdir(parents=True)
    for name in ("complex.parm7", "min.rst7", "pdb2pqr.log", "ligand.mol2"):
        (prep_dir / name).write_text("placeholder bytes from a real run would live here\n")
    pose = {"centroid_shift": 0.4, "rmsd": 0.6, "ligand_heavy_atoms": 29,
            "closest_protein_heavy_atom": {"atom": "MET769@N", "ligand_atom": "N1", "distance": 3.0},
            "contacts": [{"ligand_atom": "N1", "partner": "MET769@N", "distance": 2.9}], "cutoff": 3.5, "numbering": "crystal", "coords": "x"}
    (prep_dir / "prep.json").write_text(json.dumps({
        "charge": 0, "overrides": [], "protonation": {"ph": 7.4, "pkas": {}, "states": {}, "gap_warnings": [], "seconds": 1.0},
        "his_review": {"uncertain_his": [], "overrides": []},
        "ligand_parameters": {"heavy_atoms": 29, "atoms_with_h": 52, "net_charge": 0, "charge_sum": 0.0, "charge_residual_spread": 0.0,
                              "ligand_atoms": 52, "cached": True, "cache_key": "k", "seconds": 0.1},
        "complex": {"total_charge": -1.0, "tleap_errors": 0, "tleap_warnings": 1, "renum": {}, "overrides_applied": [], "seconds": 1.0},
        "minimisation": {"first": {"nstep": 1, "energy": -1.0, "rms": 1.0, "gmax": 50.0}, "last": {"nstep": 500, "energy": -2.0, "rms": 0.1, "gmax": 3.0},
                         "steps": 500, "seconds": 2.0},
        "pose_built": pose, "pose_min": pose}))
    _write_sample(root, "egfr_erlotinib", 0, "sander_ok.out")
    st = orchestrator.run_case("egfr_erlotinib", hmem_db=tmp_path / "h.sqlite", ledger_path=tmp_path / "l.jsonl",
                               workroot=tmp_path / "runs", log_dir=tmp_path / "logs", sample_mode=True, echo=False)
    assert st["engine_label"] == CACHED_LABEL and st["qm_ok"] is True and st["blocked"] == []
    assert st["prep_skipped"] is None and st["validation"]["recovered"] == {"MET769": 2.9}
    work = Path(st["_setup"]["work"])
    assert (work / "complex.parm7").exists() and st["_setup"]["complex"]["parm7"] == str(work / "complex.parm7")
    assert CACHED_LABEL in Path(st["report"]).read_text() or "cached" in Path(st["trace"]).read_text()
