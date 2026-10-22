"""Tests for activesite.trace.Trace."""
import json

from activesite.trace import Trace


def test_trace_writes_jsonl_and_calls_on_event(tmp_path, capsys):
    seen = []
    t = Trace("20261022-120000-abc123", tmp_path, on_event=seen.append)
    e1 = t.log("Planner", "plan", {"case": "ippoi_site_a"}, "6 steps", confidence=0.9, molecule="ippoi")
    e2 = t.log("Runner", "run_qmmm", "attempt 0", "x" * 500, target_agent="Critic", retry_count=1, status="failed",
               data={"exit_code": 1})
    assert t.path == tmp_path / "trace-20261022-120000-abc123.jsonl"
    lines = t.path.read_text().splitlines()
    assert len(lines) == 2
    rows = [json.loads(l) for l in lines]
    keys = ["ts", "run_id", "agent_name", "action", "input_summary", "output_summary", "target_agent", "confidence",
            "retry_count", "status", "molecule", "data"]
    assert all(list(r.keys()) == keys for r in rows)
    assert rows[0]["agent_name"] == "Planner" and rows[0]["confidence"] == 0.9 and rows[0]["molecule"] == "ippoi"
    assert rows[1]["status"] == "failed" and rows[1]["retry_count"] == 1 and rows[1]["target_agent"] == "Critic"
    assert len(rows[1]["output_summary"]) == 300 and rows[1]["output_summary"].endswith("…")
    assert rows[1]["data"] == {"exit_code": 1}
    assert seen == [e1, e2]
    out = capsys.readouterr().out.splitlines()
    assert len(out) == 2 and "Planner" in out[0] and "retry=1" in out[1]


def test_trace_survives_bad_listener(tmp_path):
    def boom(entry):
        raise RuntimeError("ui died")

    t = Trace("r1", tmp_path, on_event=boom, echo=False)
    t.log("Critic", "precheck", "in", "out")
    assert len(t.path.read_text().splitlines()) == 1
