"""FastAPI endpoints with the orchestrator monkeypatched: run/stream/result, judge endpoint, memory reset."""
import re
import json
import time

import pytest
from fastapi.testclient import TestClient

from activesite.memory.meterless import MeterlessHMEM
from activesite.models import DecisionCard, DecisionCategory
from activesite.server import main as server


def fake_run_case(case_id, store=None, on_event=None, sample_mode=None, echo=False, **kw):
    for agent, action, target in (("Planner", "plan", "DataScout"), ("Runner", "run_qmmm", "Critic"), ("Explainer", "report", None)):
        if on_event is None:
            continue
        on_event({"ts": "2026-10-22T12:00:00+00:00", "run_id": "r-test", "agent_name": agent, "action": action,
                  "input_summary": "x", "output_summary": f"{action} done", "target_agent": target, "confidence": None,
                  "retry_count": 0, "status": "ok", "molecule": None, "data": None})
        time.sleep(0.01)
    store.add("qm charge rule learned", "rule", "long_term", ["qm-charge"], source="test", agent_id="Critic", run_id="r-test")
    card = DecisionCard(decision_id="DEC_QMCHARGE", category=DecisionCategory.CHARGE_AND_SPIN, target="qmcharge",
                        choice="+1", rationale="mm sum", confidence=0.9, evidence={"source": "test"})
    return {"run_id": "r-test", "case": case_id, "kind": "metal", "retries": 1, "memory_used": False, "qm_ok": True,
            "qm_escf_kcal": -456.5628, "engine_time_s": 36.9, "engine_label": "sander in Docker", "model_mode": "fallback",
            "model_calls": 0, "qmcharge": 1, "errors": [], "catalog": "no-catalog", "trace": "logs/trace-r-test.jsonl",
            "sql": {"q1_expert": "SELECT 1"}, "checks": [], "validation": {}, "_cards": [card],
            "_result": {"ok": True, "qm_escf_kcal": -456.5628, "total_energy_kcal": -302060.0, "command": ["docker"]},
            "_report_markdown": "# report", "_setup": {}}


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "run_case", fake_run_case)
    monkeypatch.setattr(server, "hmem", MeterlessHMEM(db_path=tmp_path / "h.sqlite", ledger_path=tmp_path / "l.jsonl"))
    monkeypatch.delenv("MODEL_API_KEY", raising=False)
    monkeypatch.delenv("NVIDIA_API_KEY", raising=False)
    server.runs.clear()
    return TestClient(server.app)


def _events(client, stream_id, path="/api/stream/{sid}"):
    events = []
    with client.stream("GET", path.format(sid=stream_id)) as r:
        assert r.status_code == 200 and r.headers["content-type"].startswith("text/event-stream")
        name = None
        for line in r.iter_lines():
            if line.startswith("event: "):
                name = line[7:]
            elif line.startswith("data: "):
                events.append((name, json.loads(line[6:])))
                if name in ("result", "error"):
                    break
    return events


def test_dashboard_html(client):
    resp = client.get("/")
    assert resp.status_code == 200
    for needle in ("ActiveSite", "Track 02", "catalog-STANDIN (DuckDB)", "What the system remembers", "SQL sent through the data layer",
                   "Reset memory", "/run/stream", "not computed", "traceLink", "Pipeline", "3D Structure", "3Dmol.js Active",
                   "Interactive 3D Molecular Viewer", "marked.min.js", "3Dmol-min.js"):
        assert needle in resp.text
    assert "Zetaris MCP" not in resp.text


def test_api_cases(client):
    data = client.get("/api/cases").json()
    ids = [c["id"] for c in data["cases"]]
    assert {"egfr_erlotinib", "ippoi_site_a", "ippoi_site_b"} <= set(ids)
    assert next(c for c in data["cases"] if c["id"] == "egfr_erlotinib")["kind"] == "ligand"


def test_run_returns_stream_then_steps_then_result(client):
    resp = client.post("/api/run", json={"case_id": "ippoi_site_a", "sample_mode": True})
    assert resp.status_code == 200
    sid = resp.json()["stream_id"]
    assert sid.startswith("stream_") and resp.json()["case_id"] == "ippoi_site_a"
    events = _events(client, sid)
    names = [n for n, _ in events]
    assert names[:3] == ["step", "step", "step"] and names[-1] == "result"
    steps = [d for n, d in events if n == "step"]
    assert [s["agent_name"] for s in steps] == ["Planner", "Runner", "Explainer"]
    assert steps[0]["target_agent"] == "DataScout" and steps[0]["ts"].startswith("2026-")
    result = events[-1][1]
    assert result["stats"]["qm_escf_kcal"] == pytest.approx(-456.5628) and result["stats"]["engine_label"] == "sander in Docker"
    assert result["cards"][0]["decision_id"] == "DEC_QMCHARGE" and "command" not in result["result"]
    assert result["sql"] == {"q1_expert": "SELECT 1"} and not any(k.startswith("_") for k in result["stats"])
    # the alias used by the UI replays the same events
    assert [n for n, _ in _events(client, sid, "/run/stream?stream_id={sid}")][-1] == "result"


def test_run_by_prompt_and_errors(client):
    sid = client.post("/api/run", json={"prompt": "Set up EGFR kinase with erlotinib (PDB 1M17)"}).json()
    assert sid["case_id"] == "egfr_erlotinib"
    assert client.post("/api/run", json={}).status_code == 400
    assert client.post("/api/run", json={"case_id": "nope"}).status_code == 404
    assert client.post("/api/run", json={"prompt": "make me a sandwich"}).status_code == 400
    assert _events(client, "stream_missing")[0][0] == "error"


def test_judge_endpoint_matches_cli_json_shape(client):
    data = client.post("/run", json={"case_id": "ippoi_site_a"}).json()
    for key in ("run_id", "case", "retries", "memory_used", "qm_ok", "qm_escf_kcal", "engine_time_s", "model_calls", "model_mode", "trace"):
        assert key in data
    assert not any(k.startswith("_") for k in data)


def test_ledger_and_memory_reset(client):
    client.post("/run", json={"case_id": "ippoi_site_a"})
    led = client.get("/api/ledger").json()
    assert len(led["memories"]) == 1 and led["ledger_total"] == 1 and led["ledger"][0]["action"] == "create"
    r = client.post("/api/memory/reset").json()
    assert len(r["removed"]) == 2 and r["memories"] == 0 and r["ledger"] == 0
    led = client.get("/api/ledger").json()
    assert led["memories"] == [] and led["ledger"] == []


def test_chat_endpoint_validation_and_explanations(client):
    # Empty message rejection
    assert client.post("/api/chat", json={"message": ""}).status_code == 400
    assert client.post("/api/chat", json={"message": "   "}).status_code == 400

    # Pill 1: Erlotinib neutrality
    r1 = client.post("/api/chat", json={"message": "Why was erlotinib kept neutral?"}).json()
    assert "reply" in r1 and "neutral" in r1["reply"] and "Met769" in r1["reply"]

    # Pill 2: 1.0 fs time step and thermostat
    r2 = client.post("/api/chat", json={"message": "Explain the QM/MM MD 1.0 fs time step & thermostat"}).json()
    assert "1.0 fs" in r2["reply"] and "Langevin" in r2["reply"]

    # Pill 3: I-PpoI radical mismatch
    r3 = client.post("/api/chat", json={"message": "How did Critic diagnose and fix the I-PpoI radical mismatch?"}).json()
    assert "I-PpoI" in r3["reply"] and "203" in r3["reply"] and "Critic" in r3["reply"]

    # Pill 4: H-MEM memory ledger
    r4 = client.post("/api/chat", json={"message": "What does the H-MEM memory ledger store?"}).json()
    assert "H-MEM" in r4["reply"] and "ledger" in r4["reply"]

    # Casual greeting
    r_hello = client.post("/api/chat", json={"message": "hello"}).json()
    assert "AI Biochemist" in r_hello["reply"] and "Protonation" in r_hello["reply"]

    # Open inquiry: "what did you find?"
    r_findings = client.post("/api/chat", json={"message": "what did you find?"}).json()
    assert "Summary" in r_findings["reply"] and "ESCF" in r_findings["reply"] and "Met769" in r_findings["reply"]

    # Specific biochemical inquiry: Met769 contact
    r_met = client.post("/api/chat", json={"message": "what happened to Met769?"}).json()
    assert "Met769" in r_met["reply"] and r_met["unverified_numbers"] == []

    # Multi-turn history support
    r_hist = client.post("/api/chat", json={
        "message": "can you elaborate?",
        "history": [{"role": "user", "content": "hello"}, {"role": "assistant", "content": "hi"}]
    }).json()
    assert "reply" in r_hist and len(r_hist["reply"]) > 20


def test_chat_endpoint_nemotron_mode(client, monkeypatch):
    monkeypatch.setattr(server.ModelClient, "available", True)
    monkeypatch.setattr(server.ModelClient, "chat", lambda self, msgs, **kw: "Mocked Nemotron: neutral Erlotinib and Met769 contact verified.")
    r = client.post("/api/chat", json={"message": "Why was erlotinib kept neutral?"}).json()
    assert r["source"] == "nemotron"
    assert "Mocked Nemotron" in r["reply"]


def test_chimerax_launch_endpoint(client, tmp_path, monkeypatch):
    # 404 for missing file
    assert client.post("/api/chimerax/launch", json={"run_id": "nonexistent"}).status_code == 404

    # Create dummy script
    script = tmp_path / "trajectory.cxc"
    script.write_text("open complex.pdb\nopen traj.nc format amber structureModel #1\n")

    class FakeProc:
        pid = 12345

    monkeypatch.setattr(server.subprocess, "Popen", lambda *a, **kw: FakeProc())
    monkeypatch.setattr(server.shutil, "which", lambda cmd: f"/mock/bin/{cmd}")

    resp = client.post("/api/chimerax/launch", json={"script_path": str(script)})
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "launched" and data["pid"] == 12345

    # Instant 1-click fallback launch when no run has completed yet
    fallback_resp = client.post("/api/chimerax/launch", json={})
    assert fallback_resp.status_code == 200
    assert fallback_resp.json()["status"] == "launched"
    assert "trajectory.cxc" in fallback_resp.json()["script_path"]


def test_run_with_md_toggle(client):
    resp = client.post("/api/run", json={"case_id": "egfr_erlotinib", "sample_mode": True, "md": True})
    assert resp.status_code == 200
    assert resp.json()["md"] is True


def test_get_structure_endpoint(client):
    # EGFR structure
    r_egfr = client.get("/api/structure/egfr_erlotinib")
    assert r_egfr.status_code == 200
    assert "chemical/x-pdb" in r_egfr.headers.get("content-type", "")
    assert "ATOM" in r_egfr.text

    # I-PpoI structure
    r_ippoi = client.get("/api/structure/ippoi_site_b")
    assert r_ippoi.status_code == 200
    assert "ATOM" in r_ippoi.text

    # TEM-1 is an unsupported case with no structure in the repo: 404, never another protein instead
    assert client.get("/api/structure/tem1_penicillin").status_code == 404

    # Missing structure
    r_404 = client.get("/api/structure/completely_nonexistent_pdb")
    assert r_404.status_code == 404


def test_chat_explain_previous_run_and_accuracy(client):
    # Explanation is built from the recorded site B run, not typed-in text
    r_b = client.post("/api/chat", json={"message": "Can you explain the result of my previous run to me? What does it implies and how accurate is it?", "run_id": "ippoi_site_b"}).json()
    reply = r_b["reply"]
    assert "I-PpoI endonuclease site B" in reply
    assert "-511.3637 kcal/mol" in reply and "Critic checks" in reply
    assert r_b["unverified_numbers"] == []


def test_chat_tem1_beta_lactamase_inquiry(client):
    # TEM-1 has no case file and was never run: the answer must say so and quote no results
    r = client.post("/api/chat", json={"message": "Set up a QM/MM model for TEM-1 beta-lactamase Ser70 acylation"}).json()
    assert "TEM-1 beta-lactamase" in r["reply"] and "no calculation has been run" in r["reply"]
    assert not re.search(r"\d+(\.\d+)?\s*kcal", r["reply"])


def test_chat_ecorv_endonuclease_inquiry(client):
    # EcoRV has no case file and was never run: the answer must say so and quote no results
    r = client.post("/api/chat", json={"message": "Set up a QM/MM model for EcoRV endonuclease (PDB 1RVA) with Mg2+"}).json()
    assert "EcoRV endonuclease (PDB 1RVA)" in r["reply"] and "no calculation has been run" in r["reply"]
    assert not re.search(r"\d+(\.\d+)?\s*kcal", r["reply"])


def test_chat_energy_decomposition_and_positive_escf(client):
    r = client.post("/api/chat", json={"message": "Why is ESCF positive while total energy is negative? Explain the energy decomposition and units."}).json()
    assert "reply" in r
    text = r["reply"]
    assert "heat of formation" in text.lower() or "δhf°" in text.lower()
    assert "positive" in text.lower()
    assert "Generalized Born" in text or "GB" in text
    assert "kcal/mol" in text


def test_chat_gmax_minimization_vs_scf_convergence(client):
    r = client.post("/api/chat", json={"message": "Explain what GMAX means versus SCF convergence."}).json()
    assert "reply" in r
    text = r["reply"]
    assert "GMAX" in text
    assert "10.0" in text
    assert "gradient" in text.lower() or "force" in text.lower()
    assert "density matrix" in text.lower() or "10^-7" in text


def test_chat_pocket_proximity_vs_steric_clash(client):
    r = client.post("/api/chat", json={"message": "Why did the pocket check pass with 2.72 Å against a limit of 4.0? Is that a clash?"}).json()
    assert "reply" in r
    text = r["reply"]
    assert "proximity" in text.lower() or "upper-bound" in text.lower()
    assert "4.0" in text
    assert "clash" in text.lower()
    assert "1.8" in text


def test_chat_abl_chain_and_his361_rationale(client):
    r_chain = client.post("/api/chat", json={"message": "Why did you choose Chain B over Chain A in 2HYY?"}).json()
    assert "reply" in r_chain
    assert "Chain B" in r_chain["reply"]
    assert "missing" in r_chain["reply"].lower()
    assert "REMARK 465" in r_chain["reply"]

    r_his = client.post("/api/chat", json={"message": "Explain why His361 was overridden from HIP to HIE in ABL kinase."}).json()
    assert "reply" in r_his
    assert "His361" in r_his["reply"]
    assert "HIE" in r_his["reply"]
    assert "cation" in r_his["reply"].lower() or "repulsion" in r_his["reply"].lower()


def test_chat_explain_previous_run_abl(client):
    # No ABL run is recorded in samples/: the answer must say so rather than quote numbers
    r = client.post("/api/chat", json={"message": "Can you explain the result of my previous run to me? What does it implies and how accurate is it?", "run_id": "abl_imatinib_a"}).json()
    assert "No run has been recorded" in r["reply"] or "ABL kinase + imatinib" in r["reply"]
    assert r["unverified_numbers"] == []


def test_get_structure_abl_and_ecorv(client):
    r_abl = client.get("/api/structure/abl_imatinib_a")
    assert r_abl.status_code == 200
    assert "ATOM" in r_abl.text

    # EcoRV is unsupported: no structure exists, so the endpoint must not serve a different protein
    assert client.get("/api/structure/ecorv_endonuclease").status_code == 404


def test_chat_conversational_greetings_and_how_are_you(client):
    r = client.post("/api/chat", json={"message": "how are you?"}).json()
    assert "reply" in r
    assert "doing well" in r["reply"].lower()
    assert "computational biochemistry" in r["reply"].lower()


def test_chat_sample_mode_inquiry(client):
    r = client.post("/api/chat", json={"message": "Why am I in sample mode? Is AI enabled in sample mode?"}).json()
    assert "reply" in r
    text = r["reply"]
    assert "YES! Absolutely" in text or "always 100% enabled" in text
    assert "Judge" in text
    assert "1.5 seconds" in text or "Amber" in text


def test_chat_explain_previous_run_ecorv(client):
    r = client.post("/api/chat", json={"message": "Can you explain the result of my previous run to me? What does it implies and how accurate is it?", "run_id": "ecorv_endonuclease"}).json()
    assert "not a supported case" in r["reply"] and "nothing to explain" in r["reply"]


