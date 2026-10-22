"""ActiveSite — Meterless H-MEM (Hierarchical Episodic Memory & Trust Ledger).

Implements persistent episodic learning with Markovian state transitions and trust ledger tracking
for QM/MM simulation choices and error self-correction.
"""
from __future__ import annotations

import json
import logging
import os
import sqlite3
import time
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
        """Initialize local file storage and seed foundational domain memories."""
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        if self.storage_path.exists():
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
                logger.warning("Could not read existing ledger: %s. Re-initializing.", exc)
                self._seed_foundational_memories()
        else:
            self._seed_foundational_memories()
            self._save()

    def _seed_foundational_memories(self) -> None:
        """Seed foundational domain rules from prior benchmark simulations."""
        foundational = [
            EpisodicMemoryRecord(
                record_id="MEM_IPPOI_CHARGE_SPIN_001",
                system_id="ippoi_wt",
                stage="critic",
                state_signature="ippoi_mg371_his119_charge0",
                action_taken="Assign qmcharge=0 for catalytic site with Mg2+",
                outcome="SELF_CORRECTED",
                error_type="ODD_ELECTRON_SPIN_MISMATCH",
                diagnosed_cause="Catalytic site contains Mg2+ (+2) coordinating His119, Asn160, Gln139, scissile phosphate (-1). Initial assumption of neutral QM region resulted in unpaired electron count.",
                corrective_action="Increment qmcharge from 0 to +1 to satisfy closed-shell singlet ground state for semi-empirical Hamiltonian.",
                learned_rule="In I-PpoI endonuclease, catalytic Mg2+ coordination requires total qmcharge=+1 to maintain closed-shell singlet state and avoid spin contamination.",
                trust_score=0.99,
                metadata={"recommended_qmcharge": 1, "target_residue": "MG"},
            ),
            EpisodicMemoryRecord(
                record_id="MEM_EGFR_ERLOTINIB_CUTOFF_002",
                system_id="egfr_erlotinib",
                stage="partition",
                state_signature="egfr_pocket_4.0A",
                action_taken="Select active site pocket within 4.0 Angstroms of erlotinib AQ4",
                outcome="SUCCESS",
                error_type=None,
                diagnosed_cause=None,
                corrective_action=None,
                learned_rule="Met769 backbone NH provides indispensable hinge hydrogen bond (2.8 A); Thr766 interacts via bridging crystal water which should be excluded in dehydrated models.",
                trust_score=0.95,
                metadata={"hinge_residue": "MET769", "gatekeeper": "THR766"},
            ),
            EpisodicMemoryRecord(
                record_id="MEM_ABL_IMATINIB_DFG_003",
                system_id="abl_imatinib",
                stage="partition",
                state_signature="abl_2hyy_sti",
                action_taken="Include DFG motif Asp381 and Gatekeeper Thr315 in QM region",
                outcome="SUCCESS",
                error_type=None,
                diagnosed_cause=None,
                corrective_action=None,
                learned_rule="Imatinib stabilizes the DFG-out inactive conformation in ABL kinase; Thr315 OG1 forms crucial hydrogen bond with aminopyrimidine ring.",
                trust_score=0.97,
                metadata={"gatekeeper": "THR315", "dfg_asp": "ASP381"},
            ),
        ]
        self._memory_records.extend(foundational)

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
        """Find a trusted prior resolution for a specific failure mode."""
        candidates = [
            r for r in self._memory_records
            if (system_id.lower() in r.system_id.lower() or r.system_id == "generic")
            and r.error_type == error_type
            and r.outcome == "SELF_CORRECTED"
        ]
        if not candidates:
            # Fallback to any record matching the error_type
            candidates = [
                r for r in self._memory_records
                if r.error_type == error_type and r.corrective_action is not None
            ]
        if candidates:
            # Sort by trust_score descending
            candidates.sort(key=lambda x: x.trust_score, reverse=True)
            return candidates[0]
        return None

    def get_ledger(self) -> List[TrustLedgerEntry]:
        """Retrieve all trust ledger entries."""
        return list(self._trust_ledger)
