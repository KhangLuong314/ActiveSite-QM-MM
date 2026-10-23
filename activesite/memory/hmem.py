"""ActiveSite — Meterless H-MEM subset: memory store + scored retrieval + append-only ledger.

Scoring. The Meterless spec weights keyword .20, tag .10, layer .05 and
recency .05 alongside semantic, domain and entity terms. Those three are not
computed here (no embedding model in the judge's CPU budget), so the four
terms we do compute are rescaled to sum to 1:

    score = (0.50 * keyword_jaccard + 0.25 * tag_jaccard
             + 0.125 * layer_weight + 0.125 * recency) * confidence

with layer weights long_term 1.0, working 0.8, short_term 0.6 and
recency = exp(-(now - last_accessed) / 14 days). Hits need score >= 0.35 and
at most 5 are returned. When the query carries tags, a memory must share at
least one of them; a memory from another domain is never returned on keyword
overlap alone. Tokens are lowercase alphanumerics minus a small stopword list
with a trailing "s" stripped from words longer than three letters; the first 8
unique query tokens are used.

The ledger (``logs/hmem_ledger.jsonl``) is append-only: every create and
every read appends a line; nothing ever rewrites it.
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
from typing import Any, Dict, Iterable, List, Optional, Sequence

LAYERS = {"long_term": 1.0, "working": 0.8, "short_term": 0.6}
THRESHOLD = 0.35
TOP_K = 5
RECENCY_DAYS = 14.0
MAX_QUERY_TOKENS = 8
STOPWORDS = frozenset({
    "a", "an", "the", "and", "or", "of", "to", "in", "on", "for", "with", "by", "is", "are", "was", "be",
    "it", "its", "this", "that", "from", "as", "at", "not", "no", "we", "our", "if", "then", "than", "so",
})
WEIGHTS = {"keyword": 0.50, "tag": 0.25, "layer": 0.125, "recency": 0.125}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


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


class MemoryStoreService:
    def __init__(self, db_path: Path | str, ledger_path: Path | str):
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

    # ---------------------------------------------------------------- ledger
    def ledger(self, action: str, memory_id: Optional[str], actor: str, details: Any,
               new_state: Any = None) -> Dict[str, Any]:
        entry = {
            "id": f"led_{secrets.token_hex(5)}",
            "memoryId": memory_id,
            "action": action,
            "actor": actor,
            "timestamp": int(time.time() * 1000),
            "newState": new_state,
            "details": details,
        }
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

    # ----------------------------------------------------------------- store
    def add(self, content: str, type: str, layer: str, tags: Sequence[str], source: str,
            confidence: float = 0.5, agent_id: str = "unknown", run_id: str = "", origin: str = "tool",
            extra: Optional[Dict[str, Any]] = None) -> str:
        if not source or not str(source).strip():
            raise ValueError("source is required for every memory")
        if layer not in LAYERS:
            raise ValueError(f"layer must be one of {sorted(LAYERS)}, got {layer!r}")
        if not content or not str(content).strip():
            raise ValueError("content is required")
        confidence = max(0.0, min(1.0, float(confidence)))
        mem_id = f"mem_{secrets.token_hex(5)}"
        now = _now_iso()
        provenance = {"origin": origin, "learnedAt": now, "label": f"{agent_id} during run {run_id}"}
        row = {
            "id": mem_id, "content": content, "type": type, "layer": layer, "tags": list(tags or []),
            "source": source, "provenance": provenance, "confidence": confidence, "agent_id": agent_id,
            "run_id": run_id, "timestamp": now, "last_accessed": now, "access_count": 0, "extra": dict(extra or {}),
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
                             (_now_iso(), memory_id))
            self.con.commit()

    def close(self) -> None:
        self.con.close()


class MemoryRetrievalService:
    def __init__(self, store: MemoryStoreService):
        self.store = store

    def score(self, memory: Dict[str, Any], q_tokens: Sequence[str], tags: Sequence[str],
              now: Optional[float] = None) -> Dict[str, float]:
        now = time.time() if now is None else now
        kw = _jaccard(q_tokens, tokenize(memory["content"]))
        tg = _jaccard(tags, memory.get("tags", [])) if tags else 0.0
        layer = LAYERS.get(memory.get("layer"), 0.0)
        age_days = max(0.0, now - _parse_iso(memory.get("last_accessed") or "")) / 86400.0
        rec = math.exp(-age_days / RECENCY_DAYS)
        base = WEIGHTS["keyword"] * kw + WEIGHTS["tag"] * tg + WEIGHTS["layer"] * layer + WEIGHTS["recency"] * rec
        return {"keyword": round(kw, 4), "tag": round(tg, 4), "layer": layer, "recency": round(rec, 4),
                "confidence": float(memory.get("confidence") or 0.0), "score": round(base * float(memory.get("confidence") or 0.0), 4)}

    def retrieve(self, query: str, tags: Sequence[str] = (), actor: str = "agent", run_id: str = "") -> List[Dict[str, Any]]:
        q_tokens = query_tokens(query)
        tags = list(tags or [])
        scored = []
        for mem in self.store.all():
            if tags and not (set(tags) & set(mem.get("tags", []))):
                continue  # hard domain gate: no shared tag, never returned
            parts = self.score(mem, q_tokens, tags)
            if parts["score"] >= THRESHOLD:
                scored.append((parts["score"], mem, parts))
        scored.sort(key=lambda x: x[0], reverse=True)
        hits = []
        for score, mem, parts in scored[:TOP_K]:
            self.store.touch(mem["id"])
            self.store.ledger("read", mem["id"], actor,
                              {"query": query, "query_tokens": q_tokens, "tags": tags, "score": score, "parts": parts,
                               "run_id": run_id})
            hits.append({"memory": mem, "score": score, "parts": parts})
        return hits
