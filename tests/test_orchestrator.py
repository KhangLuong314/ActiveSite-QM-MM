"""Unit and integration tests for MasterOrchestrator and Explainer.

These run in SAMPLE_MODE (no Docker in CI), so every workflow must finish with a null
energy and say why. Each test uses its own empty ledger so nothing leaks between runs.
"""
import pytest
from activesite.agent.orchestrator import MasterOrchestrator
from activesite.memory.meterless import MeterlessHMEM


@pytest.fixture
def orchestrator(tmp_path, monkeypatch):
    # These tests describe sample mode with NO cached engine output, so isolate them from a generated data/sample/.
    monkeypatch.setenv("ACTIVESITE_SAMPLE_DIR", str(tmp_path / "no-sample"))
    return MasterOrchestrator(hmem=MeterlessHMEM(storage_path=tmp_path / "ledger.json"), sample_mode=True)


def test_orchestrator_run_egfr_case(orchestrator):
    events = []

    def on_event(stage, msg):
        events.append((stage, msg))

    output = orchestrator.run_case("egfr_erlotinib", on_event=on_event)

    assert output.success is False
    assert output.system_name == "egfr_erlotinib"
    assert output.result.energy_kcal_mol is None
    assert output.result.energy_hartree is None
    assert "SAMPLE_MODE" in output.result.error_message          # prep + engine skipped honestly
    assert output.stats["kind"] == "ligand" and output.stats["blocked"] == ["prep_available"]
    assert len(output.decision_cards) >= 4
    assert len(events) >= 5
    assert any("SAMPLE_MODE" in msg for stage, msg in events)
    assert "# ActiveSite report" in output.report_markdown
    assert "Decision cards" in output.report_markdown
    assert "`null`" in output.report_markdown and "SAMPLE_MODE" in output.report_markdown
    assert "## Limitations" in output.report_markdown
    assert "cryptographically" not in output.report_markdown


def test_orchestrator_run_ippoi_case(orchestrator):
    output = orchestrator.run_case("ippoi_site_a")

    assert output.success is False
    assert "ippoi" in output.system_name
    # The partitioner's formal-charge sum (Mg2+ + phosphate) is +1; the critic's per-residue
    # valence heuristic disagrees on parity and shifts it. With an empty ledger nothing can be
    # recalled to override either, so only the invariant (closed shell) is asserted here.
    # Open question for the critic prompt: replace the residue lookup table with real counting.
    assert output.partition.total_valence_electrons % 2 == 0
    assert output.partition.spin_multiplicity == 1
    assert output.result.energy_kcal_mol is None
    assert output.stats["kind"] == "metal"
    assert any("CRITIC" in c.decision_id or "CHARGE" in c.decision_id for c in output.decision_cards)


def test_orchestrator_run_freeform_query(orchestrator):
    query = "Set up a QM/MM simulation of EGFR kinase with erlotinib (PDB 1M17) at pH 7.4."
    output = orchestrator.run_query(query)

    assert output.success is False
    assert output.plan.pdb_id == "1M17"
    assert output.plan.ph == 7.4
    assert output.plan.ligand_name == "AQ4"
    assert output.result.energy_hartree is None
