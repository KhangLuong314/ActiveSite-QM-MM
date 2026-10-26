"""Active-site PDB files for the 3D viewer, built from the real system of each metal case.

The metal cases (I-PpoI site A/B) have no crystal PDB in the repo: their structure is the lab's Amber topology and
production frame named in the case file. This writes the residues within RADIUS of the case's metal as a PDB whose
atom serials and residue numbers are the topology's own, so the run's QM mask (e.g. "@385-416,...") selects the same
atoms in the viewer. The file says so in a REMARK line, and is cached under the cache directory.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parents[2]
RADIUS = 12.0
SERIALS_REMARK = "REMARK 900 ACTIVESITE SERIALS=TOPOLOGY"


def _cache_dir() -> Path:
    return Path(os.getenv("ACTIVESITE_CACHE_DIR", str(ROOT / "data" / "cache"))) / "structures"


def metal_site_pdb(case_id: str) -> Optional[Path]:
    """PDB of the active site of a metal case, or None if the case has no topology, metal or reference files."""
    case_file = ROOT / "cases" / f"{case_id}.json"
    if not case_file.exists():
        return None
    case = json.loads(case_file.read_text())
    parm7, coords, metal = case.get("parm7"), case.get("coords"), case.get("metal_resid")
    if not (parm7 and coords and metal) or not (ROOT / parm7).exists() or not (ROOT / coords).exists():
        return None
    out = _cache_dir() / f"{case_id}.pdb"
    if out.exists():
        return out
    import parmed as pmd

    st = pmd.load_file(str(ROOT / parm7), str(ROOT / coords))
    for a in st.atoms:            # parm7 atoms carry no serials; stamp the topology numbers
        a.number = a.idx + 1
    for r in st.residues:
        r.number = r.idx + 1
    st.strip(f"!(:{int(metal)}<:{RADIUS})")
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".tmp.pdb")
    st.save(str(tmp), overwrite=True, renumber=False)
    header = [f"HEADER    ACTIVESITE REFERENCE SITE {case_id.upper():<22}",
              SERIALS_REMARK,
              f"REMARK 900 ACTIVESITE SOURCE {parm7} + {coords}, residues within {RADIUS} A of :{metal}"]
    body = [line for line in tmp.read_text().splitlines() if not line.startswith(("HEADER", "TITLE"))]
    out.write_text("\n".join(header + body) + "\n")
    tmp.unlink()
    return out
