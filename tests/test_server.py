"""FastAPI endpoints with the orchestrator monkeypatched: run/stream/result, judge endpoint, memory reset."""
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
                   "Reset memory", "/run/stream", "not computed", "traceLink", "Pipeline"):
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
