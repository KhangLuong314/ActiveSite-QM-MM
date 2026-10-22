"""Unit tests for ChemistryRunner and Amber input generation."""
import pytest
from pathlib import Path
from activesite.chem.runner import ChemistryRunner
from activesite.models import QMMMPartition, ResidueRole, ResidueSelection


def test_generate_amber_mdin():
    runner = ChemistryRunner(sample_mode=True)
    partition = QMMMPartition(
        system_name="egfr_erlotinib",
        qm_residues=[
            ResidueSelection(resname="AQ4", resid=1, role=ResidueRole.LIGAND, formal_charge=0),
            ResidueSelection(resname="MET", resid=769, role=ResidueRole.FIRST_SHELL_H_BOND, formal_charge=0),
        ],
        qm_charge=0,
        spin_multiplicity=1,
        amber_qmmask=":1,:769",
    )

    mdin = runner.generate_amber_mdin(partition, qm_theory="PM6", min_steps=300)
    assert "&cntrl" in mdin
    assert "&qmmm" in mdin
    assert "qmmask=':1,:769'" in mdin
    assert "qm_theory='PM6'" in mdin
    assert "qmcharge=0" in mdin
    assert "spin=1" in mdin


def test_run_simulation_sample_mode(tmp_path: Path):
    runner = ChemistryRunner(sample_mode=True)
    partition = QMMMPartition(
        system_name="egfr_erlotinib",
        qm_residues=[
            ResidueSelection(resname="AQ4", resid=1, role=ResidueRole.LIGAND, formal_charge=0),
        ],
        qm_charge=0,
        spin_multiplicity=1,
        amber_qmmask=":1",
    )

    result = runner.run_simulation(
        partition=partition,
        prmtop_path="dummy.parm7",
        inpcrd_path="dummy.inpcrd",
        output_dir=tmp_path / "runs",
        qm_theory="PM6",
    )

    assert result.success is True
    assert result.sample_mode is True
    assert result.energy_hartree < 0
    assert result.energy_kcal_mol < 0
    assert len(result.decision_cards) >= 1
    assert any("THEORY" in c.decision_id for c in result.decision_cards)
