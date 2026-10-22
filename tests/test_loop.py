"""Tests for the retry loop with the engine mocked at the subprocess boundary (odd fixture, then ok fixture)."""
import json
import subprocess
from pathlib import Path

import pytest

from activesite.agent import orchestrator
from activesite.agent.core import ALLOWED_STEPS, DataScout, NullAdapter, Planner
from activesite.chem import sander
from activesite.memory.hmem import MemoryStoreService
from activesite.trace import Trace

FIX = Path(__file__).parent / "fixtures"
REF = Path("data/reference/qmmm_dft")
pytestmark = pytest.mark.skipif(not (REF / "step3_pbcsetup.parm7").exists(), reason="reference files missing")


class FakeDocker:
    """subprocess.run stand-in: docker info/inspect succeed; each docker run writes the next fixture as sp.out."""

    def __init__(self, outputs):
        self.outputs = list(outputs)
        self.runs = []

    def __call__(self, cmd, capture_output=True, text=True, timeout=None, **kw):
        if cmd[:2] == ["docker", "run"]:
            work = Path(cmd[cmd.index("-v", cmd.index("-v") + 1) + 1].split(":")[0])
            fixture = self.outputs.pop(0)
            (work / "sp.out").write_text((FIX / fixture).read_text())
            self.runs.append((work, fixture))
            return subprocess.CompletedProcess(cmd, 0 if fixture == "sander_ok.out" else 1, stdout="", stderr="")
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")


@pytest.fixture
def fake_docker(monkeypatch):
    fake = FakeDocker(["sander_odd.out", "sander_ok.out", "sander_ok.out"])
    monkeypatch.setattr(sander.subprocess, "run", fake)
    monkeypatch.setattr(sander.shutil, "which", lambda name: "/usr/bin/docker")
    return fake


def test_cold_then_warm_run(tmp_path, fake_docker):
    db, ledger, logs, runs = tmp_path / "hmem.sqlite", tmp_path / "ledger.jsonl", tmp_path / "logs", tmp_path / "runs"
    events = []
    cold = orchestrator.run_case("ippoi_site_a", hmem_db=db, ledger_path=ledger, on_event=events.append,
                                 workroot=runs, log_dir=logs, sample_mode=False, echo=False)
    assert cold["retries"] == 1 and cold["memory_used"] is False and cold["qm_ok"] is True
    assert cold["qmcharge"] == 1 and cold["memory_written"] is not None
    assert cold["qm_escf_kcal"] == pytest.approx(-1442.3127) and cold["model_mode"] == "fallback"
    assert [f for _, f in fake_docker.runs] == ["sander_odd.out", "sander_ok.out"]
    assert fake_docker.runs[0][0].name == "attempt0" and fake_docker.runs[1][0].name == "attempt1"

    store = MemoryStoreService(db, ledger)
    mems = store.all()
    assert len(mems) == 1 and mems[0]["extra"]["rule"] == "mm_partial_sum"
    assert set(mems[0]["tags"]) == {"qm-charge", "nucleotide-cut", "mg-phosphodiester"}
    assert mems[0]["source"] == f"critic:sander-retry run={cold['run_id']}"

    trace_lines = [json.loads(l) for l in Path(cold["trace"]).read_text().splitlines()]
    agents = {e["agent_name"] for e in trace_lines}
    assert {"Planner", "DataScout", "Setup", "Critic", "Runner", "Explainer"} <= agents
    assert len(events) == len(trace_lines)
    assert any(e["action"] == "remember" for e in trace_lines)

    cards = json.loads(Path(cold["cards"]).read_text())
    q = next(c for c in cards if c["decision_id"] == "DEC_QMCHARGE")
    assert q["alternatives"] and "qmcharge +0" in q["alternatives"][0]["name"]
    assert "odd" in q["alternatives"][0]["rejected_reason"]
    assert "First attempt rejected" in q["rationale"] and q["evidence"]["source"] == "sander validation + H-MEM"
    assert q["evidence"]["attempts"] == [{"attempt": 0, "charge": 0, "ok": False, "odd_electrons": 203},
                                         {"attempt": 1, "charge": 1, "ok": True, "odd_electrons": None}]
    assert all(0.0 <= c["confidence"] <= 1.0 for c in cards)
    assert {c["confidence"] for c in cards if c["category"] == "residue_inclusion"} != {0.96}
    report = Path(cold["report"]).read_text()
    assert "converged" in report and "no expert record" in report and cold["run_id"] in report

    warm = orchestrator.run_case("ippoi_site_b", hmem_db=db, ledger_path=ledger, workroot=runs, log_dir=logs,
                                 sample_mode=False, echo=False)
    assert warm["retries"] == 0 and warm["memory_used"] is True and warm["qm_ok"] is True
    assert warm["qmcharge"] == 1 and "recalled from H-MEM" in warm["charge_rule"]
    assert len(store.all()) == 1                       # nothing new learned on the warm run
    actions = [e["action"] for e in store.read_ledger()]
    assert actions == ["create", "read"]               # the warm Setup read the cold Critic's memory
    assert [f for _, f in fake_docker.runs][-1] == "sander_ok.out" and len(fake_docker.runs) == 3


def test_sample_mode_loop_is_honest(tmp_path, monkeypatch):
    # This test is about the EMPTY-cache state; point sample mode at a dir with no cached outputs so it does not
    # depend on whether data/sample/ has been generated in this checkout.
    monkeypatch.setenv("ACTIVESITE_SAMPLE_DIR", str(tmp_path / "no-sample"))
    st = orchestrator.run_case("ippoi_site_a", hmem_db=tmp_path / "h.sqlite", ledger_path=tmp_path / "l.jsonl",
                               workroot=tmp_path / "runs", log_dir=tmp_path / "logs", sample_mode=True, echo=False)
    assert st["qm_ok"] is False and st["engine_skipped"] is True and st["retries"] == 0
    assert st["qm_escf_kcal"] is None and "SAMPLE_MODE" in st["errors"][0]
    assert "FAILED" in Path(st["report"]).read_text() and "null" in Path(st["report"]).read_text()
    assert not (tmp_path / "h.sqlite").exists() or MemoryStoreService(tmp_path / "h.sqlite", tmp_path / "l.jsonl").all() == []


def test_planner_allow_list(tmp_path):
    trace = Trace("t", tmp_path, echo=False)

    class LLM:
        def __init__(self, payload):
            self.payload = payload

        def plan_json(self, case):
            return self.payload

    assert Planner(None, trace).plan({"id": "x"})["mode"] == "fallback"
    full = Planner(LLM({"steps": ALLOWED_STEPS + ["rm -rf"], "theory": "pm6"}), trace).plan({"id": "x"})
    assert full["mode"] == "model" and full["dropped"] == ["rm -rf"] and full["theory"] == "PM6"
    partial = Planner(LLM({"steps": ["explain"], "theory": "B3LYP"}), trace).plan({"id": "x"})
    assert partial["mode"] == "fallback" and partial["steps"] == ALLOWED_STEPS and partial["theory"] == "PM6"


def test_datascout_validates_ids(tmp_path):
    scout = DataScout(NullAdapter(), Trace("t", tmp_path, echo=False))
    out = scout.gather({"system": "ippoi_wt", "site": "A"})
    assert out["expert"] is None and out["analogy"] == [] and out["label"] == "no-catalog"
    assert "ippoi_wt" in out["sql"]["q1_expert"] and "site = 'A'" in out["sql"]["q1_expert"]
    with pytest.raises(ValueError):
        scout.gather({"system": "ippoi'; DROP TABLE lab_runs; --", "site": "A"})
    with pytest.raises(ValueError):
        scout.gather({"system": "ippoi_wt", "site": "A' OR 1=1"})
