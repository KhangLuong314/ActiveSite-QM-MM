"""Tests for activesite.chem.system (MolSystem geometry and charge layer)."""
from pathlib import Path

import numpy as np
import parmed as pmd
import pytest

from activesite.chem.system import ATOMIC_Z, ChargeReport, MolSystem

PARM7 = Path("data/reference/qmmm_dft/step3_pbcsetup.parm7")
NCRST = Path("data/reference/qmmm_dft/prod00.ncrst")


def _water() -> MolSystem:
    """Three-atom TIP3P-like water built in code: O at origin, H1 on +x, H2 at 104.52 deg."""
    s = pmd.Structure()
    o = pmd.Atom(name="O", atomic_number=8, charge=-0.834)
    h1 = pmd.Atom(name="H1", atomic_number=1, charge=0.417)
    h2 = pmd.Atom(name="H2", atomic_number=1, charge=0.417)
    for a in (o, h1, h2):
        s.add_atom(a, "WAT", 1)
    s.bonds.append(pmd.Bond(o, h1))
    s.bonds.append(pmd.Bond(o, h2))
    theta = np.radians(104.52)
    s.coordinates = np.array([
        [0.0, 0.0, 0.0],
        [0.9572, 0.0, 0.0],
        [0.9572 * np.cos(theta), 0.9572 * np.sin(theta), 0.0],
    ])
    return MolSystem.from_structure(s)


# ----------------------------------------------------------------- fast tests
def test_import_has_no_side_effects(tmp_path: Path):
    """Importing the module must not read files, write files, or build a system."""
    import subprocess
    import sys

    code = (
        "import activesite.chem.system as m, parmed\n"
        "assert not any(isinstance(v, (m.MolSystem, parmed.Structure)) for v in vars(m).values())\n"
        "print('clean')"
    )
    proc = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, cwd=tmp_path,
        env={"PYTHONPATH": str(Path.cwd()), "PATH": ""}, timeout=60,
    )
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip() == "clean"
    assert list(tmp_path.iterdir()) == []
    assert ATOMIC_Z["Mg"] == 12 and ATOMIC_Z["H"] == 1


def test_water_labels_and_geometry():
    w = _water()
    assert w.label(0) == "WAT1@O"
    assert w.label(2) == "WAT1@H2"
    assert w.res_label(0) == "WAT1"
    assert w.dist(0, 1) == pytest.approx(0.9572, abs=1e-6)
    assert w.angle(1, 0, 2) == pytest.approx(104.52, abs=1e-6)
    assert w.dist(1, 2) == pytest.approx(1.5139, abs=1e-3)


def test_water_within_sorted_and_excludes_self():
    w = _water()
    assert w.within(1, 2.0) == [0, 2]   # O (0.957 A) before H2 (1.514 A)
    assert w.within(1, 1.0) == [0]
    assert w.within(0, 0.5) == []


def test_water_select_mask():
    w = _water()
    assert w.select("@O") == [0]
    assert w.select(":WAT") == [0, 1, 2]


def test_water_charge_report():
    w = _water()
    full = w.charge_report([0, 1, 2])
    assert isinstance(full, ChargeReport)
    assert full.mm_sum == pytest.approx(0.0, abs=1e-9)
    assert full.nearest_int == 0
    assert full.electrons == 10
    assert full.link_atoms == 0

    only_o = w.charge_report([0])
    assert only_o.mm_sum == pytest.approx(-0.834)
    assert only_o.nearest_int == -1
    assert only_o.fraction == pytest.approx(0.166)
    assert only_o.electrons == 9
    assert only_o.link_atoms == 2
    # A water has no rings, so the two cut O-H bonds are not ring bonds.
    assert w.ring_bonds_cut([0]) == []


def test_atom_mask_compaction():
    assert MolSystem.atom_mask([0, 1, 2, 8, 11, 12, 13]) == "@1-3,9,12-14"
    assert MolSystem.atom_mask([5]) == "@6"
    assert MolSystem.atom_mask([3, 1, 1, 2]) == "@2-4"
    assert MolSystem.atom_mask([]) == ""


# ----------------------------------------------------------------- slow tests
needs_reference = pytest.mark.skipif(
    not (PARM7.exists() and NCRST.exists()),
    reason="I-PpoI reference parm7/ncrst not present",
)


@pytest.fixture(scope="module")
def ippoi() -> MolSystem:
    return MolSystem(PARM7, NCRST)


@needs_reference
def test_ippoi_residue_371_is_mg(ippoi: MolSystem):
    assert ippoi.res_label(370) == "MG371"
    mg = ippoi.select(":371")
    assert len(mg) == 1
    assert ippoi.label(mg[0]) == "MG371@MG"
    assert ippoi.atoms[mg[0]].atomic_number == ATOMIC_Z["Mg"]


@needs_reference
def test_ippoi_whole_system_charge_report(ippoi: MolSystem):
    rep = ippoi.charge_report(range(len(ippoi.atoms)))
    assert abs(rep.mm_sum) < 0.01
    assert rep.nearest_int == 0
    assert rep.link_atoms == 0
    assert rep.electrons > 0 and rep.electrons % 2 == 0


def _first_nucleotide(system: MolSystem):
    for res in system.s.residues:
        if res.name in ("DA", "DG", "DC", "DT"):
            return res
    pytest.skip("no interior nucleotide in reference system")


@needs_reference
def test_ippoi_ring_bonds_cut(ippoi: MolSystem):
    nuc = _first_nucleotide(ippoi)
    c3 = next(a for a in nuc.atoms if a.name == "C3'")

    # Selecting only C3' cuts its four bonds; the two furanose ring bonds (to C4' and C2') are flagged.
    cut = ippoi.ring_bonds_cut([c3.idx])
    assert sorted(cut) == sorted([
        f"{ippoi.label(c3.idx)}-C4'",
        f"{ippoi.label(c3.idx)}-C2'",
    ])
    assert ippoi.charge_report([c3.idx]).link_atoms == 4

    # The whole nucleotide only cuts inter-residue backbone bonds, which are not rings.
    whole = [a.idx for a in nuc.atoms]
    assert ippoi.ring_bonds_cut(whole) == []
    assert ippoi.charge_report(whole).link_atoms == 2  # O3'-P to the next residue, P-O3' from the previous
