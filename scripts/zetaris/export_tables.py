"""Export the three DataScout tables to CSV for Zetaris.

Run from the repo root: ``uv run python scripts/zetaris/export_tables.py <out_dir>``.
Writes ``<out_dir>/<table>/<table>.csv`` for lab_runs (lab expert QM regions from seed.lab_rows()),
eda_synthetic (SYNTHETIC placeholder, seed.SYNTHETIC_EDA) and rcsb_entries (each case's RCSB search, read from
data/cache/rcsb when present, otherwise fetched with the stand-in's own RCSB code and cached).
"""
from __future__ import annotations

import csv
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _seed():
    spec = importlib.util.spec_from_file_location("seed", ROOT / "seed/seed.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def write(out: Path, name: str, cols: list[str], rows: list[dict]) -> None:
    d = out / name
    d.mkdir(parents=True, exist_ok=True)
    with open(d / f"{name}.csv", "w", newline="") as f:
        w = csv.writer(f, quoting=csv.QUOTE_NONNUMERIC)
        w.writerow(cols)
        for r in rows:
            w.writerow([r.get(c) for c in cols])
    print(name, len(rows), "rows")


def _rcsb_rows() -> list[dict]:
    sys.path.insert(0, str(ROOT))
    from activesite.adapters.catalog_standin import CatalogStandin

    rows, seen = [], set()
    for f in sorted((ROOT / "cases").glob("*.json")):
        case = json.loads(f.read_text())
        if not case.get("pdb_query") or (case.get("system"), case["pdb_query"]) in seen:
            continue
        seen.add((case.get("system"), case["pdb_query"]))
        cat = CatalogStandin(offline=False)
        cat.system, cat.pdb_query = case.get("system"), case["pdb_query"]
        rows += [{**r, "system": r.get("system") or case.get("system")} for r in cat._rcsb_rows()]
    return rows


def main(out: Path) -> None:
    seed = _seed()
    write(out, "lab_runs", ["case_id", "system", "site", "qmmask", "qmcharge", "residues", "source", "status"],
          seed.lab_rows())
    write(out, "eda_synthetic", ["family", "residue", "total", "note"], seed.SYNTHETIC_EDA)
    write(out, "rcsb_entries", ["pdb_id", "resolution", "title", "system", "source"], _rcsb_rows())


if __name__ == "__main__":
    main(Path(sys.argv[1]))
