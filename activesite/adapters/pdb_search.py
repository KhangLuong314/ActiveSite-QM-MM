"""Search the Protein Data Bank and turn an entry (or a bundled example) into a structure record, like an upload.

- search(q): RCSB full-text search (the same query the catalog stand-in sends for a case's ``pdb_query``), then one
  RCSB GraphQL request for every hit's title, resolution, source organism and non-polymer components. Bound
  ligands and metals are classified with the upload module's own sets, so search results and uploads agree.
- fetch(pdb_id): strict id check, download from files.rcsb.org (PDB format, mmCIF when an entry has no PDB file),
  then the same record creation as an upload (activesite/chem/uploads.py).
- example(name): an allow-listed file that ships with the repo, registered the same way. No client file needed.

Every network failure becomes PdbUnavailable, which the API answers with one plain sentence.
"""
from __future__ import annotations

import json
import re
import threading
import time
from collections import OrderedDict
from pathlib import Path
from typing import Any, Dict, List

import httpx

from activesite.chem import uploads

RCSB_SEARCH = "https://search.rcsb.org/rcsbsearch/v2/query"
RCSB_GRAPHQL = "https://data.rcsb.org/graphql"
RCSB_FILES = "https://files.rcsb.org/download/{pdb_id}.{ext}"
PDB_ID_RE = re.compile(r"^[0-9][A-Za-z0-9]{3}$")
MAX_QUERY = 80
TOP = 10
TIMEOUT = httpx.Timeout(10.0, connect=5.0)
UNREACHABLE = "Could not reach the Protein Data Bank; try a verified example or upload a file."
CACHE_TTL = 3600.0
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")

# bundled examples: id -> (repo file, display name). Only files tracked in git.
EXAMPLES = {
    "egfr_1m17": ("data/reference/egfr/1m17.pdb", "1M17 EGFR kinase + erlotinib (example)"),
    "abl_2hyy": ("data/reference/abl/2hyy.pdb", "2HYY ABL kinase + imatinib (example)"),
}

_GQL = """query($ids: [String!]!) { entries(entry_ids: $ids) {
  rcsb_id struct { title } rcsb_entry_info { resolution_combined }
  polymer_entities { rcsb_entity_source_organism { scientific_name } }
  nonpolymer_entities { nonpolymer_comp { chem_comp { id name } } } } }"""


class PdbUnavailable(RuntimeError):
    """RCSB could not be reached (network, timeout, 5xx)."""


_cache: "OrderedDict[str, tuple[float, List[Dict[str, Any]]]]" = OrderedDict()
_lock = threading.Lock()


def clean_query(q: str | None) -> str:
    """Strip control characters and outer space; refuse empty or over-long queries (UploadError -> HTTP 422)."""
    s = _CONTROL.sub(" ", q or "").strip()
    s = re.sub(r"\s+", " ", s)
    if not s:
        raise uploads.UploadError("type a protein, a drug or a PDB id to search")
    if len(s) > MAX_QUERY:
        raise uploads.UploadError(f"search text is longer than {MAX_QUERY} characters")
    return s


def _classify(comp_id: str, name: str | None) -> str:
    c = comp_id.upper()
    if c in uploads.WATERS:
        return "water"
    if c in uploads.METALS:
        return "metal"
    if c in uploads.ADDITIVES:
        return "additive"
    return "ligand"


def _entry_row(e: Dict[str, Any]) -> Dict[str, Any]:
    res = ((e.get("rcsb_entry_info") or {}).get("resolution_combined") or [None])[0]
    orgs: List[str] = []
    for p in e.get("polymer_entities") or []:
        for o in p.get("rcsb_entity_source_organism") or []:
            n = (o or {}).get("scientific_name")
            if n and n not in orgs:
                orgs.append(n)
    ligands, metals, seen = [], [], set()
    for n in e.get("nonpolymer_entities") or []:
        cc = ((n.get("nonpolymer_comp") or {}).get("chem_comp") or {})
        cid = cc.get("id")
        if not cid or cid in seen:
            continue
        seen.add(cid)
        kind = _classify(cid, cc.get("name"))
        if kind == "ligand":
            ligands.append({"id": cid, "name": cc.get("name")})
        elif kind == "metal":
            metals.append({"id": cid, "name": cc.get("name")})
    return {"pdb_id": e.get("rcsb_id"), "title": (e.get("struct") or {}).get("title"), "organism": ", ".join(orgs[:2]) or None,
            "resolution": res, "ligands": ligands, "metals": metals}


def _verified_pins(query: str) -> Dict[str, str]:
    """PDB ids of the repo's own cases whose drug (from the case id, e.g. abl_imatinib_a -> imatinib) or ligand code
    the query names. RCSB's relevance can rank them low (2HYY is #25 for "imatinib"), so they are listed first,
    marked as the case they belong to."""
    words = set(re.findall(r"[a-z0-9]+", query.lower()))
    pins: Dict[str, str] = {}
    for f in sorted((uploads.ROOT / "cases").glob("*.json")):
        try:
            case = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        m = re.search(r"([0-9][a-z0-9]{3})\.(?:pdb|cif)$", str(case.get("pdb") or "").lower())
        parts = f.stem.split("_")
        keys = {parts[1]} if len(parts) > 1 else set()
        keys |= {str(case.get("ligand") or "").lower()} - {""}
        if m and words & keys:
            pins.setdefault(m.group(1).upper(), f.stem)
    return pins


def search(q: str | None) -> List[Dict[str, Any]]:
    """Top RCSB entries for free text (an enzyme, a drug, a PDB id). Cached for an hour per query."""
    query = clean_query(q)
    key = query.lower()
    with _lock:
        hit = _cache.get(key)
        if hit and time.time() - hit[0] < CACHE_TTL:
            _cache.move_to_end(key)
            return hit[1]
    body = {"query": {"type": "terminal", "service": "full_text", "parameters": {"value": query}},
            "return_type": "entry", "request_options": {"paginate": {"start": 0, "rows": TOP}}}
    pins = _verified_pins(query)
    try:
        r = httpx.post(RCSB_SEARCH, json=body, timeout=TIMEOUT)
        if r.status_code == 204:          # RCSB answers "no hits" with 204 and no body
            found: List[str] = []
        else:
            r.raise_for_status()
            found = [h["identifier"] for h in r.json().get("result_set", [])]
        ids = list(pins) + [i for i in found if i not in pins]
        ids = ids[:TOP]
        rows: List[Dict[str, Any]] = []
        if ids:
            g = httpx.post(RCSB_GRAPHQL, json={"query": _GQL, "variables": {"ids": ids}}, timeout=TIMEOUT)
            g.raise_for_status()
            by_id = {e["rcsb_id"]: _entry_row(e) for e in ((g.json().get("data") or {}).get("entries") or []) if e}
            rows = [dict(by_id[i], verified_case=pins.get(i)) for i in ids if i in by_id]   # pins first, then RCSB's order
    except (httpx.HTTPError, ValueError, KeyError) as exc:
        raise PdbUnavailable(UNREACHABLE) from exc
    with _lock:
        _cache[key] = (time.time(), rows)
        while len(_cache) > 64:
            _cache.popitem(last=False)
    return rows


def fetch(pdb_id: str | None) -> Dict[str, Any]:
    """Download one PDB entry and register it exactly like an upload. Bad id -> UploadError 422; unknown id -> 404."""
    pid = (pdb_id or "").strip()
    if not PDB_ID_RE.match(pid):
        raise uploads.UploadError("a PDB id is four characters starting with a digit, e.g. 4ZAU")
    pid = pid.upper()
    data, ext = None, "pdb"
    try:
        for ext in ("pdb", "cif"):        # very large entries have no PDB-format file
            r = httpx.get(RCSB_FILES.format(pdb_id=pid, ext=ext), timeout=TIMEOUT, follow_redirects=True)
            if r.status_code == 200 and r.content.strip():
                data = r.content
                break
            if r.status_code not in (404, 410):
                r.raise_for_status()
    except httpx.HTTPError as exc:
        raise PdbUnavailable(UNREACHABLE) from exc
    if data is None:
        raise uploads.UploadError(f"the Protein Data Bank has no entry {pid}", status=404)
    record = uploads.save_upload(data, f"{pid}.{ext}", name=pid)
    return _tag(record, {"source": "RCSB PDB", "pdb_id": pid})


def example(name: str | None) -> Dict[str, Any]:
    """Register a bundled real structure (allow-list only) as a structure record."""
    if name not in EXAMPLES:
        raise uploads.UploadError(f"unknown example; choose one of {', '.join(sorted(EXAMPLES))}", status=404)
    rel, display = EXAMPLES[name]
    path = uploads.ROOT / rel
    if not path.exists():
        raise uploads.UploadError(f"example file {Path(rel).name} is not in this checkout", status=404)
    record = uploads.save_upload(path.read_bytes(), path.name, name=display)
    return _tag(record, {"source": "bundled example", "example": name})


def _tag(record: Dict[str, Any], extra: Dict[str, Any]) -> Dict[str, Any]:
    """Add provenance to the stored record (meta.json) and to the returned summary."""
    record.update(extra)
    meta = uploads.uploads_root() / record["structure_id"] / uploads.META
    meta.write_text(json.dumps(record, indent=1), encoding="utf-8")
    return record
