"""ActiveSite — per-run agent trace.

Every agent action is one JSON line in ``logs/trace-<run_id>.jsonl`` and one
aligned line on stdout, so a judge can replay who did what, with which input,
with what confidence, and how many retries it took. ``on_event`` lets the web
UI stream the same entries live.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Optional

SUMMARY_LIMIT = 300


def _truncate(text: Any, limit: int = SUMMARY_LIMIT) -> str:
    s = "" if text is None else str(text)
    return s if len(s) <= limit else s[: limit - 1] + "…"


class Trace:
    def __init__(self, run_id: str, log_dir: Path | str = "logs",
                 on_event: Optional[Callable[[Dict[str, Any]], None]] = None, echo: bool = True):
        self.run_id = run_id
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.path = self.log_dir / f"trace-{run_id}.jsonl"
        self.on_event = on_event
        self.echo = echo
        self.entries: list[Dict[str, Any]] = []

    def log(self, agent_name: str, action: str, input_summary: Any, output_summary: Any, *,
            target_agent: Optional[str] = None, confidence: Optional[float] = None, retry_count: int = 0,
            status: str = "ok", molecule: Optional[str] = None, data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        entry = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "run_id": self.run_id,
            "agent_name": agent_name,
            "action": action,
            "input_summary": _truncate(input_summary),
            "output_summary": _truncate(output_summary),
            "target_agent": target_agent,
            "confidence": None if confidence is None else float(confidence),
            "retry_count": int(retry_count),
            "status": status,
            "molecule": molecule,
            "data": data if data is not None else None,
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, default=str) + "\n")
        self.entries.append(entry)
        if self.echo:
            conf = "" if confidence is None else f" conf={float(confidence):.2f}"
            retry = "" if not retry_count else f" retry={int(retry_count)}"
            print(f"[{self.run_id}] {agent_name:<10} {action:<20} {status:<7}{conf}{retry} {entry['output_summary'][:100]}")
        if self.on_event is not None:
            try:
                self.on_event(entry)
            except Exception:  # a UI listener must never break the run
                pass
        return entry
