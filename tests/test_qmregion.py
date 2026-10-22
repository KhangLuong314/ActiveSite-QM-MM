"""Tests for activesite.chem.qmregion against the I-PpoI reference system.

The expert QM mask for this exact parm7/ncrst is defined in
data/reference/qmmm_dft/gen_inputs.sh (QMMASK/QMCHARGE, site Mg371).
gen_qmmask.py is a fragment listing whole residues for the second site
(Mg372) and qmhub.ini carries engine settings only, so neither defines
the mask or the charge; they are read here to document that.
"""
import re
from pathlib import Path

import pytest

from activesite.chem.qmregion import Choice, compare, propose
from activesite.chem.system import MolSystem

REF = Path("data/reference/qmmm_dft")
PARM7 = REF / "step3_pbcsetup.parm7"
NCRST = REF / "prod00.ncrst"

pytestmark = pytest.mark.skipif(
    not (PARM7.exists() and NCRST.exists() and (REF / "gen_inputs.sh").exists()),
    reason="I-PpoI reference files not present",
)


def expert_mask_and_charge() -> tuple[str, int]:
    """Expand QMMASK from gen_inputs.sh exactly as its sed/shell substitution would."""
    text = (REF / "gen_inputs.sh").read_text()
    var = lambda name: re.search(rf'^{name}="([^"]*)"', text, re.M).group(1)  # noqa: E731
    mask = var("QMMASK").replace("\\", "")
    for name in ("PROTEIN", "METAL", "WATER"):
        mask = mask.replace("${%s}" % name, var(name))
    charge = int(var("QMCHARGE"))
    return mask, charge


def reference_fragments() -> tuple[list[str], str]:
    """Residue list from gen_qmmask.py and the low-level theory from qmhub.ini (documentation only)."""
    resids = re.findall(r"\[\s*'(\w+)',\s*':(\d+)'\]", (REF / "gen_qmmask.py").read_text())
    theory = re.search(r"^qm_theory\s*=\s*(\w+)", (REF / "qmhub.ini").read_text(), re.M).group(1)
    return [f"{n}{r}" for n, r in resids], theory


@pytest.fixture(scope="module")
def ippoi() -> MolSystem:
    return MolSystem(PARM7, NCRST)


def _assert_numeric_evidence(choices: list[Choice]) -> None:
    for c in choices:
        assert c.evidence, f"{c.residue}/{c.role} has no evidence"
        flat = []
        stack = list(c.evidence.values())
        while stack:
            v = stack.pop()
            if isinstance(v, (list, tuple)):
                stack.extend(v)
            else:
                flat.append(v)
        assert any(isinstance(v, (int, float)) and not isinstance(v, bool) for v in flat), (
            f"{c.residue}/{c.role} evidence has no number: {c.evidence}"
        )


def test_expert_references_are_what_we_think(ippoi: MolSystem):
    mask, charge = expert_mask_and_charge()
    assert mask == "(:301,322&!@N,H,CA,HA,C,O)|(:13&@385-409)|(:14&!@417-442)|:371,397,398,399,400"
    assert charge == 1
    assert ippoi.res_label(370) == "MG371"
    residues, theory = reference_fragments()
    assert "MG372" in residues and theory.lower() == "pm6"   # gen_qmmask.py describes the other site


def test_propose_371_matches_expert(ippoi: MolSystem):
    mask, qmcharge = expert_mask_and_charge()
    expert = ippoi.select(mask)
    assert len(expert) == 64

    prop = propose(ippoi, 371)
    cmp = compare(ippoi, prop.atoms, expert)
    assert cmp["atom_jaccard"] == 1.0, cmp
    assert cmp["only_ours"] == [] and cmp["only_expert"] == []
    assert prop.charge.nearest_int == qmcharge
    assert prop.charge.fraction <= 0.10
    assert prop.charge.link_atoms == 4
    assert prop.mask == MolSystem.atom_mask(expert)
    assert ippoi.select(prop.mask) == prop.atoms
    _assert_numeric_evidence(prop.choices)

    roles = {c.role: c for c in prop.choices}
    assert roles["metal"].residue == "MG371"
    assert roles["scissile_phosphate"].residue == "DG14"
    assert roles["leaving_group"].residue == "DA13"
    assert roles["nucleophile"].residue == "WAT397"
    assert roles["nucleophile"].evidence["Ow_P_O3prime_angle"] > 160
    assert len(roles["nucleophile"].evidence["rejected"]) >= 2
    assert roles["general_base"].residue == "HIE301"
    assert roles["general_base"].evidence["N_Ow_dist"] < 3.0
    first_shell = {c.residue for c in prop.choices if c.role == "first_shell"}
    assert {"ASN322", "WAT398", "WAT399", "WAT400", "DA13", "DG14"} <= first_shell


def test_cut_levels_minimal_rejected_sugar_accepted(ippoi: MolSystem):
    prop = propose(ippoi, 371)
    assert prop.cut_level == "sugar"
    rejected = [n for n in prop.notes if n.startswith("minimal rejected")]
    accepted = [n for n in prop.notes if n.startswith("sugar accepted")]
    assert len(rejected) == 1 and "ring bonds cut" in rejected[0]
    assert "DA13@C3'-C4'" in rejected[0] and "DA13@C3'-C2'" in rejected[0]
    assert len(accepted) == 1 and "no ring bonds cut" in accepted[0]

    forced = propose(ippoi, 371, cut_level="minimal")
    assert forced.cut_level == "minimal"
    assert any("ring bonds cut" in n for n in forced.notes)
    assert len(forced.atoms) < len(prop.atoms)


def test_propose_372_stays_local(ippoi: MolSystem):
    prop = propose(ippoi, 372)
    assert prop.atoms and prop.charge.link_atoms > 0
    _assert_numeric_evidence(prop.choices)
    metal = ippoi.select(":372")[0]
    by_res: dict[int, list[int]] = {}
    for i in prop.atoms:
        by_res.setdefault(ippoi.atoms[i].residue.idx, []).append(i)
    for ridx, idxs in by_res.items():
        nearest = min(ippoi.dist(metal, i) for i in idxs)
        assert nearest <= 8.0, f"{ippoi.res_label(ridx)} nearest atom {nearest:.2f} Å from MG372"
    roles = {c.role: c.residue for c in prop.choices}
    assert roles["scissile_phosphate"] == "DG35" and roles["leaving_group"] == "DA34"


def test_compare_reports_differences(ippoi: MolSystem):
    expert = ippoi.select(expert_mask_and_charge()[0])
    ours = [i for i in expert if ippoi.atoms[i].residue.name != "WAT"]
    cmp = compare(ippoi, ours, expert)
    assert 0 < cmp["atom_jaccard"] < 1
    assert cmp["expert_atoms"] == 64 and cmp["shared_atoms"] == len(ours)
    assert cmp["only_ours"] == []
    assert all(lbl.startswith("WAT") for lbl in cmp["only_expert"])
    assert set(cmp["residues_expert"]) - set(cmp["residues_ours"]) == {"WAT397", "WAT398", "WAT399", "WAT400"}


def test_bad_inputs(ippoi: MolSystem):
    with pytest.raises(ValueError):
        propose(ippoi, 301)                      # a His, not an ion
    with pytest.raises(ValueError):
        propose(ippoi, 371, cut_level="bogus")
