"""ActiveSite — Meterless H-MEM subset: memory store + scored retrieval + append-only ledger.

Scoring. The Meterless spec weights keyword .20, tag .10, layer .05 and
recency .05 alongside semantic, domain and entity terms. Those three are not
computed here (no embedding model in the judge's CPU budget), so the four
terms we do compute are rescaled to sum to 1:

    raw   = 0.50 * keyword_jaccard + 0.25 * tag_jaccard
            + 0.125 * layer_weight + 0.125 * recency - 0.20 * superseded
    score = clamp01(raw) * confidence

with layer weights long_term 1.0, working 0.8, short_term 0.6,
recency = exp(-(now - last_accessed) / 14 days), and superseded = 1 when
conflict resolution marked the memory ``supersededBy`` (penalised, never
deleted). Hits need score >= 0.35 and at most 5 are returned. When the query
carries tags, a memory must share at least one of them; a memory from another
domain is never returned on keyword overlap alone. Tokens are lowercase
alphanumerics minus a small stopword list with a trailing "s" stripped from
words longer than three letters; the first 8 unique query tokens are used.

The ledger (``logs/hmem_ledger.jsonl``) is append-only: every create, read,
feedback, conflict, sleep and dream action appends a line; nothing ever
rewrites it.

Spec services beyond store + retrieval (feedback deltas, sleep, conflicts,
dreaming, and the ``HMEM`` facade the Meterless conformance runner expects)
live at the bottom of this module. Where the spec says "cosine" we use
bag-of-words cosine over ``tokenize`` (no embedding model here). Lineage
fields (``derivedFrom``, ``supersedes``, ``supersededBy``) live in the
``extra`` JSON column so existing databases need no migration.
``tests/test_hmem_conformance.py`` runs the upstream conformance vectors.
"""
from __future__ import annotations

import json
import math
import re
import secrets
import sqlite3
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence

LAYERS = {"long_term": 1.0, "working": 0.8, "short_term": 0.6}
THRESHOLD = 0.35
TOP_K = 5
RECENCY_DAYS = 14.0
SUPERSEDED_PENALTY = 0.20
# Exact feedback deltas, Meterless AGENTS.md section 9.2.
FEEDBACK_DELTAS = {"helpful": 0.05, "not_helpful": -0.03, "wrong": -0.20}
# Operational defaults, Meterless AGENTS.md section 13.
DAY_S = 86400.0
CONSOLIDATION_DAYS = 7
ARCHIVE_MIN_DAYS = 30
ARCHIVE_MAX_ACCESS = 2
HUB_THRESHOLD = 3
SYNTHESIS_COSINE = 0.82
DREAM_CLUSTER_MIN = 2
DREAM_RELATEDNESS = 0.35
MAX_DREAM_PROPOSALS_PER_TYPE = 8
CONFLICT_AUTO_RESOLVE_GATE = 0.70
MAX_QUERY_TOKENS = 8
STOPWORDS = frozenset({
    "a", "an", "the", "and", "or", "of", "to", "in", "on", "for", "with", "by", "is", "are", "was", "be",
    "it", "its", "this", "that", "from", "as", "at", "not", "no", "we", "our", "if", "then", "than", "so",
})
WEIGHTS = {"keyword": 0.50, "tag": 0.25, "layer": 0.125, "recency": 0.125}


def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, float(x)))


def _parse_iso(ts: str) -> float:
    try:
        return datetime.fromisoformat(ts).timestamp()
    except (TypeError, ValueError):
        return 0.0


def tokenize(text: str) -> List[str]:
    toks = []
    for t in re.findall(r"[a-z0-9]+", (text or "").lower()):
        if t in STOPWORDS:
            continue
        if len(t) > 3 and t.endswith("s") and not t.endswith("ss"):
            t = t[:-1]
        toks.append(t)
    return toks


def query_tokens(query: str) -> List[str]:
    out: List[str] = []
    for t in tokenize(query):
        if t not in out:
            out.append(t)
        if len(out) == MAX_QUERY_TOKENS:
            break
    return out


def _jaccard(a: Iterable[str], b: Iterable[str]) -> float:
    sa, sb = set(a), set(b)
    if not sa and not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


def text_cosine(a: str, b: str) -> float:
    """Bag-of-words cosine over ``tokenize``: our stand-in for the spec's embedding cosine."""
    ta, tb = set(tokenize(a)), set(tokenize(b))
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / math.sqrt(len(ta) * len(tb))


class MemoryStoreService:
    def __init__(self, db_path: Path | str, ledger_path: Path | str,
                 clock: Optional[Callable[[], float]] = None):
        # clock returns epoch seconds; injectable so time-dependent rules (recency, sleep) are testable.
        self.clock: Callable[[], float] = clock or time.time
        self.db_path = Path(db_path)
        self.ledger_path = Path(ledger_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.ledger_path.parent.mkdir(parents=True, exist_ok=True)
        # check_same_thread=False: the FastAPI server reads the store from worker threads; writes are serialised below.
        self.con = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self.con.row_factory = sqlite3.Row
        self._lock = threading.RLock()
        self.con.execute(
            """CREATE TABLE IF NOT EXISTS memories (
                id TEXT PRIMARY KEY, content TEXT NOT NULL, type TEXT, layer TEXT, tags TEXT, source TEXT NOT NULL,
                provenance TEXT, confidence REAL, agent_id TEXT, run_id TEXT, timestamp TEXT, last_accessed TEXT,
                access_count INTEGER DEFAULT 0, extra TEXT)"""
        )
        self.con.commit()

    def _iso(self) -> str:
        return datetime.fromtimestamp(self.clock(), timezone.utc).isoformat()

    # ---------------------------------------------------------------- ledger
    def ledger(self, action: str, memory_id: Optional[str], actor: str, details: Any,
               new_state: Any = None, previous_state: Any = None) -> Dict[str, Any]:
        entry = {
            "id": f"led_{secrets.token_hex(5)}",
            "memoryId": memory_id,
            "action": action,
            "actor": actor,
            "timestamp": int(round(self.clock() * 1000)),
            "newState": new_state,
            "details": details,
        }
        if previous_state is not None:
            entry["previousState"] = previous_state
        with open(self.ledger_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, default=str) + "\n")
        return entry

    def read_ledger(self) -> List[Dict[str, Any]]:
        if not self.ledger_path.exists():
            return []
        out = []
        for line in self.ledger_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                try:
                    out.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        return out

    def history(self, memory_id: str) -> List[Dict[str, Any]]:
        """Every ledger entry for one memory, oldest first (spec 9.1 reconstruction)."""
        return [e for e in self.read_ledger() if e.get("memoryId") == memory_id]

    # ----------------------------------------------------------------- store
    def add(self, content: str, type: str, layer: str, tags: Sequence[str], source: str,
            confidence: float = 0.5, agent_id: str = "unknown", run_id: str = "", origin: str = "tool",
            extra: Optional[Dict[str, Any]] = None, derived_from: Optional[Sequence[str]] = None,
            supersedes: Optional[str] = None) -> str:
        if not source or not str(source).strip():
            raise ValueError("source is required for every memory")
        if layer not in LAYERS:
            raise ValueError(f"layer must be one of {sorted(LAYERS)}, got {layer!r}")
        if not content or not str(content).strip():
            raise ValueError("content is required")
        confidence = max(0.0, min(1.0, float(confidence)))
        mem_id = f"mem_{secrets.token_hex(5)}"
        now = self._iso()
        provenance = {"origin": origin, "learnedAt": now, "label": f"{agent_id} during run {run_id}"}
        extra = dict(extra or {})
        if derived_from:
            extra["derivedFrom"] = list(derived_from)
        if supersedes:
            extra["supersedes"] = supersedes
        row = {
            "id": mem_id, "content": content, "type": type, "layer": layer, "tags": list(tags or []),
            "source": source, "provenance": provenance, "confidence": confidence, "agent_id": agent_id,
            "run_id": run_id, "timestamp": now, "last_accessed": now, "access_count": 0, "extra": extra,
        }
        with self._lock:
            self.con.execute(
                "INSERT INTO memories VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (mem_id, content, type, layer, json.dumps(row["tags"]), source, json.dumps(provenance), confidence,
                 agent_id, run_id, now, now, 0, json.dumps(row["extra"], default=str)),
            )
            self.con.commit()
        self.ledger("create", mem_id, agent_id,
                    {"content": content[:160], "type": type, "layer": layer, "tags": row["tags"], "source": source,
                     "run_id": run_id}, new_state=row)
        return mem_id

    @staticmethod
    def _row_to_dict(r: sqlite3.Row) -> Dict[str, Any]:
        d = dict(r)
        d["tags"] = json.loads(d["tags"] or "[]")
        d["provenance"] = json.loads(d["provenance"] or "{}")
        d["extra"] = json.loads(d["extra"] or "{}")
        return d

    def all(self) -> List[Dict[str, Any]]:
        with self._lock:
            return [self._row_to_dict(r) for r in self.con.execute("SELECT * FROM memories ORDER BY timestamp")]

    def get(self, memory_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            r = self.con.execute("SELECT * FROM memories WHERE id = ?", (memory_id,)).fetchone()
        return self._row_to_dict(r) if r else None

    def touch(self, memory_id: str) -> None:
        with self._lock:
            self.con.execute("UPDATE memories SET last_accessed = ?, access_count = access_count + 1 WHERE id = ?",
                             (self._iso(), memory_id))
            self.con.commit()

    # Column allow-list for _write: column names are never taken from caller input.
    _WRITABLE = {"confidence": None, "access_count": None, "layer": None, "last_accessed": None,
                 "tags": json.dumps, "extra": lambda v: json.dumps(v, default=str)}

    def _write(self, memory_id: str, **fields: Any) -> None:
        cols, vals = [], []
        for k, v in fields.items():
            if k not in self._WRITABLE:
                raise ValueError(f"field {k!r} is not writable")
            enc = self._WRITABLE[k]
            cols.append(f"{k} = ?")
            vals.append(enc(v) if enc else v)
        with self._lock:
            self.con.execute(f"UPDATE memories SET {', '.join(cols)} WHERE id = ?", (*vals, memory_id))
            self.con.commit()

    def _must_get(self, memory_id: str) -> Dict[str, Any]:
        mem = self.get(memory_id)
        if mem is None:
            raise KeyError(f"unknown memory id {memory_id}")
        return mem

    def update(self, memory_id: str, actor: str, action: str = "update", details: Any = None,
               **fields: Any) -> Dict[str, Any]:
        """Change fields of one memory and ledger the change with previous and new state."""
        prev = self._must_get(memory_id)
        self._write(memory_id, **fields)
        new = self._must_get(memory_id)
        self.ledger(action, memory_id, actor, details or {}, new_state=new, previous_state=prev)
        return new

    def delete(self, memory_id: str, actor: str, reason: str) -> None:
        prev = self._must_get(memory_id)
        with self._lock:
            self.con.execute("DELETE FROM memories WHERE id = ?", (memory_id,))
            self.con.commit()
        self.ledger("delete", memory_id, actor, {"reason": reason}, previous_state=prev)

    def snapshot_rows(self) -> List[tuple]:
        with self._lock:
            return [tuple(r) for r in self.con.execute("SELECT * FROM memories")]

    def restore_rows(self, rows: List[tuple]) -> None:
        with self._lock:
            self.con.execute("DELETE FROM memories")
            self.con.executemany("INSERT INTO memories VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)", rows)
            self.con.commit()

    def close(self) -> None:
        self.con.close()


class MemoryRetrievalService:
    def __init__(self, store: MemoryStoreService):
        self.store = store

    def score(self, memory: Dict[str, Any], q_tokens: Sequence[str], tags: Sequence[str],
              now: Optional[float] = None) -> Dict[str, float]:
        now = self.store.clock() if now is None else now
        kw = _jaccard(q_tokens, tokenize(memory["content"]))
        tg = _jaccard(tags, memory.get("tags", [])) if tags else 0.0
        layer = LAYERS.get(memory.get("layer"), 0.0)
        age_days = max(0.0, now - _parse_iso(memory.get("last_accessed") or "")) / 86400.0
        rec = math.exp(-age_days / RECENCY_DAYS)
        superseded = 1.0 if (memory.get("extra") or {}).get("supersededBy") else 0.0
        raw = (WEIGHTS["keyword"] * kw + WEIGHTS["tag"] * tg + WEIGHTS["layer"] * layer + WEIGHTS["recency"] * rec
               - SUPERSEDED_PENALTY * superseded)
        conf = float(memory.get("confidence") or 0.0)
        return {"keyword": round(kw, 4), "tag": round(tg, 4), "layer": layer, "recency": round(rec, 4),
                "superseded": superseded, "confidence": conf, "score": round(_clamp01(raw) * conf, 4)}

    def retrieve(self, query: str, tags: Sequence[str] = (), actor: str = "agent", run_id: str = "",
                 threshold: float = THRESHOLD, top_k: int = TOP_K) -> List[Dict[str, Any]]:
        q_tokens = query_tokens(query)
        tags = list(tags or [])
        scored = []
        for mem in self.store.all():
            if tags and not (set(tags) & set(mem.get("tags", []))):
                continue  # hard domain gate: no shared tag, never returned
            parts = self.score(mem, q_tokens, tags)
            if parts["score"] >= threshold:
                scored.append((parts["score"], mem, parts))
        scored.sort(key=lambda x: x[0], reverse=True)
        hits = []
        for score, mem, parts in scored[:top_k]:
            self.store.touch(mem["id"])
            self.store.ledger("read", mem["id"], actor,
                              {"query": query, "query_tokens": q_tokens, "tags": tags, "score": score, "parts": parts,
                               "run_id": run_id})
            hits.append({"memory": mem, "score": score, "parts": parts})
        return hits

    def feedback(self, memory_id: str, kind: str, actor: str = "user") -> Dict[str, Any]:
        """Exact spec 9.2 deltas: helpful +0.05 and accessCount+1, not_helpful -0.03, wrong -0.20 plus 'review' tag."""
        if kind not in FEEDBACK_DELTAS:
            raise ValueError(f"feedback kind must be one of {sorted(FEEDBACK_DELTAS)}, got {kind!r}")
        m = self.store._must_get(memory_id)
        fields: Dict[str, Any] = {"confidence": _clamp01(float(m["confidence"]) + FEEDBACK_DELTAS[kind])}
        if kind == "helpful":
            fields["access_count"] = int(m["access_count"]) + 1
        if kind == "wrong" and "review" not in m["tags"]:
            fields["tags"] = [*m["tags"], "review"]
        return self.store.update(memory_id, actor, action="feedback",
                                 details={"kind": kind, "delta": FEEDBACK_DELTAS[kind]}, **fields)


# --------------------------------------------------------------------------- spec services
def _lineage(m: Dict[str, Any], key: str) -> Any:
    return (m.get("extra") or {}).get(key)


def _same_domain(a: Dict[str, Any], b: Dict[str, Any]) -> bool:
    # Our domain signal is the tag set (see the retrieval domain gate); untagged memories share "general".
    ta, tb = set(a.get("tags") or []), set(b.get("tags") or [])
    return bool(ta & tb) or (not ta and not tb)


class TrustLedgerService:
    """Read view over the append-only JSONL ledger (spec 9.1)."""

    def __init__(self, store: MemoryStoreService):
        self.store = store

    def history(self, memory_id: str) -> List[Dict[str, Any]]:
        return self.store.history(memory_id)

    def all(self) -> List[Dict[str, Any]]:
        return self.store.read_ledger()


class SleepCycleService:
    """Preview-first consolidation and archival (spec 8). preview() never mutates; execute() backs up first."""

    def __init__(self, store: MemoryStoreService, actor: str = "sleep"):
        self.store = store
        self.actor = actor
        self._backups: Dict[str, List[tuple]] = {}

    def preview(self) -> Dict[str, Any]:
        now = self.store.clock()
        mems = self.store.all()
        referenced = set()
        for m in mems:
            referenced.update(_lineage(m, "relatedTo") or [])
            referenced.update(_lineage(m, "derivedFrom") or [])
            if _lineage(m, "supersedes"):
                referenced.add(_lineage(m, "supersedes"))

        to_consolidate = [m["id"] for m in mems if m["layer"] == "short_term"
                          and now - _parse_iso(m["last_accessed"]) >= CONSOLIDATION_DAYS * DAY_S]
        to_archive = []
        for m in mems:
            old_enough = now - _parse_iso(m["timestamp"]) >= ARCHIVE_MIN_DAYS * DAY_S
            if not (old_enough and int(m["access_count"]) <= ARCHIVE_MAX_ACCESS and m["id"] not in referenced):
                continue
            # Guardrails (spec 8.2): never archive superseding, derived, or hub records.
            if _lineage(m, "supersedes") or _lineage(m, "derivedFrom"):
                continue
            if len(_lineage(m, "relatedTo") or []) >= HUB_THRESHOLD:
                continue
            to_archive.append(m["id"])

        to_synthesize: List[List[str]] = []
        used: set = set()
        for i, a in enumerate(mems):
            if a["id"] in used:
                continue
            group = [a] + [b for b in mems[i + 1:] if b["id"] not in used
                           and text_cosine(a["content"], b["content"]) >= SYNTHESIS_COSINE]
            if len(group) >= 2:
                used.update(g["id"] for g in group)
                to_synthesize.append([g["id"] for g in group])
        return {"toConsolidate": to_consolidate, "toArchive": to_archive, "toSynthesize": to_synthesize}

    def execute(self, plan: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        plan = plan or self.preview()
        backup_id = f"backup_{secrets.token_hex(5)}"
        self._backups[backup_id] = self.store.snapshot_rows()
        log = [f"backup {backup_id} created"]
        for mid in plan["toConsolidate"]:
            if self.store.get(mid):
                self.store.update(mid, self.actor, action="promote", layer="long_term")
                self.store.ledger("sleep_consolidate", mid, self.actor, {"from": "short_term", "to": "long_term"})
                log.append(f"consolidated {mid}")
        for mid in plan["toArchive"]:
            m = self.store.get(mid)
            if m:
                self.store.ledger("sleep_archive", mid, self.actor, {"accessCount": m["access_count"]})
                self.store.delete(mid, self.actor, "sleep archive")
                log.append(f"archived {mid}")
        synthesized = 0
        for group in plan["toSynthesize"]:
            members = [m for m in (self.store.get(i) for i in group) if m]
            if len(members) < 2:
                continue
            merged = self.store.add(
                "Synthesis: " + " | ".join(m["content"] for m in members), "factual", "long_term",
                sorted({t for m in members for t in m["tags"]}), source="sleep:synthesis",
                confidence=max(float(m["confidence"]) for m in members), agent_id=self.actor,
                origin="sleep_synthesis", derived_from=[m["id"] for m in members])
            self.store.ledger("sleep_synthesize", merged, self.actor, {"sources": group})
            for m in members:
                self.store.delete(m["id"], self.actor, "merged by sleep synthesis")
            synthesized += 1
            log.append(f"synthesized {merged} from {', '.join(group)}")
        return {"backupId": backup_id, "consolidated": len(plan["toConsolidate"]),
                "archived": len(plan["toArchive"]), "synthesized": synthesized, "actionLog": log}

    def restore(self, backup_id: str) -> None:
        if backup_id not in self._backups:
            raise KeyError(f"unknown backup {backup_id}")
        self.store.restore_rows(self._backups[backup_id])
        self.store.ledger("restore", "*", self.actor, {"backupId": backup_id})


_OPPOSING = [
    (re.compile(r"\balways\b", re.I), re.compile(r"\bnever\b", re.I)),
    (re.compile(r"\benable[ds]?\b", re.I), re.compile(r"\bdisable[ds]?\b", re.I)),
    (re.compile(r"\bprefers?\b", re.I), re.compile(r"\b(avoids?|dislikes?)\b", re.I)),
    (re.compile(r"\bon\b", re.I), re.compile(r"\boff\b", re.I)),
    (re.compile(r"\byes\b", re.I), re.compile(r"\bno\b", re.I)),
]


class ConflictDetectionService:
    """Contradiction scan + weighted auto-decision (spec 10). Losers are marked supersededBy, never deleted."""

    def __init__(self, store: MemoryStoreService, actor: str = "conflicts"):
        self.store = store
        self.actor = actor
        self.conflicts: List[Dict[str, Any]] = []

    def _check(self, a: Dict[str, Any], b: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        # A supersedes relation is an intended replacement, not a conflict.
        if b["id"] in (_lineage(a, "supersedes"), _lineage(a, "supersededBy")) or \
                a["id"] in (_lineage(b, "supersedes"), _lineage(b, "supersededBy")):
            return None
        sim = text_cosine(a["content"], b["content"])
        reason, conf = "", 0.0
        for p, q in _OPPOSING:
            if ((p.search(a["content"]) and q.search(b["content"])) or
                    (q.search(a["content"]) and p.search(b["content"]))) and sim > 0.5:
                reason, conf = "opposing phrase pair on similar content", 0.5 + 0.3 * sim
        if not reason and sim > 0.8:
            na = re.findall(r"\d+(?:\.\d+)?", a["content"])
            nb = re.findall(r"\d+(?:\.\d+)?", b["content"])
            if na and nb and na != nb:
                reason, conf = "high-similarity conflicting numeric values", 0.55 + 0.25 * sim
        if not reason:
            return None
        if _same_domain(a, b):
            conf += 0.05
        if b["id"] in (_lineage(a, "relatedTo") or []):
            conf -= 0.1  # explicit relation lowers false positives
        return {"id": f"conflict_{secrets.token_hex(4)}", "memoryA": a["id"], "memoryB": b["id"],
                "reason": reason, "confidence": _clamp01(conf), "resolved": False}

    def scan(self) -> List[Dict[str, Any]]:
        mems = self.store.all()
        found = []
        for i, a in enumerate(mems):
            for b in mems[i + 1:]:
                c = self._check(a, b)
                if c:
                    found.append(c)
                    self.conflicts.append(c)
                    self.store.ledger("conflict_detected", c["memoryA"], self.actor,
                                      {"with": c["memoryB"], "reason": c["reason"], "confidence": c["confidence"]})
        return found

    def decision(self, conflict: Dict[str, Any]) -> Dict[str, Any]:
        """Weighted heuristics (recency, access, confidence, richness, source reliability); no side effects."""
        a = self.store._must_get(conflict["memoryA"])
        b = self.store._must_get(conflict["memoryB"])
        now = max(1.0, self.store.clock())

        def score(m: Dict[str, Any]) -> float:
            return (0.3 * (_parse_iso(m["last_accessed"]) / now) + 0.2 * min(1.0, int(m["access_count"]) / 10)
                    + 0.25 * float(m["confidence"]) + 0.1 * min(1.0, len(m["content"]) / 200)
                    + 0.15 * (1.0 if (m.get("provenance") or {}).get("origin") == "user_correction" else 0.5))

        sa, sb = score(a), score(b)
        margin = abs(sa - sb) / max(sa, sb) if max(sa, sb) > 0 else 0.0
        winner, loser = (a, b) if sa >= sb else (b, a)
        return {"decisionConfidence": _clamp01(conflict["confidence"] * 0.6 + margin * 0.8),
                "winner": winner["id"], "loser": loser["id"]}

    def auto_resolve(self, conflict: Dict[str, Any]) -> str:
        d = self.decision(conflict)
        if d["decisionConfidence"] < CONFLICT_AUTO_RESOLVE_GATE:
            return "queued"
        loser = self.store._must_get(d["loser"])
        extra = {**(loser.get("extra") or {}), "supersededBy": d["winner"]}
        self.store.update(d["loser"], self.actor, action="conflict_resolved", extra=extra,
                          details={"conflictId": conflict["id"], "winner": d["winner"],
                                   "decisionConfidence": round(d["decisionConfidence"], 3)})
        conflict["resolved"] = True
        conflict["resolution"] = "keep_a" if d["winner"] == conflict["memoryA"] else "keep_b"
        return "resolved"

    def queue(self) -> List[Dict[str, Any]]:
        return [c for c in self.conflicts if not c["resolved"]]


class DreamingService:
    """Constructive synthesis behind a human approval boundary (spec 7). dream() only proposes."""

    def __init__(self, store: MemoryStoreService, actor: str = "dreaming"):
        self.store = store
        self.actor = actor
        self.proposals: Dict[str, Dict[str, Any]] = {}

    @staticmethod
    def _relatedness(a: Dict[str, Any], b: Dict[str, Any]) -> float:
        # Spec 7.1 signals we compute: content similarity, tag overlap, shared domain. No entity extraction here.
        return (0.5 * text_cosine(a["content"], b["content"]) + 0.2 * _jaccard(a["tags"], b["tags"])
                + 0.1 * (1.0 if _same_domain(a, b) else 0.0))

    def _propose(self, ptype: str, content: str, derived_from: List[str]) -> Dict[str, Any]:
        p = {"id": f"dream_{secrets.token_hex(5)}", "type": ptype, "content": content,
             "derivedFrom": derived_from, "status": "proposed"}
        self.proposals[p["id"]] = p
        self.store.ledger("dream_proposed", p["id"], self.actor, {"type": ptype, "derivedFrom": derived_from})
        return p

    def dream(self) -> List[Dict[str, Any]]:
        mems = self.store.all()
        created: List[Dict[str, Any]] = []
        used: set = set()
        for seed in mems:  # insights from clusters
            if len([p for p in created if p["type"] == "insight"]) >= MAX_DREAM_PROPOSALS_PER_TYPE:
                break
            if seed["id"] in used:
                continue
            group = [seed] + [o for o in mems if o["id"] != seed["id"] and o["id"] not in used
                              and self._relatedness(seed, o) >= DREAM_RELATEDNESS]
            if len(group) >= DREAM_CLUSTER_MIN:
                used.update(g["id"] for g in group)
                created.append(self._propose(
                    "insight", f"Across {len(group)} related memories: " + " + ".join(g["content"] for g in group),
                    [g["id"] for g in group]))
        # invariants from preference/personal/correction signals, grouped by domain (tag set)
        prefs = [m for m in mems if m["type"] in ("preference", "personal") or "event:user_correction" in m["tags"]]
        groups: Dict[tuple, List[Dict[str, Any]]] = {}
        for m in prefs:
            groups.setdefault(tuple(sorted(m["tags"])), []).append(m)
        n_inv = 0
        for key, members in groups.items():
            if n_inv >= MAX_DREAM_PROPOSALS_PER_TYPE:
                break
            if len(members) >= 2:
                domain = "/".join(key) or "general"
                created.append(self._propose("invariant", f"Stable pattern in {domain}: "
                                             + "; ".join(m["content"] for m in members), [m["id"] for m in members]))
                n_inv += 1
        return created

    def pending(self) -> List[Dict[str, Any]]:
        return [p for p in self.proposals.values() if p["status"] == "proposed"]

    def approve(self, proposal_id: str) -> Optional[Dict[str, Any]]:
        p = self.proposals.get(proposal_id)
        if not p or p["status"] != "proposed":
            raise KeyError(f"no pending proposal {proposal_id}")
        p["status"] = "approved"
        self.store.ledger("dream_approved", proposal_id, self.actor, {"type": p["type"]})
        mid = self.store.add(p["content"], "factual" if p["type"] == "insight" else "preference", "long_term",
                             [f"dream:{p['type']}"], source="dreaming", confidence=0.75, agent_id=self.actor,
                             origin="dream", derived_from=p["derivedFrom"])
        return self.store.get(mid)

    def reject(self, proposal_id: str) -> None:
        p = self.proposals.get(proposal_id)
        if not p or p["status"] != "proposed":
            raise KeyError(f"no pending proposal {proposal_id}")
        p["status"] = "rejected"  # logged, not materialised
        self.store.ledger("dream_rejected", proposal_id, self.actor, {"type": p["type"]})


class HMEM:
    """The service surface the Meterless conformance runner drives (store, ledger, sleep, dreaming, conflicts).

    ``clock`` returns epoch MILLISECONDS, matching the spec's vectors; the store works in seconds.
    """

    def __init__(self, db_path: Path | str, ledger_path: Path | str,
                 clock: Optional[Callable[[], float]] = None, actor: str = "system"):
        clock_s = (lambda: clock() / 1000.0) if clock else None
        self.store = MemoryStoreService(db_path, ledger_path, clock=clock_s)
        self.retrieval = MemoryRetrievalService(self.store)
        self.ledger = TrustLedgerService(self.store)
        self.sleep = SleepCycleService(self.store)
        self.conflicts = ConflictDetectionService(self.store)
        self.dreaming = DreamingService(self.store)
        self.actor = actor

    def add(self, content: str, source: str, confidence: float = 0.7, type: str = "general",
            layer: str = "working", tags: Sequence[str] = (), derived_from: Optional[Sequence[str]] = None,
            supersedes: Optional[str] = None) -> Dict[str, Any]:
        mid = self.store.add(content, type, layer, tags, source=source, confidence=confidence, agent_id=self.actor,
                             derived_from=derived_from, supersedes=supersedes)
        return self.store._must_get(mid)

    def query(self, query: str, threshold: float = THRESHOLD, top_n: int = TOP_K,
              tags: Sequence[str] = ()) -> List[Dict[str, Any]]:
        return self.retrieval.retrieve(query, tags=tags, actor=self.actor, threshold=threshold, top_k=top_n)

    def feedback(self, memory_id: str, kind: str) -> Dict[str, Any]:
        return self.retrieval.feedback(memory_id, kind, actor=self.actor)
