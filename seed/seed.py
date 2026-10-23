"""Seed the local data layer for catalog-STANDIN (DuckDB).

Creates ``lab_runs`` in Postgres (one row per case; the I-PpoI site-A expert
mask and charge come from data/reference/qmmm_dft/gen_inputs.sh, site B's bare
residue list from gen_qmmask.py and is marked unverified, ligand cases have no
expert record) and uploads ``eda_synthetic.parquet`` to MinIO. The EDA table is
SYNTHETIC: data/reference/wtp/theories.csv is a list of theory levels, not an
energy decomposition, so the rows here are placeholders named as such.

Usage: docker compose up -d && uv run python seed/seed.py
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REF = ROOT / "data/reference/qmmm_dft"


def expert_from_gen_inputs() -> tuple[str, int]:
    text = (REF / "gen_inputs.sh").read_text()
    var = lambda n: re.search(rf'^{n}="([^"]*)"', text, re.M).group(1)  # noqa: E731
    mask = var("QMMASK").replace("\\", "")
    for n in ("PROTEIN", "METAL", "WATER"):
        mask = mask.replace("${%s}" % n, var(n))
    return mask, int(var("QMCHARGE"))


def site_b_from_gen_qmmask() -> tuple[str, str]:
    pairs = re.findall(r"\[\s*'(\w+)',\s*':(\d+)'\]", (REF / "gen_qmmask.py").read_text())
    return ":" + ",".join(n for _, n in pairs), " ".join(f"{r}{n}" for r, n in pairs)


def lab_rows() -> list[dict]:
    rows = []
    mask_a, charge_a = expert_from_gen_inputs()
    mask_b, residues_b = site_b_from_gen_qmmask()
    for path in sorted((ROOT / "cases").glob("*.json")):
        case = json.loads(path.read_text())
        row = {"case_id": case["id"], "system": case["system"], "site": case.get("site", "A"), "qmmask": None,
               "qmcharge": None, "residues": None, "source": "none", "status": "none"}
        if case["id"] == "ippoi_site_a":
            row.update(qmmask=mask_a, qmcharge=charge_a, source="data/reference/qmmm_dft/gen_inputs.sh (QMMASK, QMCHARGE)",
                       status="expert")
        elif case["id"] == "ippoi_site_b":
            row.update(qmmask=mask_b, residues=residues_b, source="data/reference/qmmm_dft/gen_qmmask.py (fragment, whole residues)",
                       status="unverified")
        else:
            row.update(qmmask=":LIG", source="case file (whole ligand)", status="none")
        rows.append(row)
    return rows


def seed_postgres(dsn: str) -> int:
    import psycopg2

    con = psycopg2.connect(dsn)
    cur = con.cursor()
    cur.execute("""CREATE TABLE IF NOT EXISTS lab_runs (
        case_id TEXT PRIMARY KEY, system TEXT NOT NULL, site TEXT NOT NULL, qmmask TEXT, qmcharge INTEGER,
        residues TEXT, source TEXT NOT NULL, status TEXT NOT NULL)""")
    rows = lab_rows()
    for r in rows:
        cur.execute("""INSERT INTO lab_runs (case_id, system, site, qmmask, qmcharge, residues, source, status)
                       VALUES (%(case_id)s, %(system)s, %(site)s, %(qmmask)s, %(qmcharge)s, %(residues)s, %(source)s, %(status)s)
                       ON CONFLICT (case_id) DO UPDATE SET qmmask = EXCLUDED.qmmask, qmcharge = EXCLUDED.qmcharge,
                       residues = EXCLUDED.residues, source = EXCLUDED.source, status = EXCLUDED.status""", r)
    con.commit()
    con.close()
    return len(rows)


SYNTHETIC_EDA = [
    {"family": "homing_endonuclease_synthetic", "residue": "SYNTHETIC-RES1", "total": -12.0, "note": "synthetic placeholder, not a measurement"},
    {"family": "homing_endonuclease_synthetic", "residue": "SYNTHETIC-RES2", "total": 7.5, "note": "synthetic placeholder, not a measurement"},
    {"family": "homing_endonuclease_synthetic", "residue": "SYNTHETIC-RES3", "total": -3.1, "note": "synthetic placeholder, not a measurement"},
]


def seed_minio(endpoint: str, bucket: str = "activesite") -> str:
    import duckdb

    local = ROOT / "data/cache/eda_synthetic.parquet"
    local.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    con.execute("CREATE TABLE eda_synthetic (family VARCHAR, residue VARCHAR, total DOUBLE, note VARCHAR)")
    con.executemany("INSERT INTO eda_synthetic VALUES (?, ?, ?, ?)", [(r["family"], r["residue"], r["total"], r["note"]) for r in SYNTHETIC_EDA])
    con.execute(f"COPY eda_synthetic TO '{local}' (FORMAT PARQUET)")
    try:
        con.execute("LOAD httpfs")
    except duckdb.Error:
        con.execute("INSTALL httpfs; LOAD httpfs")
    host = re.sub(r"^https?://", "", endpoint).rstrip("/")
    con.execute(f"SET s3_endpoint='{host}'; SET s3_use_ssl=false; SET s3_url_style='path'")
    con.execute(f"SET s3_access_key_id='{os.getenv('MINIO_ROOT_USER', 'minioadmin')}'")
    con.execute(f"SET s3_secret_access_key='{os.getenv('MINIO_ROOT_PASSWORD', 'minioadmin')}'")
    target = f"s3://{bucket}/eda/eda_synthetic.parquet"
    con.execute(f"COPY eda_synthetic TO '{target}' (FORMAT PARQUET)")
    return target


def main() -> int:
    dsn = os.getenv("POSTGRES_DSN", "postgresql://lab@127.0.0.1:56432/activesite")
    endpoint = os.getenv("MINIO_ENDPOINT", "http://127.0.0.1:59100")
    n = seed_postgres(dsn)
    print(f"lab_runs: {n} rows in {dsn}")
    print(f"eda_synthetic: uploaded to {seed_minio(endpoint)} (SYNTHETIC placeholder table)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
