"""Meterless H-MEM conformance vectors, run against activesite.memory.hmem.

One pytest case per vector in tests/fixtures/meterless_hmem_vectors.json (an
unmodified upstream copy, see meterless_NOTICE.md). Each section function
applies the same assertions as upstream engines/hmem/conformance/runner.ts
(commit 0aa7417). The clock is fixed at the vectors' ``clock`` value (epoch ms).

Translation notes (TypeScript runner -> our Python surface):
- ``hmem.add({...})`` -> ``HMEM.add(...)``, returning the stored row dict
  (``accessCount`` is ``access_count``).
- The runner sets ``supersededBy`` by mutating the returned object; our rows
  live in SQLite, so the test writes the same field through ``store.update``.
- Lineage fields (``supersededBy``, ``derivedFrom``) live in the row's ``extra``.
"""
import json
from pathlib import Path

import pytest

from activesite.memory.hmem import HMEM

VECTORS = json.loads((Path(__file__).parent / "fixtures" / "meterless_hmem_vectors.json").read_text())
T0 = VECTORS["clock"]
DAY_MS = 24 * 60 * 60 * 1000
CASES = [(section, case) for section, cases in VECTORS["sections"].items() for case in cases]


def approx(a, b, eps=1e-9):
    return a is not None and abs(a - b) < eps


def make(tmp_path, clock):
    return HMEM(tmp_path / "hmem.sqlite", tmp_path / "hmem_ledger.jsonl", clock=clock)


def ids(mems):
    return sorted(m["id"] for m in mems)


# ------------------------------------------------------------------ sections
def record_validation(c, tmp_path):
    hmem = make(tmp_path, lambda: T0)
    rejected = False
    try:
        hmem.add(c["input"]["content"], source=c["input"]["source"])
    except Exception:
        rejected = True
    assert rejected == (c["expect"] == "reject"), f"expected {c['expect']}, got {'reject' if rejected else 'accept'}"


def feedback_deltas(c, tmp_path):
    hmem = make(tmp_path, lambda: T0)
    m = hmem.add("feedback target record", confidence=c["start"], source="conformance")
    access_before = m["access_count"]
    hmem.feedback(m["id"], c["kind"])
    after = hmem.store.get(m["id"])
    assert approx(after["confidence"], c["expectConfidence"]), \
        f"confidence {after['confidence']}, expected {c['expectConfidence']}"
    if "expectAccessDelta" in c:
        delta = after["access_count"] - access_before
        assert delta == c["expectAccessDelta"], f"accessCount delta {delta}, expected {c['expectAccessDelta']}"
    if c.get("expectTag"):
        assert c["expectTag"] in after["tags"], f"missing tag {c['expectTag']}"


def ranking_order(c, tmp_path):
    hmem = make(tmp_path, lambda: T0)
    by_key = {r["key"]: hmem.add(r["content"], confidence=r["confidence"], layer=r["layer"], source="conformance")
              for r in c["records"]}
    for r in c["records"]:
        if r.get("supersededByKey"):
            old = by_key[r["key"]]
            hmem.store.update(old["id"], "conformance",
                              extra={**old["extra"], "supersededBy": by_key[r["supersededByKey"]]["id"]})
    result = hmem.query(c["query"], threshold=0, top_n=10)
    order = [h["memory"]["id"] for h in result]
    expected = [by_key[k]["id"] for k in c["expectOrder"]]

    def index(x):  # JS indexOf semantics: -1 when absent
        return order.index(x) if x in order else -1

    for i in range(len(expected) - 1):
        assert index(expected[i]) < index(expected[i + 1]), \
            f"expected {c['expectOrder'][i]} before {c['expectOrder'][i + 1]}, got {order}"


def sleep_guardrails(c, tmp_path):
    now = {"t": T0}
    hmem = make(tmp_path, lambda: now["t"])
    by_key = {r["key"]: hmem.add(r["content"], source=r["source"], derived_from=r.get("derivedFrom"))
              for r in c["records"]}
    now["t"] = T0 + c["ageDays"] * DAY_MS
    before = json.dumps(ids(hmem.store.all()))
    preview = hmem.sleep.preview()
    assert json.dumps(ids(hmem.store.all())) == before, "preview mutated the store"
    for k in c["expectArchived"]:
        assert by_key[k]["id"] in preview["toArchive"], f"{k} should be archivable"
    for k in c["expectProtected"]:
        assert by_key[k]["id"] not in preview["toArchive"], f"{k} is guardrail-protected and must not archive"
    report = hmem.sleep.execute(preview)
    for k in c["expectProtected"]:
        assert hmem.store.get(by_key[k]["id"]) is not None, f"{k} was deleted despite guardrails"
    assert isinstance(report["backupId"], str) and len(report["backupId"]) > 0, "execute must return a backupId"


def conflict_gate(c, tmp_path):
    hmem = make(tmp_path, lambda: T0)
    a = hmem.add(c["a"]["content"], confidence=c["a"]["confidence"], source="conformance")
    b = hmem.add(c["b"]["content"], confidence=c["b"]["confidence"], source="conformance")
    found = hmem.conflicts.scan()
    assert len(found) > 0, "opposing always/never pair on similar content must be detected"
    outcome = hmem.conflicts.auto_resolve(found[0])
    assert outcome in ("resolved", "queued"), f"outcome must be resolved or queued, got {outcome}"
    if outcome == "resolved":
        loser = [m for m in (hmem.store.get(a["id"]), hmem.store.get(b["id"]))
                 if m and (m["extra"] or {}).get("supersededBy")]
        assert loser, "resolved conflicts must mark the loser supersededBy"
    assert hmem.store.get(a["id"]) and hmem.store.get(b["id"]), "conflict resolution must never delete records"


def ledger_audit(c, tmp_path):
    hmem = make(tmp_path, lambda: T0)
    m = hmem.add("audited record", confidence=c["start"], source="conformance")
    hmem.feedback(m["id"], c["kind"])
    history = hmem.ledger.history(m["id"])
    actions = [h["action"] for h in history]
    assert json.dumps(actions) == json.dumps(c["expectActions"]), f"actions {actions}, expected {c['expectActions']}"
    fb = history[-1]
    prev = (fb.get("previousState") or {}).get("confidence")
    new = (fb.get("newState") or {}).get("confidence")
    assert approx(prev, c["expectPrev"]), f"previousState.confidence {prev}, expected {c['expectPrev']}"
    assert approx(new, c["expectNew"]), f"newState.confidence {new}, expected {c['expectNew']}"


def dream_boundary(c, tmp_path):
    hmem = make(tmp_path, lambda: T0)
    for r in c["records"]:
        hmem.add(r["content"], type=r["type"], source="conformance")
    count_before = len(hmem.store.all())
    proposals = hmem.dreaming.dream()
    assert len(proposals) > 0, "two related preferences must produce at least one proposal"
    assert len(hmem.store.all()) == count_before, "dreaming must not materialize anything before approval"
    created = hmem.dreaming.approve(proposals[0]["id"])
    if created:
        assert created["layer"] == "long_term", "approved proposals materialize as long_term"
        assert len((created["extra"] or {}).get("derivedFrom") or []) > 0, "approved proposals carry derivedFrom lineage"


SECTION_RUNNERS = {
    "record-validation": record_validation,
    "feedback-deltas": feedback_deltas,
    "ranking-order": ranking_order,
    "sleep-guardrails": sleep_guardrails,
    "conflict-gate": conflict_gate,
    "ledger-audit": ledger_audit,
    "dream-boundary": dream_boundary,
}


def test_vector_file_shape():
    # Guards against a silently truncated fixture: 13 vectors in 7 sections, all ids unique.
    assert set(VECTORS["sections"]) == set(SECTION_RUNNERS)
    all_ids = [c["id"] for _, c in CASES]
    assert len(all_ids) == 13 and len(set(all_ids)) == 13


@pytest.mark.parametrize("section,case", CASES, ids=[c["id"] for _, c in CASES])
def test_conformance_vector(section, case, tmp_path):
    SECTION_RUNNERS[section](case, tmp_path)
