"""Unit and integration tests for MasterOrchestrator and Explainer."""
import pytest
from activesite.agent.orchestrator import MasterOrchestrator


def test_orchestrator_run_egfr_case():
    orchestrator = MasterOrchestrator(sample_mode=True)
    events = []

    def on_event(stage, msg):
        events.append((stage, msg))

    output = orchestrator.run_case("egfr_erlotinib", on_event=on_event)

    assert output.success is True
    assert output.system_name == "egfr_erlotinib"
    assert output.result.energy_kcal_mol < 0
    assert len(output.decision_cards) >= 4
    assert len(events) >= 5
    assert "# 🔬 ActiveSite Explanation Report" in output.report_markdown
    assert "Decision Cards" in output.report_markdown


def test_orchestrator_run_ippoi_case():
    orchestrator = MasterOrchestrator(sample_mode=True)
    output = orchestrator.run_case("ippoi_site_a")

    assert output.success is True
    assert "ippoi" in output.system_name
    assert output.partition.qm_charge == 1  # Self-corrected or balanced
    assert output.result.energy_kcal_mol < 0
    assert any("CRITIC" in c.decision_id or "CHARGE" in c.decision_id for c in output.decision_cards)


def test_orchestrator_run_freeform_query():
    orchestrator = MasterOrchestrator(sample_mode=True)
    query = "Set up a QM/MM simulation of EGFR kinase with erlotinib (PDB 1M17) at pH 7.4."
    output = orchestrator.run_query(query)

    assert output.success is True
    assert output.plan.pdb_id == "1M17"
    assert output.plan.ph == 7.4
    assert output.plan.ligand_name == "AQ4"
    assert output.result.energy_hartree < 0
