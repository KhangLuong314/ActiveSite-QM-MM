"""ActiveSite — "bring your own structure": parse, store and point-mutate user PDB / mmCIF files.

Everything here is pure Python (no container, no new dependency). Uploaded bytes and names are untrusted:

* the file extension is allow-listed (.pdb, .cif, .mmcif) and the size is capped (MAX_BYTES);
* the stored files get server-chosen names under ``<uploads root>/<uuid hex>/``; the user's file name and display
  name are never used to build a path, and every structure id is checked against ``ID_RE`` before it touches disk;
* chain / residue / mutation tokens are validated with strict regexes before use; nothing is passed to a shell.

mmCIF is converted to PDB with a small ``_atom_site`` loop reader below (parmed's CIF reader fails on several
predicted-model files and gemmi is not a dependency). If a file cannot be written as PDB (multi-character chain ids,
more than 99,999 atoms) it is stored as-is and the record says so; such a structure cannot be run.

Mutation is a standard template rebuild: rename the residue, delete side-chain atoms beyond CB (CB too for X->GLY),
keep the backbone. The missing side chain is rebuilt later in the normal prep pipeline (PDB2PQR's missing-heavy-atom
repair, then tleap's ff14SB residue template). There is no rotamer search and no repacking of neighbours.
"""
from __future__ import annotations

import json
import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
MAX_BYTES = 20 * 1024 * 1024
ALLOWED_EXT = {".pdb": "pdb", ".cif": "cif", ".mmcif": "cif"}
ID_RE = re.compile(r"^[0-9a-f]{32}$")
CHAIN_RE = re.compile(r"^[A-Za-z0-9]$")
RESNAME_RE = re.compile(r"^[A-Z0-9]{1,3}$")
MUTATION_RE = re.compile(r"^([A-Za-z0-9]):([A-Z])(-?\d{1,4})([A-Z])$")
NAME_SAFE = re.compile(r"[^A-Za-z0-9 ._()+-]")
MAX_MUTATIONS = 20
STORED_PDB = "structure.pdb"
META = "meta.json"
METHOD = ("point mutation by template rebuild: wild type checked, residue renamed, side-chain atoms beyond CB deleted "
          "(CB too for X->GLY), backbone kept; the side chain is rebuilt in the prep pipeline by PDB2PQR's missing-atom "
          "repair and the tleap ff14SB template. No rotamer search, no repacking of neighbouring residues.")

ONE_TO_THREE = {"A": "ALA", "R": "ARG", "N": "ASN", "D": "ASP", "C": "CYS", "Q": "GLN", "E": "GLU", "G": "GLY",
                "H": "HIS", "I": "ILE", "L": "LEU", "K": "LYS", "M": "MET", "F": "PHE", "P": "PRO", "S": "SER",
                "T": "THR", "W": "TRP", "Y": "TYR", "V": "VAL"}
THREE_TO_ONE = {v: k for k, v in ONE_TO_THREE.items()} | {"HID": "H", "HIE": "H", "HIP": "H"}
BACKBONE = {"N", "CA", "C", "O", "OXT"}
WATERS = {"HOH", "WAT", "DOD", "H2O", "TIP", "TIP3", "SOL"}
# Common crystallisation / cryo / buffer components and counter-ions: reported as additives, never as the ligand.
ADDITIVES = {"SO4", "GOL", "EDO", "PEG", "PGE", "PG4", "1PE", "P6G", "ACT", "ACY", "CL", "NA", "K", "BR", "IOD", "PO4",
             "NO3", "FMT", "MPD", "MRD", "DMS", "BME", "TRS", "MES", "EPE", "HEZ", "IMD", "CIT", "FLC", "IPA", "EOH",
             "MOH", "BU3", "PE4", "SCN", "AZI", "NH4", "TAR", "MLI", "SIN", "UNX", "CO3", "BCT", "OXL", "DTT", "ACE"}
METALS = {"MG", "ZN", "MN", "FE", "FE2", "CA", "CU", "CU1", "CO", "NI", "CD", "HG", "MO", "W", "V", "CR", "PT", "AU",
          "AG", "PB", "SR", "BA", "LI", "RB", "CS", "AL", "GA", "TL", "SN", "LA", "EU", "GD", "TB", "YB", "PD", "RU",
          "IR", "OS", "ZR", "Y", "SC", "TI"}
METAL_COORD_MAX = 3.0  # Å, side-chain N/O/S to metal counted as coordinating


class UploadError(ValueError):
    """A user-facing validation error (the API turns it into HTTP 400/413/422)."""

    def __init__(self, message: str, status: int = 422):
        super().__init__(message)
        self.status = status


def uploads_root() -> Path:
    return Path(os.getenv("ACTIVESITE_UPLOADS_DIR", str(ROOT / "data" / "uploads")))


def structure_dir(structure_id: str) -> Path:
    if not isinstance(structure_id, str) or not ID_RE.match(structure_id):
        raise UploadError(f"invalid structure id {str(structure_id)[:40]!r}", status=400)
    d = uploads_root() / structure_id
    if not (d / META).exists():
        raise UploadError(f"unknown structure {structure_id}", status=404)
    return d


def safe_display_name(name: Optional[str], fallback: str = "structure") -> str:
    """A display-only name: no path parts, a conservative character set, at most 64 characters."""
    raw = (name or "").replace("\\", "/").split("/")[-1].strip()
    clean = NAME_SAFE.sub("_", raw).strip(" .")[:64]
    return clean or fallback


def extension_format(filename: Optional[str]) -> str:
    suffix = Path((filename or "").replace("\\", "/").split("/")[-1]).suffix.lower()
    if suffix not in ALLOWED_EXT:
        raise UploadError(f"file type {suffix or '(none)'!r} not accepted; upload .pdb, .cif or .mmcif", status=415)
    return ALLOWED_EXT[suffix]


# ------------------------------------------------------------------ parsing
def _pdb_atom(line: str, lineno: int) -> Dict[str, Any]:
    try:
        name = line[12:16].strip()
        element = line[76:78].strip().upper() if len(line) >= 78 else ""
        if not element:
            element = re.sub(r"[^A-Za-z]", "", name)[:1].upper()
        return {"record": line[:6].strip(), "serial": line[6:11].strip(), "name": name, "altloc": line[16] if len(line) > 16 else " ",
                "resname": line[17:20].strip(), "chain": line[21] if len(line) > 21 else " ", "resnum": int(line[22:26]),
                "icode": line[26] if len(line) > 26 else " ", "x": float(line[30:38]), "y": float(line[38:46]),
                "z": float(line[46:54]), "element": element}
    except (ValueError, IndexError):
        raise UploadError(f"line {lineno} is not a valid PDB ATOM/HETATM record: {line[:60]!r}")


def clean_pdb_text(text: str) -> Tuple[str, List[str]]:
    """First model only; header records kept (REMARK 465/470 matter for chain choice); ANISOU/CONECT dropped."""
    out: List[str] = []
    warnings: List[str] = []
    in_model, models, seen_coords = False, 0, False
    for raw in text.splitlines():
        rec = raw[:6].strip()
        if rec == "MODEL":
            models += 1
            in_model = models == 1
            continue
        if rec == "ENDMDL":
            if models >= 1:
                in_model = False
            continue
        if models > 1 and not in_model:
            continue
        if rec in ("ATOM", "HETATM", "TER"):
            seen_coords = True
            out.append(raw.rstrip())
        elif rec in ("ANISOU", "CONECT", "MASTER", "END"):
            continue
        elif not seen_coords:
            out.append(raw.rstrip())
    if models > 1:
        warnings.append(f"{models} models in the file; only model 1 is kept")
    return "\n".join(out) + "\nEND\n", warnings


def _cif_tokens(line: str) -> List[str]:
    # CIF quoting: a quote closes only when followed by whitespace or end of line (so O5' inside "O5'" survives)
    toks = re.findall(r"'(?:[^']|'(?=\S))*'|\"(?:[^\"]|\"(?=\S))*\"|\S+", line)
    return [t[1:-1] if len(t) >= 2 and t[0] == t[-1] and t[0] in "'\"" else t for t in toks]


def cif_atom_rows(text: str) -> List[Dict[str, str]]:
    lines = text.splitlines()
    i, n = 0, len(lines)
    while i < n:
        if lines[i].strip() == "loop_" and i + 1 < n and lines[i + 1].strip().startswith("_atom_site."):
            headers: List[str] = []
            i += 1
            while i < n and lines[i].strip().startswith("_atom_site."):
                headers.append(lines[i].strip().split(".", 1)[1].split()[0])
                i += 1
            rows: List[Dict[str, str]] = []
            buf: List[str] = []
            while i < n:
                s = lines[i].strip()
                if s.startswith(("_", "loop_", "data_")) or s == "#":
                    break
                if s:
                    buf += _cif_tokens(s)
                    while len(buf) >= len(headers):
                        rows.append(dict(zip(headers, buf[:len(headers)])))
                        buf = buf[len(headers):]
                i += 1
            return rows
        i += 1
    return []


def _fmt_name(name: str, element: str) -> str:
    if len(name) < 4 and len(element) == 1:
        name = " " + name
    return f"{name:<4s}"[:4]


def cif_to_pdb(text: str) -> Tuple[Optional[str], List[str]]:
    """(PDB text or None if it cannot be written as PDB, warnings). Raises UploadError if there is no atom_site loop."""
    rows = cif_atom_rows(text)
    if not rows:
        raise UploadError("no _atom_site loop found; this does not look like an mmCIF coordinate file")
    warnings: List[str] = ["converted from mmCIF to PDB (author chain ids and residue numbers kept); "
                           "mmCIF has no REMARK 465/470, so chain choice cannot see missing residues"]
    first_model = rows[0].get("pdbx_PDB_model_num", "1")
    rows = [r for r in rows if r.get("pdbx_PDB_model_num", "1") == first_model]
    if len(rows) > 99999:
        return None, warnings + [f"{len(rows)} atoms is too many for the PDB format; stored as mmCIF only"]

    def g(r: Dict[str, str], *keys: str, default: str = "") -> str:
        for k in keys:
            v = r.get(k)
            if v not in (None, "?", "."):
                return v
        return default

    lines = []
    for serial, r in enumerate(rows, start=1):
        chain = g(r, "auth_asym_id", "label_asym_id", default="A")
        if len(chain) != 1:
            return None, warnings + [f"chain id {chain[:8]!r} has more than one character; PDB cannot hold it; stored as mmCIF only"]
        try:
            resi = int(g(r, "auth_seq_id", "label_seq_id", default="0"))
            x, y, z = (float(g(r, f"Cartn_{c}")) for c in "xyz")
            occ = float(g(r, "occupancy", default="1.0"))
            b = float(g(r, "B_iso_or_equiv", default="0.0"))
        except ValueError:
            raise UploadError(f"atom_site row {serial} has non-numeric coordinates or residue number")
        element = g(r, "type_symbol", default="").upper()[:2]
        name = g(r, "auth_atom_id", "label_atom_id", default="X")[:4]
        resname = g(r, "auth_comp_id", "label_comp_id", default="UNK")[:3]
        alt = g(r, "label_alt_id", default=" ")[:1]
        icode = g(r, "pdbx_PDB_ins_code", default=" ")[:1]
        rec = "HETATM" if g(r, "group_PDB", default="ATOM") == "HETATM" else "ATOM"
        if abs(resi) > 9999:
            return None, warnings + [f"residue number {resi} does not fit the PDB format; stored as mmCIF only"]
        lines.append(f"{rec:<6s}{serial:>5d} {_fmt_name(name, element)}{alt:1s}{resname:>3s} {chain:1s}{resi:>4d}{icode:1s}   "
                     f"{x:8.3f}{y:8.3f}{z:8.3f}{occ:6.2f}{b:6.2f}          {element:>2s}")
    return "REMARK 900 ACTIVESITE CONVERTED FROM MMCIF\n" + "\n".join(lines) + "\nEND\n", warnings


def read_atoms(pdb_text: str) -> List[Dict[str, Any]]:
    atoms = []
    for lineno, line in enumerate(pdb_text.splitlines(), start=1):
        if line[:6].strip() in ("ATOM", "HETATM"):
            atoms.append(_pdb_atom(line, lineno))
    return atoms


def _residues(atoms: Iterable[Dict[str, Any]]) -> Dict[Tuple[str, int, str, str], List[Dict[str, Any]]]:
    res: Dict[Tuple[str, int, str, str], List[Dict[str, Any]]] = {}
    for a in atoms:
        res.setdefault((a["chain"], a["resnum"], a["icode"], a["resname"]), []).append(a)
    return res


def _heavy(atoms: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [a for a in atoms if a["element"] not in ("H", "D")]


def _is_metal(resname: str, atoms: List[Dict[str, Any]]) -> bool:
    return len(atoms) == 1 and (resname in METALS or atoms[0]["element"] in METALS) and resname not in ADDITIVES


def summarise(pdb_text: str) -> Dict[str, Any]:
    """Chains, ligand candidates, metals, additives and warnings from a PDB text (first model)."""
    atoms = read_atoms(pdb_text)
    if not atoms:
        raise UploadError("no ATOM/HETATM records found; the file contains no coordinates")
    warnings: List[str] = []
    chains: Dict[str, set] = {}
    for a in atoms:
        if a["record"] == "ATOM":
            chains.setdefault(a["chain"], set()).add((a["resnum"], a["icode"]))
    ligands, metals, additives, modified = [], [], [], []
    for (chain, resi, icode, resname), ra in _residues(a for a in atoms if a["record"] == "HETATM").items():
        if resname in WATERS:
            continue
        names = {a["name"] for a in ra}
        if _is_metal(resname, ra):
            el = ra[0]["element"] if ra[0]["element"] in METALS else resname
            metals.append({"resname": resname, "element": el.capitalize(), "chain": chain, "resi": resi})
        elif resname in ADDITIVES:
            additives.append({"resname": resname, "chain": chain, "resi": resi})
        elif {"N", "CA", "C"} <= names:
            modified.append(f"{resname}{resi}{chain}")
        else:
            ligands.append({"resname": resname, "chain": chain, "resi": resi, "n_heavy_atoms": len(_heavy(ra))})
    if additives:
        names = sorted({a["resname"] for a in additives})
        warnings.append(f"{len(additives)} buffer/cryo additives or counter-ions ({', '.join(names)}) flagged as additives, "
                        f"not ligands; they are dropped from QM/MM preparation")
    if modified:
        warnings.append(f"modified residues as HETATM ({', '.join(modified[:8])}) are dropped by preparation and leave a gap")
    if any(a["altloc"] not in (" ", "A") for a in atoms):
        warnings.append("alternate locations present; only altloc A (or blank) is kept")
    if any(a["element"] in ("H", "D") for a in atoms):
        warnings.append("hydrogens present; preparation strips and re-adds them with PDB2PQR")
    if not any(line.startswith("REMARK 465") for line in pdb_text.splitlines()):
        warnings.append("no REMARK 465 (missing residues) records; gaps near the pocket cannot be detected from the header")
    if not ligands and not metals:
        warnings.append("no ligand or metal found; a custom run needs a ligand (HETATM residue) or a metal site")
    seen: Dict[Tuple[str, str], int] = {}
    for lg in ligands:
        seen[(lg["resname"], lg["chain"])] = seen.get((lg["resname"], lg["chain"]), 0) + 1
    for (rn, ch), k in seen.items():
        if k > 1:
            warnings.append(f"ligand {rn} occurs {k} times in chain {ch}; runs need one copy per chain")
    return {"chains": [{"id": c, "n_residues": len(r)} for c, r in sorted(chains.items())], "ligands": ligands,
            "metals": metals, "additives": additives, "n_atoms": len(atoms), "warnings": warnings}


# ------------------------------------------------------------------ storage
def _write_record(pdb_text: Optional[str], original: bytes, fmt: str, name: str, warnings: List[str],
                  extra: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    sid = uuid.uuid4().hex
    d = uploads_root() / sid
    d.mkdir(parents=True, exist_ok=False)
    (d / ("original.cif" if fmt == "cif" else "original.pdb")).write_bytes(original)
    summary = summarise(pdb_text) if pdb_text is not None else {"chains": [], "ligands": [], "metals": [], "additives": [],
                                                              "n_atoms": len(cif_atom_rows(original.decode("utf-8", "replace"))),
                                                              "warnings": []}
    if pdb_text is not None:
        (d / STORED_PDB).write_text(pdb_text, encoding="utf-8")
    record = {"structure_id": sid, "name": name, "format": fmt, **summary,
              "warnings": warnings + summary["warnings"], "runnable": pdb_text is not None,
              "file_format_served": "pdb" if pdb_text is not None else "cif",
              "created_at": datetime.now(timezone.utc).isoformat()}
    if extra:
        record.update(extra)
    (d / META).write_text(json.dumps(record, indent=1), encoding="utf-8")
    return record


def save_upload(data: bytes, filename: Optional[str], name: Optional[str] = None) -> Dict[str, Any]:
    fmt = extension_format(filename)
    if len(data) > MAX_BYTES:
        raise UploadError(f"file is larger than {MAX_BYTES // (1024 * 1024)} MB", status=413)
    if not data.strip():
        raise UploadError("empty file")
    if b"\x00" in data[:4096]:
        raise UploadError("binary file; upload a text PDB or mmCIF")
    text = data.decode("utf-8", errors="replace")
    display = safe_display_name(name or Path(safe_display_name(filename)).stem)
    if fmt == "cif":
        pdb_text, warnings = cif_to_pdb(text)
        if pdb_text is None:
            warnings.append("served as the original mmCIF; runs need a PDB-representable structure")
    else:
        pdb_text, warnings = clean_pdb_text(text)
    return _write_record(pdb_text, data, fmt, display, warnings)


def load_record(structure_id: str) -> Dict[str, Any]:
    return json.loads((structure_dir(structure_id) / META).read_text(encoding="utf-8"))


def structure_file(structure_id: str) -> Tuple[Path, str]:
    d = structure_dir(structure_id)
    if (d / STORED_PDB).exists():
        return d / STORED_PDB, "pdb"
    return d / "original.cif", "cif"


def list_records() -> List[Dict[str, Any]]:
    root = uploads_root()
    out = []
    if root.exists():
        for d in root.iterdir():
            if d.is_dir() and ID_RE.match(d.name) and (d / META).exists():
                try:
                    out.append(json.loads((d / META).read_text(encoding="utf-8")))
                except (OSError, ValueError):
                    continue
    return sorted(out, key=lambda r: r.get("created_at", ""), reverse=True)


# ----------------------------------------------------------------- mutation
def parse_mutation(token: str) -> Dict[str, Any]:
    m = MUTATION_RE.match(str(token).strip()) if isinstance(token, str) else None
    if not m:
        raise UploadError(f"mutation {str(token)[:20]!r} must look like A:Y61F (chain:from resnum to, one-letter codes)")
    chain, frm, resi, to = m.group(1), m.group(2), int(m.group(3)), m.group(4)
    for aa in (frm, to):
        if aa not in ONE_TO_THREE:
            raise UploadError(f"{aa!r} in {token} is not one of the 20 standard amino acids; non-standard residues are not supported")
    if frm == to:
        raise UploadError(f"{token} does not change the residue")
    return {"chain": chain, "resi": resi, "from": frm, "to": to, "token": f"{chain}:{frm}{resi}{to}"}


def _coordinating(res_atoms: List[Dict[str, Any]], metal_atoms: List[Dict[str, Any]]) -> Optional[Tuple[str, str, float]]:
    side = [a for a in res_atoms if a["name"] not in BACKBONE and a["element"] in ("N", "O", "S")]
    best = None
    for a in side:
        for m in metal_atoms:
            d = float(np.linalg.norm(np.array([a["x"] - m["x"], a["y"] - m["y"], a["z"] - m["z"]])))
            if d <= METAL_COORD_MAX and (best is None or d < best[2]):
                best = (a["name"], f"{m['resname']}{m['resnum']}{m['chain']}", round(d, 2))
    return best


def mutate(structure_id: str, mutations: List[str], force: bool = False) -> Dict[str, Any]:
    parent = load_record(structure_id)
    path, fmt = structure_file(structure_id)
    if fmt != "pdb":
        raise UploadError("this structure is stored as mmCIF only and cannot be mutated")
    if not isinstance(mutations, list) or not mutations:
        raise UploadError("give at least one mutation, e.g. [\"A:Y61F\"]")
    if len(mutations) > MAX_MUTATIONS:
        raise UploadError(f"at most {MAX_MUTATIONS} mutations per request")
    muts = [parse_mutation(t) for t in mutations]
    if len({(m["chain"], m["resi"]) for m in muts}) != len(muts):
        raise UploadError("the same residue is mutated twice")
    text = path.read_text(encoding="utf-8")
    atoms = read_atoms(text)
    metal_atoms = [a for a in atoms if a["record"] == "HETATM" and _is_metal(a["resname"], [a])]
    applied = []
    for m in muts:
        ra = [a for a in atoms if a["record"] == "ATOM" and a["chain"] == m["chain"] and a["resnum"] == m["resi"]]
        if not ra:
            raise UploadError(f"{m['token']}: no protein residue {m['resi']} in chain {m['chain']}")
        if len({a["icode"] for a in ra}) > 1:
            raise UploadError(f"{m['token']}: residue {m['resi']} has insertion codes; not supported")
        resname = ra[0]["resname"]
        if resname not in THREE_TO_ONE:
            raise UploadError(f"{m['token']}: residue {m['resi']}{m['chain']} is {resname}, a non-standard residue; not supported")
        if THREE_TO_ONE[resname] != m["from"]:
            raise UploadError(f"{m['token']}: wild type at {m['chain']}:{m['resi']} is {resname} "
                              f"({THREE_TO_ONE[resname]}), not {ONE_TO_THREE[m['from']]} ({m['from']})")
        coord = _coordinating(ra, metal_atoms)
        if coord and not force:
            raise UploadError(f"{m['token']}: {resname}{m['resi']} {coord[0]} coordinates metal {coord[1]} at {coord[2]} Å; "
                              f"mutating a metal ligand changes the site; resend with \"force\": true to do it anyway")
        applied.append({"chain": m["chain"], "resi": m["resi"], "from": m["from"], "to": m["to"], "from_resname": resname,
                        "to_resname": ONE_TO_THREE[m["to"]], "metal_coordinating": coord is not None})
    targets = {(a["chain"], a["resi"]): a for a in applied}
    out_lines = []
    removed: Dict[str, List[str]] = {}
    for line in text.splitlines():
        if line[:6].strip() == "ATOM":
            key = (line[21], int(line[22:26]))
            if key in targets:
                t = targets[key]
                name = line[12:16].strip()
                element = (line[76:78].strip().upper() if len(line) >= 78 else "") or re.sub(r"[^A-Za-z]", "", name)[:1].upper()
                keep = name in BACKBONE or (name == "CB" and t["to"] != "G")
                if element in ("H", "D") or not keep:
                    removed.setdefault(f"{t['chain']}:{t['resi']}", []).append(name)
                    continue
                line = line[:17] + f"{t['to_resname']:>3s}" + line[20:]
        out_lines.append(line)
    tokens = ",".join(f"{a['chain']}:{a['from']}{a['resi']}{a['to']}" for a in applied)
    header = f"REMARK 900 ACTIVESITE MUTANT OF {structure_id} {tokens} (TEMPLATE REBUILD, NO ROTAMER SEARCH)"
    new_text = header + "\n" + "\n".join(out_lines) + "\n"
    for a in applied:
        a["removed_atoms"] = removed.get(f"{a['chain']}:{a['resi']}", [])
    name = safe_display_name(f"{parent['name']} {tokens}")
    warnings = [f"side chains of {tokens} deleted beyond CB and rebuilt later from the Amber template: no rotamer search, "
                f"no repacking"] + [f"{a['chain']}:{a['from']}{a['resi']}{a['to']} coordinates a metal (forced)"
                                    for a in applied if a["metal_coordinating"]]
    lineage = list(parent.get("mutations_applied") or []) + [f"{a['chain']}:{a['from']}{a['resi']}{a['to']}" for a in applied]
    return _write_record(new_text, new_text.encode("utf-8"), "pdb", name, warnings,
                         extra={"parent_id": structure_id, "applied": applied, "method": METHOD,
                                "mutations_applied": lineage, "root_name": parent.get("root_name") or parent["name"]})
