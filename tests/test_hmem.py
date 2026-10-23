"""Tests for activesite.memory.hmem: store, ledger and scored retrieval."""
import json
import time
from datetime import datetime, timedelta, timezone

import pytest

from activesite.memory.hmem import (
    THRESHOLD,
    MemoryRetrievalService,
    MemoryStoreService,
    query_tokens,
    tokenize,
)


@pytest.fixture
def store(tmp_path):
    return MemoryStoreService(tmp_path / "hmem.sqlite", tmp_path / "hmem_ledger.jsonl")


def _ledger(store):
    return [json.loads(l) for l in store.ledger_path.read_text().splitlines() if l.strip()]


def test_tokens():
    assert tokenize("The charges of nucleotides are cut, mg!") == ["charge", "nucleotide", "cut", "mg"]
    q = query_tokens("qm charge rule nucleotide phosphate cut mg partial charge sum extra words")
    assert q == ["qm", "charge", "rule", "nucleotide", "phosphate", "cut", "mg", "partial"]


def test_store_refuses_empty_source_and_bad_layer(store):
    with pytest.raises(ValueError, match="source"):
        store.add("rule", "fact", "long_term", ["t"], source="")
    with pytest.raises(ValueError, match="layer"):
        store.add("rule", "fact", "eternal", ["t"], source="x")
    assert store.all() == [] and not store.ledger_path.exists()


def test_add_clamps_confidence_and_writes_create_ledger(store):
    mid = store.add("qmcharge from MM partial sum", "rule", "long_term", ["qm-charge"], source="critic:test",
                    confidence=1.7, agent_id="Critic", run_id="run1", extra={"rule": "mm_partial_sum"})
    assert mid.startswith("mem_") and len(mid) == 14
    mem = store.get(mid)
    assert mem["confidence"] == 1.0 and mem["tags"] == ["qm-charge"] and mem["extra"] == {"rule": "mm_partial_sum"}
    assert mem["provenance"]["label"] == "Critic during run run1" and mem["provenance"]["origin"] == "tool"
    led = _ledger(store)
    assert len(led) == 1 and led[0]["action"] == "create" and led[0]["memoryId"] == mid
    assert led[0]["id"].startswith("led_") and isinstance(led[0]["timestamp"], int)
    assert led[0]["newState"]["id"] == mid and led[0]["actor"] == "Critic"


def test_retrieval_threshold_and_read_ledger(store):
    rs = MemoryRetrievalService(store)
    mid = store.add(
        "QM charge rule: when the mask cuts nucleotides at the phosphate, set qmcharge from the MM partial charge sum",
        "rule", "long_term", ["qm-charge", "nucleotide-cut", "mg-phosphodiester"], source="critic:sander-retry run=r0",
        confidence=0.9, agent_id="Critic", run_id="r0", extra={"rule": "mm_partial_sum"},
    )
    store.add("Erlotinib hinge contact is Met769 backbone NH", "fact", "long_term", ["ligand-pocket"],
              source="prep", confidence=0.9)
    hits = rs.retrieve("qm charge rule nucleotide phosphate cut mg partial charge sum",
                       tags=["qm-charge", "nucleotide-cut"], actor="Setup", run_id="r1")
    assert len(hits) == 1 and hits[0]["memory"]["id"] == mid
    assert hits[0]["score"] >= THRESHOLD
    parts = hits[0]["parts"]
    assert parts["keyword"] > 0 and parts["tag"] == pytest.approx(2 / 3, abs=1e-3) and parts["layer"] == 1.0
    assert store.get(mid)["access_count"] == 1
    led = _ledger(store)
    assert [e["action"] for e in led] == ["create", "create", "read"]
    assert led[-1]["memoryId"] == mid and led[-1]["actor"] == "Setup"
    assert led[-1]["details"]["score"] == hits[0]["score"] and led[-1]["details"]["query"].startswith("qm charge")

    # Below threshold: no keyword or tag overlap gives at most 0.25*confidence.
    assert rs.retrieve("completely unrelated words about weather", tags=[]) == []
    assert len(_ledger(store)) == 3  # no read line for a miss


def test_domain_tag_gate(store):
    rs = MemoryRetrievalService(store)
    store.add("qm charge rule nucleotide phosphate cut mg partial charge sum", "rule", "long_term",
              ["mg-phosphodiester"], source="critic", confidence=1.0)
    # Identical wording, but the query is tagged for another domain: never returned.
    assert rs.retrieve("qm charge rule nucleotide phosphate cut mg partial charge sum", tags=["ligand-pocket"]) == []
    assert len(rs.retrieve("qm charge rule nucleotide phosphate cut mg partial charge sum", tags=["mg-phosphodiester"])) == 1


def test_recency_and_layer_weights(store):
    rs = MemoryRetrievalService(store)
    mid = store.add("alpha beta gamma", "fact", "short_term", ["x"], source="s", confidence=1.0)
    old = (datetime.now(timezone.utc) - timedelta(days=28)).isoformat()
    store.con.execute("UPDATE memories SET last_accessed = ? WHERE id = ?", (old, mid))
    store.con.commit()
    parts = rs.score(store.get(mid), ["alpha", "beta", "gamma"], ["x"])
    assert parts["layer"] == 0.6 and parts["recency"] == pytest.approx(pow(2.718281828, -2), rel=1e-3)
    assert parts["score"] == pytest.approx(0.5 * 1 + 0.25 * 1 + 0.125 * 0.6 + 0.125 * parts["recency"], abs=1e-3)


def test_ledger_only_grows(store):
    rs = MemoryRetrievalService(store)
    sizes = [0]
    snapshots = [""]
    for i in range(3):
        store.add(f"rule number {i} about charge", "rule", "working", ["t"], source="s", confidence=0.9)
        rs.retrieve("rule number charge", tags=["t"])
        text = store.ledger_path.read_text()
        assert text.startswith(snapshots[-1])          # earlier lines are never rewritten
        assert len(text) > sizes[-1]
        sizes.append(len(text))
        snapshots.append(text)
    assert len(_ledger(store)) == 3 + 1 + 2 + 3     # 3 creates + reads of 1, 2, 3 hits
