"""ActiveSite — Meterless H-MEM facade.

Keeps the public API the Critic, the MCP server and ``/api/ledger`` already
use (``record_episode``, ``record_trust_entry``, ``query_memories``,
``recall_corrective_action``, ``get_ledger``) but stores everything through
``activesite.memory.hmem.MemoryStoreService`` (SQLite) and reads the
append-only JSONL ledger. A fresh store is empty; nothing is seeded.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from activesite.memory.hmem import MemoryStoreService

logger = logging.getLogger(__name__)

DEFAULT_DB_PATH = Path("data/memory/hmem.sqlite")
DEFAULT_LEDGER_PATH = Path("logs/hmem_ledger.jsonl")
EPISODE_TYPE = "episodic"


class EpisodicMemoryRecord(BaseModel):
    """An episodic memory entry capturing a state transition and learned lesson."""
    record_id: str
    system_id: str
    stage: str = Field(description="Stage: prep, partition, critic, runner")
    state_signature: str = Field(description="Hash or key representing system state")
    action_taken: str
    outcome: str = Field(description="'SUCCESS', 'FAILURE', 'SELF_CORRECTED'")
    error_type: Optional[str] = None
    diagnosed_cause: Optional[str] = None
    corrective_action: Optional[str] = None
    learned_rule: str
    trust_score: float = Field(default=0.85, ge=0.0, le=1.0)
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    metadata: Dict[str, Any] = Field(default_factory=dict)


class TrustLedgerEntry(BaseModel):
    """Trust ledger entry for auditing agent decisions and reproducibility."""
    entry_id: str
    decision_id: str
    system_id: str
    agent_name: str
    confidence: float
    verified: bool
    verifier_notes: str
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class MeterlessHMEM:
    """Facade over the H-MEM store for the episodic-record API."""

    def __init__(
        self,
        db_path: Optional[Path | str] = None,
        ledger_path: Optional[Path | str] = None,
        storage_path: Optional[Path | str] = None,
        endpoint_url: Optional[str] = None,
        api_key: Optional[str] = None,
    ):
        if storage_path is not None and db_path is None:
            # Backwards compatibility: an old JSON path maps to a sibling SQLite db + ledger.
            sp = Path(storage_path)
            db_path = sp.with_suffix(".sqlite")
            ledger_path = ledger_path or sp.parent / "hmem_ledger.jsonl"
        self.db_path = Path(db_path or DEFAULT_DB_PATH)
        self.ledger_path = Path(ledger_path or DEFAULT_LEDGER_PATH)
        self.endpoint_url = endpoint_url or os.getenv("METERLESS_ENDPOINT", "")
        self.api_key = api_key or os.getenv("METERLESS_API_KEY", "")
        self.store = MemoryStoreService(self.db_path, self.ledger_path)

    # ------------------------------------------------------------ writes
    def record_episode(self, record: EpisodicMemoryRecord) -> str:
        """Store an episodic record as a long-term H-MEM memory tagged with its system and error type."""
        tags = [record.system_id, record.stage, record.outcome]
        if record.error_type:
            tags.append(record.error_type)
        return self.store.add(
            content=record.learned_rule, type=EPISODE_TYPE, layer="long_term", tags=tags,
            source=f"{record.stage}:{record.record_id}", confidence=record.trust_score,
            agent_id=record.stage, run_id=record.record_id, origin="episode",
            extra={"record": record.model_dump()},
        )

    def record_trust_entry(self, entry: TrustLedgerEntry) -> None:
        self.store.ledger("trust", entry.decision_id, entry.agent_name, entry.model_dump(),
                          new_state={"verified": entry.verified, "confidence": entry.confidence})

    # ------------------------------------------------------------- reads
    def _records(self) -> List[EpisodicMemoryRecord]:
        out = []
        for mem in self.store.all():
            if mem.get("type") != EPISODE_TYPE:
                continue
            raw = (mem.get("extra") or {}).get("record")
            if raw:
                try:
                    out.append(EpisodicMemoryRecord(**raw))
                except Exception as exc:  # malformed extra; skip rather than guess
                    logger.warning("skipping memory %s: %s", mem.get("id"), exc)
        return out

    def query_memories(
        self,
        system_id: Optional[str] = None,
        stage: Optional[str] = None,
        error_type: Optional[str] = None,
        keywords: Optional[List[str]] = None,
    ) -> List[EpisodicMemoryRecord]:
        results = []
        for r in self._records():
            if system_id and system_id.lower() not in r.system_id.lower():
                continue
            if stage and r.stage.lower() != stage.lower():
                continue
            if error_type and (r.error_type or "").lower() != error_type.lower():
                continue
            if keywords:
                corpus = f"{r.learned_rule} {r.action_taken} {r.diagnosed_cause or ''}".lower()
                if not any(kw.lower() in corpus for kw in keywords):
                    continue
            results.append(r)
        return results

    def recall_corrective_action(self, system_class_tag: str, error_type: str) -> Optional[EpisodicMemoryRecord]:
        """Exact tag match AND error type, outcome SELF_CORRECTED, highest trust. No fallback."""
        candidates = []
        for mem in self.store.all():
            if mem.get("type") != EPISODE_TYPE or system_class_tag not in (mem.get("tags") or []):
                continue
            raw = (mem.get("extra") or {}).get("record") or {}
            if raw.get("error_type") == error_type and raw.get("outcome") == "SELF_CORRECTED" and raw.get("corrective_action"):
                candidates.append((float(mem.get("confidence") or 0.0), mem["id"], raw))
        if not candidates:
            return None
        candidates.sort(key=lambda c: c[0], reverse=True)
        _, mem_id, raw = candidates[0]
        self.store.touch(mem_id)
        self.store.ledger("read", mem_id, "recall_corrective_action",
                          {"system_class_tag": system_class_tag, "error_type": error_type})
        return EpisodicMemoryRecord(**raw)

    def get_ledger(self) -> List[TrustLedgerEntry]:
        out = []
        for e in self.store.read_ledger():
            if e.get("action") == "trust" and isinstance(e.get("details"), dict):
                try:
                    out.append(TrustLedgerEntry(**e["details"]))
                except Exception:
                    continue
        return out

    def ledger_entries(self) -> List[Dict[str, Any]]:
        """Every raw ledger line (create/read/trust), for the UI."""
        return self.store.read_ledger()
