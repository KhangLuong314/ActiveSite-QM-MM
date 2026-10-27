"""RCSB chemical-component SMILES lookup for user-uploaded ligands (cached on disk).

GET https://data.rcsb.org/rest/v1/core/chemcomp/<RESNAME>. Preference order: the CACTVS stereo SMILES
(``pdbx_chem_comp_descriptor`` type SMILES_CANONICAL), then CACTVS SMILES, then ``rcsb_chem_comp_descriptor``
SMILES_stereo / SMILES. The CACTVS string is the one the shipped cases use (e.g. egfr_erlotinib AQ4), so a custom run of
the same ligand feeds antechamber the same input. A failed lookup raises LookupError; nothing is guessed.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Optional, Tuple

import httpx

URL = "https://data.rcsb.org/rest/v1/core/chemcomp/{}"
RESNAME_RE = re.compile(r"^[A-Z0-9]{1,3}$")
SMILES_RE = re.compile(r"^[A-Za-z0-9@+\-\[\]()=#%/\\.:*]{1,500}$")
TIMEOUT_S = 10.0


def _cache_dir() -> Path:
    root = Path(os.getenv("ACTIVESITE_CACHE_DIR", str(Path(__file__).resolve().parents[2] / "data" / "cache")))
    return root / "chemcomp"


def pick_smiles(doc: dict) -> Optional[str]:
    desc = doc.get("pdbx_chem_comp_descriptor") or []
    for want in ("SMILES_CANONICAL", "SMILES"):
        for d in desc:
            if d.get("type") == want and str(d.get("program", "")).upper().startswith("CACTVS") and d.get("descriptor"):
                return str(d["descriptor"])
    rc = doc.get("rcsb_chem_comp_descriptor") or {}
    return rc.get("SMILES_stereo") or rc.get("SMILES")


def lookup_smiles(resname: str, transport: Optional[httpx.BaseTransport] = None, use_cache: bool = True) -> Tuple[str, str]:
    """(SMILES, source text) for an RCSB chemical component id, or LookupError explaining why not."""
    if not isinstance(resname, str) or not RESNAME_RE.match(resname):
        raise LookupError(f"ligand residue name {str(resname)[:8]!r} is not a valid chemical component id")
    source = f"RCSB chemcomp {resname} (data.rcsb.org/rest/v1/core/chemcomp/{resname})"
    cache = _cache_dir() / f"{resname}.json"
    if use_cache and cache.exists():
        try:
            smiles = pick_smiles(json.loads(cache.read_text(encoding="utf-8")))
            if smiles and SMILES_RE.match(smiles):
                return smiles, source + " [cached]"
        except (OSError, ValueError):
            pass
    try:
        with httpx.Client(timeout=TIMEOUT_S, transport=transport) as client:
            resp = client.get(URL.format(resname))
    except httpx.HTTPError as exc:
        raise LookupError(f"RCSB chemcomp lookup for {resname} failed ({type(exc).__name__}); give the ligand SMILES")
    if resp.status_code == 404:
        raise LookupError(f"RCSB has no chemical component {resname}; give the ligand SMILES")
    if resp.status_code != 200:
        raise LookupError(f"RCSB chemcomp lookup for {resname} returned HTTP {resp.status_code}; give the ligand SMILES")
    try:
        doc = resp.json()
    except ValueError:
        raise LookupError(f"RCSB chemcomp {resname} did not return JSON; give the ligand SMILES")
    smiles = pick_smiles(doc)
    if not smiles or not SMILES_RE.match(smiles):
        raise LookupError(f"RCSB chemcomp {resname} has no usable SMILES; give the ligand SMILES")
    try:
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps(doc), encoding="utf-8")
    except OSError:
        pass
    return smiles, source
