"""Unit tests for ActiveSite data models and Decision Cards."""
import pytest
from activesite.models import (
    AlternativeChoice,
    DecisionCard,
    DecisionCategory,
    LinkAtom,
    QMMMPartition,
    ResidueRole,
    ResidueSelection,
    SimulationResult,
)


def test_decision_card_creation_and_markdown():
    card = DecisionCard(
        decision_id="DEC_EGFR_MET769_INC",
        category=DecisionCategory.RESIDUE_INCLUSION,
        target="MET769",
        choice="Include MET769 backbone in QM region",
        alternatives=[
            AlternativeChoice(
                name="Treat MET769 as classical MM point charges",
                rejected_reason="Direct 2.8 A hydrogen bond to erlotinib quinazoline N1 requires quantum orbital overlap and polarization.",
            )
        ],
        rationale="MET769 forms the key hinge hydrogen bond (backbone NH to N1 at 2.8 A). Neglecting quantum polarization underestimates binding affinity by ~3.5 kcal/mol.",
        confidence=0.98,
        evidence={"distance_angstrom": 2.82, "donor_acceptor_angle": 165.4},
    )

    assert card.decision_id == "DEC_EGFR_MET769_INC"
    assert card.confidence == 0.98
    md = card.to_markdown()
    assert "Decision Card: `DEC_EGFR_MET769_INC`" in md
    assert "MET769" in md
    assert "2.8 A" in md


def test_qmmm_partition_model():
    res1 = ResidueSelection(
        resname="MET",
        resid=769,
        chain="A",
        role=ResidueRole.FIRST_SHELL_H_BOND,
        is_qm=True,
        formal_charge=0,
    )
    res2 = ResidueSelection(
        resname="AQ4",
        resid=1,
        chain="A",
        role=ResidueRole.LIGAND,
        is_qm=True,
        formal_charge=0,
    )
    link = LinkAtom(
        link_id="LA_MET769_CA_CB",
        residue_name="MET",
        residue_number=769,
        qm_atom="CB",
        mm_atom="CA",
        element="H",
    )

    partition = QMMMPartition(
        system_name="EGFR_erlotinib",
        qm_residues=[res1, res2],
        link_atoms=[link],
        qm_charge=0,
        spin_multiplicity=1,
        amber_qmmask=":769,:1",
    )

    assert len(partition.qm_residues) == 2
    assert partition.qm_charge == 0
    assert partition.link_atoms[0].element == "H"


def test_simulation_result_model_defaults_to_null_energy():
    res = SimulationResult(
        success=False,
        system_name="egfr_erlotinib",
        qm_theory="PM6",
        error_message="engine not run: SAMPLE_MODE=true",
    )
    assert res.success is False
    assert res.energy_hartree is None
    assert res.energy_kcal_mol is None
    dumped = res.model_dump()
    assert dumped["energy_hartree"] is None
    assert dumped["error_message"] == "engine not run: SAMPLE_MODE=true"
    assert dumped["engine"] == "engine unavailable" and dumped["engine_output"] == {}
