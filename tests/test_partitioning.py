"""Unit tests for QMMMPartitioner, link atom cuts, and Track 02 explanation cards."""
import pytest
import numpy as np
from activesite.chem.partitioning import QMMMPartitioner, compute_link_atom_coords


def test_compute_link_atom_coords():
    qm_pos = np.array([0.0, 0.0, 0.0])
    mm_pos = np.array([1.5, 0.0, 0.0])
    la_pos = compute_link_atom_coords(qm_pos, mm_pos, bond_length=1.09)
    assert pytest.approx(la_pos[0], 0.01) == 1.09
    assert pytest.approx(la_pos[1], 0.01) == 0.0
    assert pytest.approx(la_pos[2], 0.01) == 0.0


def test_partition_egfr_erlotinib():
    partitioner = QMMMPartitioner()
    pdb_path = "data/reference/egfr/1m17.pdb"
    partition = partitioner.partition_ligand_system(
        pdb_path=pdb_path,
        ligand_resname="AQ4",
        cutoff_radius=4.0,
        literature_contacts={"MET769": "hinge backbone NH to quinazoline N1"},
        expected_absent={"THR766": "Interacts only through bridging crystal water"},
    )

    # Check net charge from residues (Lys721 +1, Glu738 -1, Asp831 -1 -> -1)
    assert partition.qm_charge == -1
    assert partition.spin_multiplicity == 1
    # Check that AQ4 is in QM residues
    resnames = [r.resname for r in partition.qm_residues]
    assert "AQ4" in resnames
    # Check that MET769 is in QM residues
    assert any(r.resname == "MET" and r.resid == 769 for r in partition.qm_residues)
    # Check that THR766 is excluded
    assert not any(r.resname == "THR" and r.resid == 766 for r in partition.qm_residues)

    # Check Decision Cards
    card_targets = [c.target for c in partition.decision_cards]
    assert any("MET769" in t for t in card_targets)
    assert any("THR766" in t for t in card_targets)
    assert any("Radius" in c.choice or "4.0" in c.choice for c in partition.decision_cards)
    assert any("Link Atom" in c.target or "Boundary" in c.target for c in partition.decision_cards)


def test_partition_metal_active_site():
    partitioner = QMMMPartitioner()
    parm7_path = "data/reference/qmmm_dft/step3_pbcsetup.parm7"
    coords_path = "data/reference/qmmm_dft/prod00.ncrst"
    partition = partitioner.partition_metal_system(
        parm7_path=parm7_path,
        coords_path=coords_path,
        metal_resid=371,
        cutoff_radius=4.0,
    )

    assert len(partition.qm_residues) >= 4
    # Metal MG is included
    assert any(r.resname == "MG" for r in partition.qm_residues)
    # Decision cards contain metal card
    assert any("MG" in c.target for c in partition.decision_cards)
