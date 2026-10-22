"""ActiveSite — Meterless H-MEM (Hierarchical Episodic Memory & Trust Ledger).

Implements persistent episodic learning with Markovian state transitions and trust ledger tracking
for QM/MM simulation choices and error self-correction.
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

DEFAULT_LEDGER_PATH = Path("data/memory/meterless_ledger.json")


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
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
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
    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


class MeterlessHMEM:
    """Meterless Hierarchical Episodic Memory (H-MEM) Manager.

    Provides episodic memory retrieval, Markovian state transition evaluation,
    and trust auditing with zero external API key requirements in offline mode.
    """

    def __init__(
        self,
        storage_path: Optional[Path] = None,
        endpoint_url: Optional[str] = None,
        api_key: Optional[str] = None,
    ):
        self.storage_path = storage_path or DEFAULT_LEDGER_PATH
        self.endpoint_url = endpoint_url or os.getenv("METERLESS_ENDPOINT", "")
        self.api_key = api_key or os.getenv("METERLESS_API_KEY", "")
        self._memory_records: List[EpisodicMemoryRecord] = []
        self._trust_ledger: List[TrustLedgerEntry] = []
        self._init_storage()

    def _init_storage(self) -> None:
        """Load an existing ledger from disk. A fresh ledger starts empty.

        Nothing is seeded: every record must come from an actual run or an
        explicit ``record_episode`` / ``record_lesson`` call.
        """
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.storage_path.exists():
            return
        try:
            with open(self.storage_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self._memory_records = [
                EpisodicMemoryRecord(**r) for r in data.get("records", [])
            ]
            self._trust_ledger = [
                TrustLedgerEntry(**e) for e in data.get("ledger", [])
            ]
        except Exception as exc:
            logger.warning("Could not read existing ledger %s: %s. Starting empty.", self.storage_path, exc)
            self._memory_records = []
            self._trust_ledger = []

    def _save(self) -> None:
        """Persist memory records and trust ledger to disk."""
        data = {
            "version": "1.0",
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "records": [r.model_dump() for r in self._memory_records],
            "ledger": [e.model_dump() for e in self._trust_ledger],
        }
        with open(self.storage_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    def record_episode(self, record: EpisodicMemoryRecord) -> None:
        """Store an episodic memory record and update ledger."""
        self._memory_records.append(record)
        self._save()

    def record_trust_entry(self, entry: TrustLedgerEntry) -> None:
        """Add an audited trust ledger entry."""
        self._trust_ledger.append(entry)
        self._save()

    def query_memories(
        self,
        system_id: Optional[str] = None,
        stage: Optional[str] = None,
        error_type: Optional[str] = None,
        keywords: Optional[List[str]] = None,
    ) -> List[EpisodicMemoryRecord]:
        """Query episodic memory for matching past experiences or corrective rules."""
        results = []
        for r in self._memory_records:
            if system_id and system_id.lower() not in r.system_id.lower():
                continue
            if stage and r.stage.lower() != stage.lower():
                continue
            if error_type and r.error_type and r.error_type.lower() != error_type.lower():
                continue
            if keywords:
                text_corpus = f"{r.learned_rule} {r.action_taken} {r.diagnosed_cause or ''}".lower()
                if not any(kw.lower() in text_corpus for kw in keywords):
                    continue
            results.append(r)
        return results

    def recall_corrective_action(
        self, system_id: str, error_type: str
    ) -> Optional[EpisodicMemoryRecord]:
        """Find a trusted prior resolution for this system and failure mode.

        Only records whose ``system_id`` matches (or is ``generic``) and whose
        outcome is ``SELF_CORRECTED`` qualify; there is no cross-system fallback.
        """
        candidates = [
            r for r in self._memory_records
            if (system_id.lower() in r.system_id.lower() or r.system_id == "generic")
            and r.error_type == error_type
            and r.outcome == "SELF_CORRECTED"
        ]
        if candidates:
            # Sort by trust_score descending
            candidates.sort(key=lambda x: x.trust_score, reverse=True)
            return candidates[0]
        return None

    def get_ledger(self) -> List[TrustLedgerEntry]:
        """Retrieve all trust ledger entries."""
        return list(self._trust_ledger)
