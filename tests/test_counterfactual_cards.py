"""Counterfactual faithfulness tests for Decision Cards (Track 02: "explain why" must be faithful).

Each test flips ONE piece of evidence behind a decision and asserts that the card's choice and evidence flip with
it. Baseline numbers are the ones the agent produces on the unmodified inputs (samples/*/cards.json,
data/sample/abl_imatinib_a/prep/prep.json); every perturbation is made on a copy (tmp_path or an in-memory copy of
the coordinates), never on data/reference/.

1. QM charge     engine output order (odd-electron first vs OK first) -> DEC_QMCHARGE rejection/retry or none.
2. Mg first shell Mg-bound waters 398-400 removed from the QM atoms (function level: Setup output -> Critic.precheck),
                 and moved out of the first shell (in-memory coordinates -> qmregion.propose).
3. Ligand site   ILE360 backbone O moved away from the piperazine N51 (or next to N48) -> DEC_LIGAND_* card.
4. Chain choice  REMARK 465/470 lines of chain D deleted -> DEC_CHAIN_D with the edited evidence table.
5. His override  PROPKA pKa of HIS361 moved outside the 1-unit window -> DEC_HIS_OVERRIDE_361 disappears.
"""
from __future__ import annotations

import copy
import json
import re
import subprocess
from pathlib import Path

import numpy as np
import pytest

from activesite.agent import orchestrator
from activesite.agent.core import Critic, Explainer, Setup
from activesite.agent.ligand import LigandSetup, ligand_cards
from activesite.chem import prep, sander
from activesite.chem.qmregion import FIRST_SHELL, propose
from activesite.chem.system import MolSystem

FIX = Path(__file__).parent / "fixtures"
REF = Path("data/reference/qmmm_dft")
PDB = Path("data/reference/abl/2hyy.pdb")
ABL_CACHE = Path("data/sample/abl_imatinib_a/prep/prep.json")
IPPOI_A = json.loads(Path("cases/ippoi_site_a.json").read_text())
ABL_A = json.loads(Path("cases/abl_imatinib_a.json").read_text())
MG_WATERS = (398, 399, 400)

needs_metal = pytest.mark.skipif(not (REF / "step3_pbcsetup.parm7").exists(), reason="reference files missing")
needs_abl = pytest.mark.skipif(not PDB.exists(), reason="2hyy.pdb missing")


def _card(cards, prefix):
    hits = [c for c in cards if c["decision_id"].startswith(prefix)] if cards and isinstance(cards[0], dict) else \
        [c.model_dump() for c in cards if c.decision_id.startswith(prefix)]
    assert len(hits) <= 1, [c["decision_id"] for c in hits]
    return hits[0] if hits else None


# ---------------------------------------------------------------- 1. QM charge
class FakeEngine:
    """subprocess.run stand-in: each `docker run` writes the next sp.out text; docker info/inspect succeed."""

    def __init__(self, texts):
        self.texts = list(texts)
        self.runs = 0

    def __call__(self, cmd, capture_output=True, text=True, timeout=None, **kw):
        if cmd[:2] == ["docker", "run"]:
            work = Path(cmd[cmd.index("-v", cmd.index("-v") + 1) + 1].split(":")[0])
            out = self.texts.pop(0)
            (work / "sp.out").write_text(out)
            self.runs += 1
            return subprocess.CompletedProcess(cmd, 0 if "odd number" not in out else 1, stdout="", stderr="")
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")


def _run_metal(tmp_path, monkeypatch, texts):
    fake = FakeEngine(texts)
    monkeypatch.setattr(sander.subprocess, "run", fake)
    monkeypatch.setattr(sander.shutil, "which", lambda name: "/usr/bin/docker")
    st = orchestrator.run_case("ippoi_site_a", hmem_db=tmp_path / "h.sqlite", ledger_path=tmp_path / "l.jsonl",
                               workroot=tmp_path / "runs", log_dir=tmp_path / "logs", sample_mode=False, echo=False)
    return st, json.loads(Path(st["cards"]).read_text()), fake


@needs_metal
def test_qmcharge_card_follows_engine_outcome(tmp_path, monkeypatch):
    odd, ok = (FIX / "sander_odd.out").read_text(), (FIX / "sander_ok.out").read_text()

    # factual: textbook charge +0 gives an odd electron count, Critic retries at the MM-sum integer +1
    st_a, cards_a, eng_a = _run_metal(tmp_path / "a", monkeypatch, [odd, ok])
    q_a = _card(cards_a, "DEC_QMCHARGE")
    assert st_a["retries"] == 1 and eng_a.runs == 2
    assert q_a["choice"].startswith("qmcharge +1")
    assert len(q_a["alternatives"]) == 1 and q_a["alternatives"][0]["name"].startswith("qmcharge +0")
    assert "odd" in q_a["alternatives"][0]["rejected_reason"]
    assert "First attempt rejected" in q_a["rationale"]
    assert [a["ok"] for a in q_a["evidence"]["attempts"]] == [False, True]
    assert q_a["evidence"]["attempts"][0]["odd_electrons"] == 203
    assert q_a["evidence"]["source"] == "sander validation + H-MEM"

    # counterfactual: the engine accepts the first (textbook +0) charge. Copy of the OK output, echo set to +0.
    ok0 = ok.replace("qmcharge=+1,", "qmcharge=+0,").replace("qmcharge=1,", "qmcharge=0,")
    st_b, cards_b, eng_b = _run_metal(tmp_path / "b", monkeypatch, [ok0])
    q_b = _card(cards_b, "DEC_QMCHARGE")
    assert st_b["retries"] == 0 and eng_b.runs == 1 and st_b["memory_written"] is None
    assert q_b["choice"].startswith("qmcharge +0")
    assert q_b["alternatives"] == []
    assert "rejected" not in q_b["rationale"].lower()
    assert q_b["evidence"]["attempts"] == [{"attempt": 0, "charge": 0, "ok": True, "odd_electrons": None}]
    assert q_b["evidence"]["source"] == "MM partial-charge sum"
    # the evidence the charge card cites for the geometry did not change (same region, same MM sum)
    for k in ("mm_partial_sum", "nearest_int", "formal_sum"):
        assert q_a["evidence"][k] == q_b["evidence"][k]


# ----------------------------------------------------------- 2. Mg first shell
@pytest.fixture(scope="module")
def ippoi():
    if not (REF / "step3_pbcsetup.parm7").exists():
        pytest.skip("reference files missing")
    return MolSystem(IPPOI_A["parm7"], IPPOI_A["coords"])


def _metal_cards(system, setup, checks):
    attempts = [{"attempt": 0, "setup": setup, "result": {"ok": True}}]
    return Explainer().cards(system, IPPOI_A, setup, checks, attempts, {}, {}, "PM6")


@needs_metal
def test_first_shell_check_fails_when_mg_waters_are_dropped(ippoi):
    """Function-level: Setup's QM atoms minus the three Mg-bound waters -> Critic.precheck must flag it."""
    setup = Setup(None, None, "cf").build(ippoi, IPPOI_A)
    base = {c["name"]: c for c in Critic(None, None, "cf").precheck(ippoi, IPPOI_A, setup, {})}
    assert base["first_shell_in_qm"]["passed"] and base["first_shell_in_qm"]["margin"] == 1.0
    assert "7 heavy atoms" in base["first_shell_in_qm"]["detail"] and "7 in QM" in base["first_shell_in_qm"]["detail"]

    water_atoms = {a.idx for r in MG_WATERS for a in ippoi.s.residues[r - 1].atoms}
    assert {ippoi.s.residues[r - 1].name for r in MG_WATERS} == {"WAT"}
    cut = dict(setup, atoms=[i for i in setup["atoms"] if i not in water_atoms])
    checks = Critic(None, None, "cf").precheck(ippoi, IPPOI_A, cut, {})
    fs = next(c for c in checks if c["name"] == "first_shell_in_qm")
    assert fs["passed"] is False
    assert fs["margin"] == round(4 / 7, 3)
    assert "7 heavy atoms" in fs["detail"] and "4 in QM" in fs["detail"]
    for r in MG_WATERS:
        assert f"WAT{r}@O" in fs["detail"]

    card = _card(_metal_cards(ippoi, cut, checks), "DEC_CHECK_FIRST_SHELL_IN_QM")
    assert card["choice"].startswith("flagged:") and card["confidence"] == 0.0
    assert card["evidence"]["passed"] is False and card["evidence"]["margin"] == round(4 / 7, 3)


@needs_metal
def test_region_cards_follow_mg_water_geometry(ippoi):
    """Move the three Mg-bound waters 6 Å further from the Mg (in-memory copy): their first-shell cards must go."""
    setup = Setup(None, None, "cf").build(ippoi, IPPOI_A)
    base_ids = {c.decision_id for c in _metal_cards(ippoi, setup, [])}
    for r in MG_WATERS:
        assert any(i.endswith(f"FIRST_SHELL_WAT{r}") for i in base_ids)

    moved = copy.copy(ippoi)
    moved.xyz = ippoi.xyz.copy()
    mg = ippoi.s.residues[IPPOI_A["metal_resid"] - 1].atoms[0].idx
    for r in MG_WATERS:
        res = ippoi.s.residues[r - 1]
        o = next(a.idx for a in res.atoms if a.name == "O")
        u = (ippoi.xyz[o] - ippoi.xyz[mg]) / np.linalg.norm(ippoi.xyz[o] - ippoi.xyz[mg])
        for a in res.atoms:
            moved.xyz[a.idx] = ippoi.xyz[a.idx] + 6.0 * u
    heavy_shell = lambda s: [j for j in s.within(mg, FIRST_SHELL) if s.atoms[j].atomic_number > 1]  # noqa: E731
    assert len(heavy_shell(ippoi)) == 7 and len(heavy_shell(moved)) == 4  # the copy moved; the original did not

    prop = propose(moved, IPPOI_A["metal_resid"])
    shell = [c.residue for c in prop.choices if c.role == "first_shell"]
    assert not any(s.startswith("WAT") for s in shell)
    assert set(shell) == {"DG14", "ASN322", "DA13"}
    water_atoms = {a.idx for r in MG_WATERS for a in ippoi.s.residues[r - 1].atoms}
    assert not water_atoms & set(prop.atoms) and water_atoms <= set(setup["atoms"])

    setup_m = Setup(None, None, "cf").build(moved, IPPOI_A)
    checks_m = Critic(None, None, "cf").precheck(moved, IPPOI_A, setup_m, {})
    fs = next(c for c in checks_m if c["name"] == "first_shell_in_qm")
    assert fs["passed"] and f"4 heavy atoms within {FIRST_SHELL}" in fs["detail"]  # shell is complete, just smaller
    ids = {c.decision_id for c in _metal_cards(moved, setup_m, checks_m)}
    assert not any("FIRST_SHELL_WAT" in i for i in ids)
    cut = next(c for c in _metal_cards(moved, setup_m, checks_m) if c.decision_id == "DEC_CUT_LEVEL")
    assert cut.evidence["mask"] != setup["mask"] and cut.evidence["mask"] == prop.mask


# ----------------------------------------------------------- 3/4/5. ABL ligand
def _set_xyz(line: str, xyz) -> str:
    return line[:30] + "".join(f"{v:8.3f}" for v in xyz) + line[54:]


def _edit_pdb(src: Path, dst: Path, drop=None, move=None) -> Path:
    """Copy src to dst, dropping lines where drop(line) is true and moving atoms {(chain, resnum, name): xyz}."""
    move = move or {}
    out = []
    for line in src.read_text().splitlines(keepends=True):
        if drop and drop(line):
            continue
        if line.startswith(("ATOM", "HETATM")):
            key = (line[21], int(line[22:26]), line[12:16].strip())
            if key in move:
                line = _set_xyz(line, move[key])
        out.append(line)
    dst.write_text("".join(out))
    return dst


def _atom_xyz(pdb: Path, chain: str, resname: str, name: str) -> np.ndarray:
    a = next(a for a in prep.read_pdb_atoms(pdb) if a["chain"] == chain and a["resname"] == resname and a["name"] == name)
    return np.array([a["x"], a["y"], a["z"]])


def _ligand_setup(pdb: Path, work: Path, chain: str = "B") -> dict:
    """The pure stages of LigandSetup (choose_chain, extract, protonation site) on a given PDB."""
    table = prep.choose_chain(pdb, "STI")
    prep.extract(pdb, chain, "STI", work)
    return {"chain": chain, "chain_source": "test", "chain_table": table["table"], "overrides": [],
            "ligand_site": prep.ligand_protonation_site(work)}


def _abl_cards(setup, pdb):
    return ligand_cards(dict(ABL_A, pdb=str(pdb)), setup, [], {}, {}, {})


@needs_abl
def test_ligand_protonation_follows_backbone_o(tmp_path):
    base = _ligand_setup(PDB, tmp_path / "base")
    card = _card(_abl_cards(base, PDB), "DEC_LIGAND_")
    assert card["decision_id"] == "DEC_LIGAND_PROTONATION_N51" and card["choice"] == "protonate N51 (+1)"
    assert card["evidence"]["contacts"] == [{"partner": "ILE360@O", "distance": 2.751}]

    # (a) ILE360 O moved 10 Å away: HIS361@O stays at 3.445 Å (> 3.3), so no amine keeps a backbone-O contact
    o = _atom_xyz(PDB, "B", "ILE", "O")
    far = _edit_pdb(PDB, tmp_path / "far.pdb", move={("B", 360, "O"): o + np.array([10.0, 0.0, 0.0])})
    s_far = _ligand_setup(far, tmp_path / "far")
    assert s_far["ligand_site"] is None
    c_far = _card(_abl_cards(s_far, far), "DEC_LIGAND_")
    assert c_far["decision_id"] == "DEC_LIGAND_NEUTRAL" and c_far["choice"] == "kept neutral"
    assert "contacts" not in c_far["evidence"]

    # (b) ILE360 O placed 2.90 Å beyond N48 on the N51->N48 axis: the protonation site moves to N48
    n48, n51 = _atom_xyz(PDB, "B", "STI", "N48"), _atom_xyz(PDB, "B", "STI", "N51")
    u = (n48 - n51) / np.linalg.norm(n48 - n51)
    near = _edit_pdb(PDB, tmp_path / "n48.pdb", move={("B", 360, "O"): n48 + 2.9 * u})
    s_n48 = _ligand_setup(near, tmp_path / "n48")
    c_n48 = _card(_abl_cards(s_n48, near), "DEC_LIGAND_")
    assert c_n48["decision_id"] == "DEC_LIGAND_PROTONATION_N48" and c_n48["choice"] == "protonate N48 (+1)"
    assert c_n48["evidence"]["contacts"][0]["partner"] == "ILE360@O"
    assert c_n48["evidence"]["contacts"][0]["distance"] == pytest.approx(2.9, abs=0.002)
    assert "N51" not in [e["atom"] for e in s_n48["ligand_site"]["checked"] if e["contacts"]]


def _drop_chain_remarks(chain):
    pat = re.compile(rf"REMARK (465|470)\s+[A-Z]{{3}} {chain}\s")
    return lambda line: bool(pat.match(line))


@needs_abl
def test_chain_card_follows_remark_465_470(tmp_path):
    base = _ligand_setup(PDB, tmp_path / "base")
    assert prep.choose_chain(PDB, "STI")["chain"] == "B"
    rows = {r["chain"]: r for r in base["chain_table"]}
    assert rows["B"]["score"] == (0, 2, 8, "B") and rows["D"]["score"] == (0, 3, 9, "D")

    edited = _edit_pdb(PDB, tmp_path / "d.pdb", drop=_drop_chain_remarks("D"))
    choice = prep.choose_chain(edited, "STI")
    assert choice["chain"] == "D"
    setup = {"chain": choice["chain"], "chain_source": "REMARK 465/470 pocket completeness", "chain_table": choice["table"],
             "overrides": [], "ligand_site": None}
    card = _card(_abl_cards(setup, edited), "DEC_CHAIN_")
    assert card["decision_id"] == "DEC_CHAIN_D" and card["choice"].startswith("chain D")
    d_row = next(r for r in card["evidence"]["table"] if r["chain"] == "D")
    assert d_row["score"] == (0, 0, 0, "D")
    assert d_row["missing_residues"] == 0 and d_row["missing_atom_residues_in_pocket"] == []
    assert next(r for r in card["evidence"]["table"] if r["chain"] == "B")["score"] == (0, 2, 8, "B")  # untouched
    assert {a["name"] for a in card["alternatives"]} == {"chain A", "chain B", "chain C"}
    assert "0 residues with missing atoms in the pocket, 0 missing residues" in card["rationale"]


@needs_abl
@pytest.mark.skipif(not ABL_CACHE.exists(), reason="no cached ABL preparation")
def test_sample_mode_setup_does_not_let_cache_override_edited_inputs(tmp_path):
    """End-to-end on the judge path (SAMPLE_MODE, cached prep keyed by case id).

    Before the fix, setup.update(cached) replaced this run's chain/site with the cached ones, so a card built from an
    edited PDB still said chain B / N51. Now the fresh decision is kept and the mismatching cache is refused.
    """
    base = LigandSetup(None, None, "cf", tmp_path / "w0", sample_mode=True).build(dict(ABL_A))
    assert base["prep_skipped"] is None and base["chain"] == "B" and base["ligand_site"]["atom"] == "N51"

    edited = _edit_pdb(PDB, tmp_path / "d.pdb", drop=_drop_chain_remarks("D"))
    s = LigandSetup(None, None, "cf", tmp_path / "w1", sample_mode=True).build(dict(ABL_A, pdb=str(edited)))
    assert s["chain"] == "D" and next(r for r in s["chain_table"] if r["chain"] == "D")["score"] == (0, 0, 0, "D")
    assert s["prep_skipped"] and "chain D" in s["prep_skipped"] and "chain B" in s["prep_skipped"]
    assert _card(_abl_cards(s, edited), "DEC_CHAIN_")["decision_id"] == "DEC_CHAIN_D"

    o = _atom_xyz(PDB, "B", "ILE", "O")
    far = _edit_pdb(PDB, tmp_path / "far.pdb", move={("B", 360, "O"): o + np.array([10.0, 0.0, 0.0])})
    s2 = LigandSetup(None, None, "cf", tmp_path / "w2", sample_mode=True).build(dict(ABL_A, pdb=str(far)))
    assert s2["chain"] == "B" and s2["ligand_site"] is None
    assert s2["prep_skipped"] and "N51" in s2["prep_skipped"]
    assert _card(_abl_cards(s2, far), "DEC_LIGAND_")["decision_id"] == "DEC_LIGAND_NEUTRAL"


@needs_abl
@pytest.mark.skipif(not ABL_CACHE.exists(), reason="no cached ABL preparation")
def test_his_override_follows_pka_window(tmp_path):
    """review_uncertain is pure given PROPKA output; use the cached PROPKA pKa table, then move HIS361's pKa."""
    cached = json.loads(ABL_CACHE.read_text())
    keyed = ((re.fullmatch(r"([A-Z]+)(\d+)", k), v) for k, v in cached["protonation"]["pkas"].items())
    pkas = {(m.group(1), int(m.group(2))): v for m, v in keyed if m}  # skips terminus groups such as "N+1"
    states = {int(k): v for k, v in cached["protonation"]["states"].items()}
    work = tmp_path / "b"
    prep.extract(PDB, "B", "STI", work)
    site = prep.ligand_protonation_site(work)

    def cards_for(pka_table, cation):
        review = prep.review_uncertain(work, {"pka_table": pka_table, "states": states}, 7.4, cation)
        setup = {"chain": "B", "chain_source": "test", "chain_table": prep.choose_chain(PDB, "STI")["table"],
                 "ligand_site": site, "overrides": review["overrides"]}
        return review, _abl_cards(setup, PDB)

    review, cards = cards_for(pkas, site["atom"])
    card = _card(cards, "DEC_HIS_OVERRIDE_361")
    assert [o["resnum"] for o in review["overrides"]] == [361]
    assert card["choice"] == "HIP -> HIE (sensitivity run advised)"
    assert card["evidence"]["pka"] == 7.59 and card["evidence"]["d_ND1_cation"] == 5.96

    # counterfactual: HIS361 pKa 8.50 (|8.50 - 7.4| > 1.0) -> no longer uncertain -> no override card
    review2, cards2 = cards_for({**pkas, ("HIS", 361): 8.5}, site["atom"])
    assert review2["overrides"] == [] and "HIS361 pKa 8.50" not in review2["uncertain_his"]
    assert _card(cards2, "DEC_HIS_OVERRIDE_") is None

    # counterfactual: neutral ligand (no cation atom) -> nothing to face -> no override, pKa unchanged
    review3, cards3 = cards_for(pkas, None)
    assert review3["overrides"] == [] and "HIS361 pKa 7.59" in review3["uncertain_his"]
    assert _card(cards3, "DEC_HIS_OVERRIDE_") is None
