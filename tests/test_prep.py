"""Tests for activesite.chem.prep: pure parts without Docker, full preparation only on a Docker host."""
import json
import os
from pathlib import Path

import pytest

from activesite.chem import prep
from activesite.chem.prep import (
    HBOND,
    choose_chain,
    extract,
    finalise_mol2,
    ligand_protonation_site,
    parse_propka_summary,
    parse_renum,
    polar_contacts,
    prep_available,
    review_uncertain,
)

EGFR = Path("data/reference/egfr/1m17.pdb")
ABL = Path("data/reference/abl/2hyy.pdb")
FIX = Path(__file__).parent / "fixtures"
needs_pdbs = pytest.mark.skipif(not (EGFR.exists() and ABL.exists()), reason="reference PDBs missing")


# ------------------------------------------------------------------ no Docker
@needs_pdbs
def test_choose_chain_egfr():
    r = choose_chain(EGFR, "AQ4")
    assert r["chain"] == "A"
    assert len(r["table"]) == 1
    row = r["table"][0]
    assert row["ligand_atoms"] == 29 and row["pocket_residues"] > 20
    assert row["missing_residues"] > 0            # 1M17 lists missing termini
    assert row["gaps_adjacent_to_pocket"] == 0


@needs_pdbs
def test_choose_chain_abl():
    r = choose_chain(ABL, "STI")
    assert len(r["table"]) == 4
    chains = [row["chain"] for row in r["table"]]
    assert chains == ["A", "B", "C", "D"]
    assert r["chain"] in chains
    best = next(row for row in r["table"] if row["chain"] == r["chain"])
    assert all(best["score"] <= row["score"] for row in r["table"])
    assert all(row["ligand_atoms"] == 37 for row in r["table"])


@needs_pdbs
def test_extract_and_ligand_site_abl(tmp_path):
    chain = choose_chain(ABL, "STI")["chain"]
    ext = extract(ABL, chain, "STI", tmp_path)
    assert ext["ligand_atoms"] == 37 and ext["protein_atoms"] > 2000
    assert (tmp_path / "protein.pdb").exists() and (tmp_path / "ligand.pdb").exists()
    site = ligand_protonation_site(tmp_path)
    assert site is not None
    assert site["atom"] in ("N51", "N48")           # piperazine nitrogens
    assert site["contacts"][0]["distance"] < HBOND
    assert site["contacts"][0]["partner"].endswith("@O")
    assert any(e["tertiary_amine"] for e in site["checked"])
    assert "Å" in site["evidence"] and site["atom"] in site["evidence"]
    assert len([e for e in site["checked"] if e["tertiary_amine"]]) == 2


@needs_pdbs
def test_ligand_site_egfr_is_none(tmp_path):
    extract(EGFR, "A", "AQ4", tmp_path)
    assert ligand_protonation_site(tmp_path) is None
    pc = polar_contacts(tmp_path)
    assert any(c["partner"].startswith("MET769") and c["distance"] < HBOND for c in pc["contacts"])


def test_finalise_mol2_ok():
    mol2 = (FIX / "methanol.mol2").read_text()
    sdf = (FIX / "methanol.sdf").read_text()
    out, info = finalise_mol2(mol2, sdf, 0)
    assert info["ligand_atoms"] == 6
    assert abs(info["charge_sum"]) < 1e-6 and abs(info["charge_residual_spread"]) < 1e-6
    # coordinates come from THIS run's sdf, charges/types from the cached mol2
    atom1 = [l for l in out.splitlines() if l.split()[:2] == ["1", "C1"]][0].split()
    assert float(atom1[2]) == pytest.approx(0.1000) and atom1[5] == "c3"
    assert "@<TRIPOS>BOND" in out and "@<TRIPOS>SUBSTRUCTURE" in out


def test_finalise_mol2_spreads_small_residual():
    mol2 = (FIX / "methanol.mol2").read_text().replace("0.395600", "0.399600")   # +0.004 e
    out, info = finalise_mol2(mol2, (FIX / "methanol.sdf").read_text(), 0)
    assert info["charge_residual_spread"] == pytest.approx(-0.004)
    assert abs(info["charge_sum"]) < 1e-6


def test_finalise_mol2_refuses_residual_and_order():
    mol2 = (FIX / "methanol.mol2").read_text()
    sdf = (FIX / "methanol.sdf").read_text()
    with pytest.raises(ValueError, match="residual"):
        finalise_mol2(mol2.replace("0.395600", "0.445600"), sdf, 0)         # +0.05 e
    swapped = sdf.replace("    0.1000    0.0000    0.0000 C ", "    0.1000    0.0000    0.0000 O ", 1) \
                 .replace("    1.5300    0.0000    0.0000 O ", "    1.5300    0.0000    0.0000 C ", 1)
    with pytest.raises(ValueError, match="element order"):
        finalise_mol2(mol2, swapped, 0)
    with pytest.raises(ValueError, match="atom count"):
        finalise_mol2(mol2, sdf.replace("  6  5  0", "  5  5  0"), 0)


def test_parse_propka_summary_and_renum(tmp_path):
    text = """
--------------------------------------------------------------------------------------------------------
SUMMARY OF THIS PREDICTION
       Group      pKa  model-pKa   ligand atom-type
   ASP   9 A     3.33       3.80
   HIS 361 A     6.91       6.50
   LYS 271 A    10.12      10.50
   N+  229 A     7.86       8.00
--------------------------------------------------------------------------------------------------------
Free energy of   folding (kcal/mol) as a function of pH (using neutral reference)
"""
    pk = parse_propka_summary(text)
    assert pk[("HIS", 361)] == 6.91 and pk[("ASP", 9)] == 3.33 and ("N+", 229) in pk
    renum = tmp_path / "protein_amber_renum.txt"
    renum.write_text("HIS A 361      HIE   133\nMET A 318      MET    90\n")
    assert parse_renum(renum) == {361: 133, 318: 90}


@needs_pdbs
def test_review_uncertain_from_geometry(tmp_path):
    chain = choose_chain(ABL, "STI")["chain"]
    extract(ABL, chain, "STI", tmp_path)
    site = ligand_protonation_site(tmp_path)
    # Synthetic PROPKA result: His361 uncertain (pKa 6.9 at pH 7.4) and one far-away His.
    prot = {"pka_table": {("HIS", 361): 6.9, ("HIS", 246): 6.8}, "states": {361: "HID", 246: "HIE"}}
    r = review_uncertain(tmp_path, prot, 7.4, site["atom"])
    assert r["uncertain_his"] == ["HIS361 pKa 6.90", "HIS246 pKa 6.80"]
    assert "sensitivity" in r["note"]
    for o in r["overrides"]:
        assert o["to"] in ("HID", "HIE")
        nearer = "ND1" if o["d_ND1_cation"] < o["d_NE2_cation"] else "NE2"
        assert (o["to"] == "HIE") == (nearer == "ND1")
        assert min(o["d_ND1_cation"], o["d_NE2_cation"]) <= prep.CATION_RANGE
        assert "Å" in o["evidence"]
    assert review_uncertain(tmp_path, prot, 7.4, None)["overrides"] == []


def test_dock_command_shape(monkeypatch, tmp_path):
    seen = {}

    def fake_run(args, stdout, stderr, text, timeout):
        seen["args"] = args
        seen["timeout"] = timeout
        import subprocess
        return subprocess.CompletedProcess(args, 0, stdout="ok\n")

    monkeypatch.setattr(prep.subprocess, "run", fake_run)
    code, out, secs = prep.dock(tmp_path, ["pdb2pqr", "--ff=AMBER"], env="prep", timeout=5)
    assert code == 0 and out == "ok\n" and secs >= 0 and seen["timeout"] == 5
    assert seen["args"] == ["docker", "run", "--rm", "-v", f"{tmp_path.resolve()}:/work", prep.PREP_IMAGE,
                            "micromamba", "run", "-n", "prep", "pdb2pqr", "--ff=AMBER"]
    prep.dock(tmp_path, ["tleap", "-f", "tleap.in"])
    assert seen["args"][5:] == [prep.PREP_IMAGE, "tleap", "-f", "tleap.in"]


def test_ligand_rdkit_script_is_standalone():
    src = (Path("activesite/chem/ligand_rdkit.py")).read_text()
    assert "import activesite" not in src and "from activesite" not in src


# --------------------------------------------------------------------- Docker
PREP_READY = prep_available() and EGFR.exists() and ABL.exists()


def _case(name):
    return json.loads(Path(f"cases/{name}.json").read_text())


@pytest.mark.slow
@pytest.mark.skipif(not PREP_READY, reason="activesite-prep:at26 image not available")
def test_full_prep_egfr_erlotinib(tmp_path):
    case = _case("egfr_erlotinib")
    r = prep.prepare_complex(EGFR, "AQ4", case["ligand_smiles"], 7.4, tmp_path / "egfr", steps=500,
                             cache=tmp_path / "cache")
    assert Path(r["parm7"]).exists() and Path(r["rst7"]).exists()
    assert r["ligand_site"] is None and r["ligand_parameters"]["net_charge"] == 0
    assert r["minimisation"]["last"]["gmax"] < 10
    assert r["pose"]["centroid_shift"] < 1.0
    assert any(c["partner"].startswith("MET769") and c["distance"] < HBOND for c in r["pose"]["contacts"])
    assert set(os.listdir(tmp_path)) <= {"egfr", "cache"}


@pytest.mark.slow
@pytest.mark.skipif(not PREP_READY, reason="activesite-prep:at26 image not available")
def test_full_prep_abl_imatinib(tmp_path):
    case = _case("abl_imatinib_a")
    r = prep.prepare_complex(ABL, "STI", case["ligand_smiles"], 7.4, tmp_path / "abl", steps=500,
                             cache=tmp_path / "cache")
    assert Path(r["parm7"]).exists() and Path(r["rst7"]).exists()
    assert r["ligand_site"]["atom"] in ("N51", "N48") and r["ligand_parameters"]["net_charge"] == 1
    assert r["minimisation"]["last"]["gmax"] < 10
    assert r["pose"]["centroid_shift"] < 1.0


def test_tleap_template_combines_units_with_single_braces():
    """tleap reads ``combine {PROT LIG}``; doubled braces make a list-of-lists, the combine is skipped and
    ``charge COMPLEX`` fails on a String (seen in a real EGFR run, 2026-10-22)."""
    from activesite.chem import prep as prep_mod
    assert "COMPLEX = combine {PROT LIG}" in prep_mod.TLEAP_TEMPLATE
    assert "{{" not in prep_mod.TLEAP_TEMPLATE and "}}" not in prep_mod.TLEAP_TEMPLATE
