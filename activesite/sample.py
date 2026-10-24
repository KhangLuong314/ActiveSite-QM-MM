"""ActiveSite — sample mode: replay cached engine output and prepared artefacts.

When ``SAMPLE_MODE=true`` or Docker is unavailable, the Runner reads
``data/sample/<case>/charge<±N>/sp.out`` (or ``attempt<N>/sp.out`` whose echoed
``qmcharge`` matches the requested charge) through ``parse_sander_output``,
and LigandSetup loads ``data/sample/<case>/prep/`` (complex.parm7, min.rst7,
pdb2pqr.log, ligand.mol2, prep.json). Every other agent runs its real logic.
Cached files are produced only by ``scripts/make_samples.sh`` on a Docker
host; nothing here fabricates output. A missing cache is reported as such.
"""
from __future__ import annotations

import json
import os
import re
import shutil
from pathlib import Path
from typing import Any, Dict, Optional

from activesite.chem.sander import parse_sander_output

CACHED_LABEL = "cached engine output (sample mode)"
PREP_FILES = ("complex.parm7", "min.rst7", "pdb2pqr.log", "ligand.mol2", "prep.json")


def sample_root() -> Path:
    return Path(os.getenv("ACTIVESITE_SAMPLE_DIR", "data/sample"))


def _echoed_charge(text: str) -> Optional[int]:
    # The &qmmm namelist line (leading whitespace), not the free-text title line.
    m = re.search(r"^\s*qmcharge\s*=\s*([-+]?\d+)", text, re.M)
    return int(m.group(1)) if m else None


def cached_engine_result(case_id: str, attempt: int, charge: int, theory: str = "PM6") -> Dict[str, Any]:
    """Parsed cached sp.out for this case/charge, or a skipped result naming what is missing."""
    root = sample_root() / case_id
    candidates = [root / f"charge{charge:+d}" / "sp.out", root / f"attempt{attempt}" / "sp.out"]
    for path in candidates:
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        echoed = _echoed_charge(text)
        if echoed is not None and echoed != charge:
            continue  # a cached run for a different charge is not this run
        parsed = parse_sander_output(text, theory)
        return {**parsed, "cached": True, "skipped": False, "exit_code": 0 if parsed["ok"] else 1, "wall_time_s": 0.0,
                "mdout": str(path), "workdir": str(path.parent), "sample_source": str(path)}
    return {"ok": False, "skipped": True, "cached": False, "qm_escf_kcal": None, "total_energy_kcal": None,
            "odd_electrons": None, "link_atoms": None, "exit_code": None, "wall_time_s": 0.0,
            "errors": [f"engine not run: SAMPLE_MODE=true and no cached sample output for qmcharge {charge:+d} "
                       f"under {root} (run scripts/make_samples.sh on a Docker host)"]}


def cached_md_result(case_id: str, charge: int, theory: str = "PM6") -> Dict[str, Any]:
    """Parsed cached md.out and traj.nc for this case/charge, or a skipped result naming what is missing."""
    root = sample_root() / case_id / "md"
    mdout = root / "md.out"
    traj = root / "traj.nc"
    if mdout.exists():
        text = mdout.read_text(encoding="utf-8", errors="replace")
        echoed = _echoed_charge(text)
        if echoed is None or echoed == charge:
            from activesite.chem.sander import parse_sander_md_output
            parsed = parse_sander_md_output(text, theory)
            return {
                **parsed,
                "cached": True,
                "skipped": False,
                "exit_code": 0 if parsed["ok"] else 1,
                "wall_time_s": 0.0,
                "mdout": str(mdout),
                "traj": str(traj) if traj.exists() else None,
                "workdir": str(root),
                "sample_source": str(mdout),
            }
    return {
        "ok": False,
        "skipped": True,
        "cached": False,
        "steps_completed": 0,
        "final_temperature_k": None,
        "qm_escf_kcal": None,
        "total_energy_kcal": None,
        "qm_resp_charge_sum": None,
        "link_atoms": None,
        "odd_electrons": None,
        "energy_progression": [],
        "averages": {},
        "rms_fluctuations": {},
        "exit_code": None,
        "wall_time_s": 0.0,
        "traj": None,
        "mdout": None,
        "errors": [
            f"MD simulation not run: SAMPLE_MODE=true and no cached MD trajectory for {case_id} "
            f"under {root} (run with --docker on a Docker host)"
        ],
    }


def cached_prep(case_id: str, work: Path | str) -> Optional[Dict[str, Any]]:
    """Copy the cached preparation into ``work`` and return the saved setup evidence, or None."""
    src = sample_root() / case_id / "prep"
    if not (src / "prep.json").exists():
        return None
    work = Path(work)
    work.mkdir(parents=True, exist_ok=True)
    for name in PREP_FILES:
        if (src / name).exists():
            shutil.copy(src / name, work / name)
    setup = json.loads((src / "prep.json").read_text(encoding="utf-8"))
    setup.setdefault("complex", {})["parm7"] = str(work / "complex.parm7")
    setup["complex"]["rst7"] = str(work / "complex.rst7")
    setup.setdefault("minimisation", {})["rst7"] = str(work / "min.rst7")
    setup["work"] = str(work)
    setup["prep_cached"] = str(src)
    return setup


def prep_missing_reason(case_id: str) -> str:
    return (f"prep not run: SAMPLE_MODE=true and no cached preparation under {sample_root() / case_id / 'prep'} "
            f"(run scripts/make_samples.sh on a Docker host)")


def serialisable_setup(setup: Dict[str, Any]) -> Dict[str, Any]:
    """The ligand setup dict without non-JSON values, for prep.json."""
    keep = ("kind", "mask", "theory", "charge", "overrides", "chain", "chain_source", "chain_table", "extract", "crystal_contacts",
            "ligand_site", "protonation", "his_review", "ligand_parameters", "complex", "minimisation", "pose_built", "pose_min")
    out = {k: setup[k] for k in keep if k in setup}
    if "protonation" in out and "pka_table" in out["protonation"]:
        out["protonation"] = {k: v for k, v in out["protonation"].items() if k != "pka_table"}
    return json.loads(json.dumps(out, default=str))
