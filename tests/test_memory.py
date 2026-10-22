"""Unit tests for Meterless H-MEM episodic memory and trust ledger."""
import pytest
from pathlib import Path
from activesite.memory.meterless import EpisodicMemoryRecord, MeterlessHMEM, TrustLedgerEntry
from activesite.memory.meterless_mcp import handle_request


def test_hmem_initialization_and_seeding(tmp_path: Path):
    ledger_file = tmp_path / "test_ledger.json"
    hmem = MeterlessHMEM(storage_path=ledger_file)

    # Check seeded foundational memories
    records = hmem.query_memories(system_id="ippoi")
    assert len(records) >= 1
    assert "ODD_ELECTRON_SPIN_MISMATCH" in [r.error_type for r in records]

    # Check query with keywords
    results = hmem.query_memories(keywords=["erlotinib"])
    assert len(results) >= 1
    assert "769" in results[0].learned_rule


def test_hmem_record_and_recall_correction(tmp_path: Path):
    ledger_file = tmp_path / "test_ledger.json"
    hmem = MeterlessHMEM(storage_path=ledger_file)

    # Store a new self-corrected record
    new_record = EpisodicMemoryRecord(
        record_id="MEM_TEST_001",
        system_id="test_kinase",
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
    hmem.record_episode(new_record)

    # Recall corrective action
    recalled = hmem.recall_corrective_action(system_id="test_kinase", error_type="CHARGE_DISCREPANCY")
    assert recalled is not None
    assert recalled.corrective_action == "Set qmcharge=-1"
    assert recalled.trust_score == 0.92


def test_trust_ledger_entry(tmp_path: Path):
    ledger_file = tmp_path / "test_ledger.json"
    hmem = MeterlessHMEM(storage_path=ledger_file)

    entry = TrustLedgerEntry(
        entry_id="LEDGER_001",
        decision_id="DEC_001",
        system_id="egfr_erlotinib",
        agent_name="CriticAgent",
        confidence=0.99,
        verified=True,
        verifier_notes="Electron count is even, spin multiplicity 1",
    )
    hmem.record_trust_entry(entry)

    ledger = hmem.get_ledger()
    assert len(ledger) == 1
    assert ledger[0].decision_id == "DEC_001"


def test_mcp_handler(tmp_path: Path):
    ledger_file = tmp_path / "test_ledger.json"
    hmem = MeterlessHMEM(storage_path=ledger_file)

    # List tools
    req_list = {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}
    resp_list = handle_request(hmem, req_list)
    assert "result" in resp_list
    tool_names = [t["name"] for t in resp_list["result"]["tools"]]
    assert "query_memory" in tool_names

    # Call query_memory
    req_call = {
        "jsonrpc": "2.0",
        "id": 2,
        "method": "tools/call",
        "params": {"name": "query_memory", "arguments": {"system_id": "ippoi"}},
    }
    resp_call = handle_request(hmem, req_call)
    assert "result" in resp_call
    assert "ippoi" in resp_call["result"]["content"][0]["text"].lower()
