"""ActiveSite — Data Scout Adapter.

Handles fetching and inspecting PDB structures, ligands, and metadata from
local reference storage or RCSB PDB REST API with offline fallbacks.
"""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional
import httpx
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

REFERENCE_DIR = Path("data/reference")
CASES_DIR = Path("cases")


class StructureMetadata(BaseModel):
    """Metadata for a resolved or downloaded macromolecular structure."""
    identifier: str
    title: str = ""
    resolution_angstrom: Optional[float] = None
    experimental_method: str = "X-RAY DIFFRACTION"
    ligands: List[str] = Field(default_factory=list)
    local_pdb_path: Optional[str] = None
    is_offline_cached: bool = False


class DataScout:
    """Scouts structures, ligands, and benchmark cases."""

    def __init__(self, cache_dir: Optional[Path] = None, timeout: float = 10.0):
        self.cache_dir = cache_dir or Path("data/cache")
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.timeout = timeout

    def ensure_pdb(self, pdb_path_or_id: str | Path) -> Path:
        """Ensure a PDB file exists locally; if missing, download from RCSB PDB."""
        p = Path(pdb_path_or_id)
        if p.exists():
            return p
        m = re.search(r"([0-9][a-zA-Z0-9]{3})", p.name)
        if not m:
            raise FileNotFoundError(f"PDB file not found and cannot infer RCSB PDB code from {pdb_path_or_id}")
        pdb_code = m.group(1).lower()
        meta = self.resolve_pdb(pdb_code)
        if meta and meta.local_pdb_path and Path(meta.local_pdb_path).exists():
            src = Path(meta.local_pdb_path)
            if src.resolve() != p.resolve():
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_bytes(src.read_bytes())
            return p
        raise FileNotFoundError(f"Could not load or download PDB structure for '{pdb_code}' to {p}")

    def load_benchmark_case(self, case_id: str) -> Dict[str, Any]:
        """Load a benchmark case definition from cases/ directory."""
        clean_id = case_id.removesuffix(".json")
        case_path = CASES_DIR / f"{clean_id}.json"
        if not case_path.exists():
            raise FileNotFoundError(f"Case '{case_id}' not found in {CASES_DIR}")
        with open(case_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if "pdb" in data:
            try:
                self.ensure_pdb(data["pdb"])
            except Exception as exc:
                logger.warning("Could not auto-download PDB for case %s: %s", case_id, exc)
        return data

    def list_benchmark_cases(self) -> List[str]:
        """List all available benchmark case IDs."""
        if not CASES_DIR.exists():
            return []
        return sorted([p.stem for p in CASES_DIR.glob("*.json")])

    def resolve_pdb(self, pdb_id: str) -> StructureMetadata:
        """Resolve a PDB structure either from local reference or RCSB PDB."""
        pdb_clean = pdb_id.strip().lower()

        # 1. Check local reference files first
        local_candidates = [
            REFERENCE_DIR / "egfr" / f"{pdb_clean}.pdb",
            REFERENCE_DIR / "abl" / f"{pdb_clean}.pdb",
            self.cache_dir / f"{pdb_clean}.pdb",
        ]
        for candidate in local_candidates:
            if candidate.exists():
                return self._inspect_local_pdb(pdb_clean.upper(), candidate)

        # 2. Attempt RCSB PDB download
        downloaded = self._fetch_from_rcsb(pdb_clean)
        if downloaded:
            return downloaded

        # 3. Fallback: check if any reference pdb contains matching name
        for p in REFERENCE_DIR.glob(f"**/{pdb_clean}*.pdb"):
            if p.exists():
                return self._inspect_local_pdb(pdb_clean.upper(), p)

        raise FileNotFoundError(
            f"PDB structure '{pdb_id}' could not be found locally or downloaded from RCSB PDB."
        )

    def _inspect_local_pdb(self, pdb_code: str, pdb_path: Path) -> StructureMetadata:
        """Extract basic header and ligand information from a local PDB file."""
        title = ""
        resolution = None
        method = "X-RAY DIFFRACTION"
        ligands = set()

        # Standard non-ligand residues to ignore
        standard_residues = {
            "ALA", "ARG", "ASN", "ASP", "CYS", "GLN", "GLU", "GLY", "HIS",
            "ILE", "LEU", "LYS", "MET", "PHE", "PRO", "SER", "THR", "TRP",
            "TYR", "VAL", "HOH", "WAT", "HIE", "HID", "HIP", "ASH", "GLH",
            "DA", "DG", "DC", "DT", "A", "G", "C", "U",
        }

        with open(pdb_path, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                if line.startswith("TITLE"):
                    title += line[10:].strip() + " "
                elif line.startswith("EXPDTA"):
                    method = line[10:].strip()
                elif "RESOLUTION." in line and "ANGSTROMS." in line:
                    parts = line.split()
                    for idx, part in enumerate(parts):
                        if "RESOLUTION" in part and idx + 1 < len(parts):
                            try:
                                resolution = float(parts[idx + 1])
                            except ValueError:
                                pass
                elif line.startswith("HETATM"):
                    resname = line[17:20].strip()
                    if resname not in standard_residues:
                        ligands.add(resname)

        return StructureMetadata(
            identifier=pdb_code,
            title=title.strip() or f"Structure {pdb_code}",
            resolution_angstrom=resolution,
            experimental_method=method,
            ligands=sorted(list(ligands)),
            local_pdb_path=str(pdb_path),
            is_offline_cached=True,
        )

    def _fetch_from_rcsb(self, pdb_code: str) -> Optional[StructureMetadata]:
        """Fetch PDB from RCSB PDB REST API and cache locally."""
        url = f"https://files.rcsb.org/download/{pdb_code}.pdb"
        dest_path = self.cache_dir / f"{pdb_code}.pdb"

        try:
            with httpx.Client(timeout=self.timeout) as client:
                resp = client.get(url)
                if resp.status_code == 200 and len(resp.text) > 100:
                    with open(dest_path, "w", encoding="utf-8") as f:
                        f.write(resp.text)
                    return self._inspect_local_pdb(pdb_code.upper(), dest_path)
        except Exception as exc:
            logger.warning("RCSB download failed for %s: %s", pdb_code, exc)

        return None
