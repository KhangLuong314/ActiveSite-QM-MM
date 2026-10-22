"""Unit tests for CriticAgent and episodic self-correction loop."""
import pytest
from pathlib import Path
from activesite.agent.critic import CriticAgent
from activesite.memory.meterless import EpisodicMemoryRecord, MeterlessHMEM
from activesite.models import LinkAtom, QMMMPartition, ResidueRole, ResidueSelection


def test_critic_inspect_closed_shell_egfr():
    critic = CriticAgent()
    partition = QMMMPartition(
        system_name="egfr_erlotinib",
        qm_residues=[
            ResidueSelection(resname="AQ4", resid=1, role=ResidueRole.LIGAND, formal_charge=0),
            ResidueSelection(resname="MET", resid=769, role=ResidueRole.FIRST_SHELL_H_BOND, formal_charge=0),
        ],
        link_atoms=[
            LinkAtom(
                link_id="LA_MET769",
                residue_name="MET",
                residue_number=769,
                qm_atom="CB",
                mm_atom="CA",
                position=(1.0, 2.0, 3.0),
            )
        ],
        qm_charge=-1,  # Lys, Glu, Asp net
        spin_multiplicity=1,
    )

    report = critic.inspect_and_correct(partition, qm_theory="PM6")
    assert report.is_closed_shell is True
    assert report.spin_multiplicity == 1


def _ippoi_partition() -> QMMMPartition:
    return QMMMPartition(
        system_name="ippoi_wt",
        qm_residues=[
            ResidueSelection(resname="MG", resid=371, role=ResidueRole.METAL, formal_charge=2),
            ResidueSelection(resname="DA", resid=34, role=ResidueRole.CATALYTIC, formal_charge=-1),
            ResidueSelection(resname="HIS", resid=119, role=ResidueRole.CATALYTIC, formal_charge=0),
            ResidueSelection(resname="GLN", resid=139, role=ResidueRole.CATALYTIC, formal_charge=0),
            ResidueSelection(resname="ASN", resid=160, role=ResidueRole.CATALYTIC, formal_charge=0),
        ],
        link_atoms=[],
        qm_charge=0,  # deliberately incorrect initial charge
        spin_multiplicity=2,
    )


def test_critic_odd_electron_without_memory_uses_generic_shift(tmp_path: Path):
    """With an empty ledger there is nothing to recall; the critic falls back to a parity shift."""
    hmem = MeterlessHMEM(storage_path=tmp_path / "empty.json")
    critic = CriticAgent(hmem=hmem)
    partition = _ippoi_partition()

    report = critic.inspect_and_correct(partition, qm_theory="PM6")

    assert partition.qm_charge == 1
    assert report.is_closed_shell is True
    assert len(report.corrections_applied) == 1
    assert "Meterless H-MEM" not in report.corrections_applied[0]
    assert report.decision_cards == []
    assert hmem.get_ledger() == []


def test_critic_self_correct_ippoi_odd_electron(tmp_path: Path):
    # Record the lesson explicitly: the ledger is never pre-seeded.
    ledger_file = tmp_path / "test_ledger.json"
    hmem = MeterlessHMEM(storage_path=ledger_file)
    hmem.record_episode(
        EpisodicMemoryRecord(
            record_id="MEM_TEST_IPPOI_SPIN",
            system_id="ippoi_wt",
            stage="critic",
            state_signature="ippoi_mg371_charge0",
            action_taken="Assign qmcharge=0 for catalytic site with Mg2+",
            outcome="SELF_CORRECTED",
            error_type="ODD_ELECTRON_SPIN_MISMATCH",
            diagnosed_cause="Mg2+ site with scissile phosphate left an unpaired electron at qmcharge=0.",
            corrective_action="Increment qmcharge from 0 to +1.",
            learned_rule="Mg2+ coordination in this site requires qmcharge=+1 for a closed-shell singlet.",
            trust_score=0.9,
            metadata={"recommended_qmcharge": 1},
        )
    )
    critic = CriticAgent(hmem=hmem)

    partition = _ippoi_partition()
    report = critic.inspect_and_correct(partition, qm_theory="PM6")

    # Verify that the critic detected the odd electron and self-corrected to qmcharge=+1
    assert partition.qm_charge == 1
    assert report.is_closed_shell is True
    assert report.spin_multiplicity == 1
    assert len(report.corrections_applied) > 0
    assert any("MEM_TEST_IPPOI_SPIN" in c for c in report.corrections_applied)
    assert len(report.decision_cards) > 0
    assert len(hmem.get_ledger()) == 1

    critic_card = report.decision_cards[0]
    assert critic_card.confidence >= 0.95
    assert "odd-electron" in critic_card.rationale.lower()
