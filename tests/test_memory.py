"""Unit tests for Meterless H-MEM episodic memory and trust ledger."""
import json
from pathlib import Path

from activesite.memory.meterless import EpisodicMemoryRecord, MeterlessHMEM, TrustLedgerEntry
from activesite.memory.meterless_mcp import handle_request


def _lesson(record_id: str = "MEM_TEST_001", system_id: str = "test_kinase") -> EpisodicMemoryRecord:
    return EpisodicMemoryRecord(
        record_id=record_id,
        system_id=system_id,
        stage="critic",
        state_signature="test_sig",
        action_taken="Auto-correct charge",
        outcome="SELF_CORRECTED",
        error_type="CHARGE_DISCREPANCY",
        diagnosed_cause="Deprotonated Asp without balance",
        corrective_action="Set qmcharge=-1",
        learned_rule="When active site pocket has uncoordinated Asp, total charge must decrement by 1",
        trust_score=0.92,
    )


def test_fresh_ledger_starts_empty(tmp_path: Path):
    ledger_file = tmp_path / "test_ledger.json"
    hmem = MeterlessHMEM(storage_path=ledger_file)

    assert hmem.query_memories() == []
    assert hmem.get_ledger() == []
    assert hmem.recall_corrective_action("ippoi_wt", "ODD_ELECTRON_SPIN_MISMATCH") is None
    # Nothing is written to disk until a record is actually stored.
    assert not ledger_file.exists()


def test_committed_default_ledger_is_empty():
    data = json.loads(Path("data/memory/meterless_ledger.json").read_text())
    assert data["records"] == []
    assert data["ledger"] == []


def test_corrupt_ledger_starts_empty_without_seeding(tmp_path: Path):
    ledger_file = tmp_path / "test_ledger.json"
    ledger_file.write_text("{not json")
    hmem = MeterlessHMEM(storage_path=ledger_file)
    assert hmem.query_memories() == []


def test_hmem_record_persist_and_recall_correction(tmp_path: Path):
    ledger_file = tmp_path / "test_ledger.json"
    hmem = MeterlessHMEM(storage_path=ledger_file)
    hmem.record_episode(_lesson())

    recalled = hmem.recall_corrective_action(system_id="test_kinase", error_type="CHARGE_DISCREPANCY")
    assert recalled is not None
    assert recalled.corrective_action == "Set qmcharge=-1"
    assert recalled.trust_score == 0.92

    # Persisted and reloaded by a fresh instance pointing at the same file.
    reloaded = MeterlessHMEM(storage_path=ledger_file)
    assert [r.record_id for r in reloaded.query_memories()] == ["MEM_TEST_001"]


def test_recall_does_not_cross_systems(tmp_path: Path):
    """A lesson learned on one system must not be applied to an unrelated one."""
    hmem = MeterlessHMEM(storage_path=tmp_path / "l.json")
    hmem.record_episode(_lesson(system_id="test_kinase"))
    assert hmem.recall_corrective_action("other_enzyme", "CHARGE_DISCREPANCY") is None
    # 'generic' lessons remain applicable everywhere.
    hmem.record_episode(_lesson(record_id="MEM_GEN", system_id="generic"))
    assert hmem.recall_corrective_action("other_enzyme", "CHARGE_DISCREPANCY").record_id == "MEM_GEN"


def test_trust_ledger_entry(tmp_path: Path):
    hmem = MeterlessHMEM(storage_path=tmp_path / "test_ledger.json")
    hmem.record_trust_entry(
        TrustLedgerEntry(
            entry_id="LEDGER_001",
            decision_id="DEC_001",
            system_id="egfr_erlotinib",
            agent_name="CriticAgent",
            confidence=0.99,
            verified=True,
            verifier_notes="Electron count is even, spin multiplicity 1",
        )
    )
    ledger = hmem.get_ledger()
    assert len(ledger) == 1
    assert ledger[0].decision_id == "DEC_001"


def test_mcp_handler_records_then_queries(tmp_path: Path):
    hmem = MeterlessHMEM(storage_path=tmp_path / "test_ledger.json")

    resp_list = handle_request(hmem, {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}})
    tool_names = [t["name"] for t in resp_list["result"]["tools"]]
    assert {"query_memory", "record_lesson", "get_trust_ledger"} <= set(tool_names)

    # Empty before anything is recorded.
    empty = handle_request(hmem, {
        "jsonrpc": "2.0", "id": 2, "method": "tools/call",
        "params": {"name": "query_memory", "arguments": {"system_id": "ippoi"}},
    })
    assert json.loads(empty["result"]["content"][0]["text"]) == []

    recorded = handle_request(hmem, {
        "jsonrpc": "2.0", "id": 3, "method": "tools/call",
        "params": {"name": "record_lesson", "arguments": {
            "system_id": "ippoi_wt", "stage": "critic",
            "learned_rule": "Mg2+ site needs qmcharge=+1 for a closed shell",
            "error_type": "ODD_ELECTRON_SPIN_MISMATCH", "corrective_action": "qmcharge 0 -> +1",
        }},
    })
    assert "Lesson recorded" in recorded["result"]["content"][0]["text"]

    found = handle_request(hmem, {
        "jsonrpc": "2.0", "id": 4, "method": "tools/call",
        "params": {"name": "query_memory", "arguments": {"system_id": "ippoi"}},
    })
    records = json.loads(found["result"]["content"][0]["text"])
    assert len(records) == 1
    assert records[0]["system_id"] == "ippoi_wt"
