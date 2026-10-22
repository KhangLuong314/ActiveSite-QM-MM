"""ActiveSite — protein-ligand complex preparation for QM/MM, with evidence.

Every chemistry tool (pdb2pqr/PROPKA, RDKit, antechamber, parmchk2, pdb4amber,
tleap, sander) runs inside the ``activesite-prep:at26`` container through
``dock``. The pure-Python parts (chain choice, ligand amine detection, His
tautomer review, mol2 finalisation, contact geometry) are testable without
Docker. Every function returns a plain dict carrying the numbers it used.

Writes go only to the given ``work`` directory and to ``CACHE``.
"""
from __future__ import annotations

import hashlib
import math
import re
import shutil
import subprocess
import time
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np

PREP_IMAGE = "activesite-prep:at26"
CACHE = Path("data/cache/ligands")
HBOND = 3.3           # Å, polar contact cutoff
PKA_WINDOW = 1.0      # pKa units around pH where a His state is "uncertain"
CATION_RANGE = 8.0    # Å, His ring N to ligand cation to count as "facing"
POCKET_RADIUS = 12.0  # Å, CA atoms within this of the ligand define the pocket
AMINE_CN_BOND = 1.6   # Å

PROTONATION_STATE_NAMES = frozenset({"HID", "HIE", "HIP", "ASH", "GLH", "LYN", "CYX", "CYM"})
HIS_NAMES = frozenset({"HIS", "HID", "HIE", "HIP"})
_LIGAND_SCRIPT = Path(__file__).with_name("ligand_rdkit.py")


# ------------------------------------------------------------------- container
def dock(workdir: Path | str, cmd: Sequence[str], env: Optional[str] = None,
         timeout: int = 900) -> Tuple[int, str, float]:
    """Run ``cmd`` in the prep container with ``workdir`` mounted at /work.

    Returns (exit code, merged stdout+stderr, seconds). ``cmd`` is an argv list;
    no shell is involved, so nothing in it is interpreted.
    """
    workdir = Path(workdir).resolve()
    args = ["docker", "run", "--rm", "-v", f"{workdir}:/work", PREP_IMAGE]
    if env:
        args += ["micromamba", "run", "-n", env]
    args += [str(c) for c in cmd]
    start = time.monotonic()
    try:
        proc = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        out = (exc.stdout or b"")
        out = out.decode(errors="replace") if isinstance(out, bytes) else str(out)
        return 124, out + f"\n[timeout after {timeout}s]", round(time.monotonic() - start, 2)
    return proc.returncode, proc.stdout or "", round(time.monotonic() - start, 2)


def prep_available(image: str = PREP_IMAGE) -> bool:
    if shutil.which("docker") is None:
        return False
    try:
        if subprocess.run(["docker", "info"], capture_output=True, timeout=20).returncode != 0:
            return False
        return subprocess.run(["docker", "image", "inspect", image], capture_output=True, timeout=20).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


# ------------------------------------------------------------------ PDB parsing
def read_pdb_atoms(path: Path | str, records: Tuple[str, ...] = ("ATOM", "HETATM")) -> List[Dict[str, Any]]:
    atoms = []
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            rec = line[:6].strip()
            if rec not in records:
                continue
            name = line[12:16].strip()
            element = line[76:78].strip().capitalize() if len(line) >= 78 else ""
            if not element:
                element = re.sub(r"[^A-Za-z]", "", name)[:1].upper()
            atoms.append({
                "record": rec, "serial": int(line[6:11]), "name": name, "altloc": line[16],
                "resname": line[17:20].strip(), "chain": line[21], "resnum": int(line[22:26]),
                "icode": line[26], "x": float(line[30:38]), "y": float(line[38:46]), "z": float(line[46:54]),
                "element": element, "line": line.rstrip("\n"),
            })
    return atoms


def _xyz(atoms: Iterable[Dict[str, Any]]) -> np.ndarray:
    return np.array([[a["x"], a["y"], a["z"]] for a in atoms], dtype=float).reshape(-1, 3)


def parse_remarks(path: Path | str) -> Dict[str, Dict[str, list]]:
    """REMARK 465 missing residues and REMARK 470 missing atoms, per chain."""
    out: Dict[str, Dict[str, list]] = defaultdict(lambda: {"missing_residues": [], "missing_atoms": []})
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            if line.startswith("REMARK 465"):
                m = re.match(r"REMARK 465\s+(?:\d+\s+)?([A-Z]{1,3})\s+([A-Za-z0-9])\s+(-?\d+)([A-Z]?)\s*$", line.rstrip())
                if m and m.group(1) not in ("M", "RES"):
                    out[m.group(2)]["missing_residues"].append((m.group(1), int(m.group(3))))
            elif line.startswith("REMARK 470"):
                m = re.match(r"REMARK 470\s+(?:\d+\s+)?([A-Z]{1,3})\s+([A-Za-z0-9])\s*(-?\d+)([A-Z]?)\s+(.+?)\s*$", line.rstrip())
                if m and m.group(1) not in ("M", "RES"):
                    out[m.group(2)]["missing_atoms"].append((m.group(1), int(m.group(3)), m.group(5).split()))
    return dict(out)


# ---------------------------------------------------------------- choose_chain
def choose_chain(pdb: Path | str, ligand: str) -> Dict[str, Any]:
    """Pick the chain whose ligand pocket is most complete.

    Score per chain = (gaps adjacent to the pocket, residues with missing atoms
    in the pocket, missing residues in the chain, chain id); smallest wins.
    """
    atoms = read_pdb_atoms(pdb)
    remarks = parse_remarks(pdb)
    lig_chains = sorted({a["chain"] for a in atoms if a["record"] == "HETATM" and a["resname"] == ligand})
    if not lig_chains:
        raise ValueError(f"no HETATM residue named {ligand!r} in {pdb}")
    rows = []
    for ch in lig_chains:
        lig = [a for a in atoms if a["record"] == "HETATM" and a["resname"] == ligand and a["chain"] == ch]
        cas = [a for a in atoms if a["record"] == "ATOM" and a["chain"] == ch and a["name"] == "CA"
               and a["altloc"] in (" ", "A")]
        lig_xyz, ca_xyz = _xyz(lig), _xyz(cas)
        d = np.linalg.norm(ca_xyz[:, None, :] - lig_xyz[None, :, :], axis=2).min(axis=1)
        pocket = sorted({cas[i]["resnum"] for i in np.flatnonzero(d <= POCKET_RADIUS)})
        pocket_set = set(pocket)
        rem = remarks.get(ch, {"missing_residues": [], "missing_atoms": []})
        missing = sorted(n for _, n in rem["missing_residues"])
        adjacent = sorted(n for n in missing if (n - 1 in pocket_set) or (n + 1 in pocket_set))
        gaps = 0
        prev = None
        for n in adjacent:
            if prev is None or n != prev + 1:
                gaps += 1
            prev = n
        missing_atom_res = sorted({n for _, n, _ in rem["missing_atoms"] if n in pocket_set})
        rows.append({
            "chain": ch, "ligand_atoms": len(lig), "pocket_residues": len(pocket),
            "gaps_adjacent_to_pocket": gaps, "missing_residues_adjacent": adjacent,
            "missing_atom_residues_in_pocket": missing_atom_res,
            "missing_residues": len(missing),
            "score": (gaps, len(missing_atom_res), len(missing), ch),
        })
    best = min(rows, key=lambda r: r["score"])
    return {"chain": best["chain"], "table": rows, "pocket_radius": POCKET_RADIUS}


# --------------------------------------------------------------------- extract
def extract(pdb: Path | str, chain: str, ligand: str, work: Path | str) -> Dict[str, Any]:
    """Write protein.pdb (ATOM lines of the chain, first altloc) and ligand.pdb (HETATM of the ligand)."""
    work = Path(work)
    work.mkdir(parents=True, exist_ok=True)
    protein, lig = [], []
    for a in read_pdb_atoms(pdb):
        if a["chain"] != chain or a["altloc"] not in (" ", "A"):
            continue
        line = a["line"][:16] + " " + a["line"][17:]  # blank the altloc column
        if a["record"] == "ATOM":
            protein.append(line)
        elif a["resname"] == ligand:
            lig.append(line)
    if not lig:
        raise ValueError(f"no {ligand} in chain {chain}")
    (work / "protein.pdb").write_text("\n".join(protein) + "\nTER\nEND\n", encoding="utf-8")
    (work / "ligand.pdb").write_text("\n".join(lig) + "\nEND\n", encoding="utf-8")
    return {"chain": chain, "ligand": ligand, "protein_atoms": len(protein), "ligand_atoms": len(lig),
            "protein_pdb": str(work / "protein.pdb"), "ligand_pdb": str(work / "ligand.pdb")}


# ------------------------------------------------------------------- protonate
def parse_propka_summary(text: str) -> Dict[Tuple[str, int], float]:
    pkas: Dict[Tuple[str, int], float] = {}
    in_summary = False
    for line in text.splitlines():
        if "SUMMARY OF THIS PREDICTION" in line:
            in_summary = True
            continue
        if not in_summary:
            continue
        toks = line.split()
        if not toks:
            if pkas:
                break
            continue
        if toks[0] == "Group":
            continue
        if len(toks) >= 4 and re.fullmatch(r"[A-Z0-9+-]{1,3}", toks[0]) and re.fullmatch(r"-?\d+", toks[1]):
            try:
                pkas[(toks[0], int(toks[1]))] = float(toks[3])
            except ValueError:
                continue
        elif toks[0].startswith("-"):
            break
    return pkas


def residue_states(pdb_h: Path | str) -> Dict[int, str]:
    states: Dict[int, str] = {}
    for a in read_pdb_atoms(pdb_h, records=("ATOM",)):
        if a["resname"] in PROTONATION_STATE_NAMES:
            states[a["resnum"]] = a["resname"]
    return states


def protonate(work: Path | str, ph: float) -> Dict[str, Any]:
    """pdb2pqr + PROPKA at the given pH, inside the container's prep env."""
    work = Path(work)
    ph = float(ph)
    cmd = ["pdb2pqr", "--ff=AMBER", "--ffout=AMBER", "--titration-state-method=propka", f"--with-ph={ph}",
           "--pdb-output", "protein_h.pdb", "protein.pdb", "protein.pqr"]
    code, out, secs = dock(work, cmd, env="prep")
    (work / "pdb2pqr.log").write_text(out, encoding="utf-8")
    text = out
    for extra in work.glob("*.propka"):
        text += "\n" + extra.read_text(encoding="utf-8", errors="replace")
    pkas = parse_propka_summary(text)
    states = residue_states(work / "protein_h.pdb") if (work / "protein_h.pdb").exists() else {}
    gaps = [l.strip() for l in out.splitlines() if "gap" in l.lower() and ("WARN" in l.upper() or "missing" in l.lower())]
    if code != 0 or not (work / "protein_h.pdb").exists():
        raise RuntimeError(f"pdb2pqr failed (exit {code}); see {work / 'pdb2pqr.log'}")
    return {"ph": ph, "pkas": {f"{r}{n}": v for (r, n), v in pkas.items()}, "pka_table": pkas,
            "states": states, "gap_warnings": gaps, "seconds": secs, "log": str(work / "pdb2pqr.log")}


# ------------------------------------------------------ ligand_protonation_site
def ligand_protonation_site(work: Path | str) -> Optional[Dict[str, Any]]:
    """Tertiary amine (N with exactly three C neighbours) closest to a backbone O within HBOND."""
    work = Path(work)
    lig = read_pdb_atoms(work / "ligand.pdb", records=("HETATM", "ATOM"))
    prot = read_pdb_atoms(work / "protein.pdb", records=("ATOM",))
    lig_xyz = _xyz(lig)
    bb_o = [a for a in prot if a["name"] == "O"]
    bb_xyz = _xyz(bb_o)
    checked, candidates = [], []
    for i, a in enumerate(lig):
        if a["element"] != "N":
            continue
        d = np.linalg.norm(lig_xyz - lig_xyz[i], axis=1)
        carbons = [lig[j]["name"] for j in np.flatnonzero((d > 0) & (d <= AMINE_CN_BOND)) if lig[j]["element"] == "C"]
        heavy = int(((d > 0) & (d <= AMINE_CN_BOND)).sum())
        entry = {"atom": a["name"], "carbon_neighbours": carbons, "heavy_neighbours": heavy, "tertiary_amine": False,
                 "contacts": []}
        if len(carbons) == 3 and heavy == 3:
            entry["tertiary_amine"] = True
            if len(bb_o):
                dd = np.linalg.norm(bb_xyz - lig_xyz[i], axis=1)
                for j in np.argsort(dd):
                    if dd[j] > HBOND:
                        break
                    o = bb_o[j]
                    entry["contacts"].append({"partner": f"{o['resname']}{o['resnum']}@O", "distance": round(float(dd[j]), 3)})
            if entry["contacts"]:
                candidates.append(entry)
        checked.append(entry)
    if not candidates:
        return None
    best = min(candidates, key=lambda e: e["contacts"][0]["distance"])
    c0 = best["contacts"][0]
    others = [e["atom"] for e in checked if e["atom"] != best["atom"]]
    evidence = (f"{best['atom']} is a tertiary amine ({', '.join(best['carbon_neighbours'])}) whose closest backbone "
                f"carbonyl O is {c0['partner']} at {c0['distance']:.2f} Å (cutoff {HBOND} Å)"
                + (f"; other N atoms checked: {', '.join(others)}" if others else "") + ".")
    return {"atom": best["atom"], "contacts": best["contacts"], "checked": checked, "evidence": evidence}


# ------------------------------------------------------------- review_uncertain
def review_uncertain(work: Path | str, prot: Dict[str, Any], ph: float,
                     ligand_cation_atom: Optional[str]) -> Dict[str, Any]:
    """His within PKA_WINDOW of pH whose ring N faces the ligand cation -> neutral tautomer, N toward cation unprotonated."""
    work = Path(work)
    ph = float(ph)
    overrides: List[Dict[str, Any]] = []
    uncertain = [(res, num, pka) for (res, num), pka in prot.get("pka_table", {}).items()
                 if res == "HIS" and abs(pka - ph) < PKA_WINDOW]
    note = ("Overridden His states are chosen from geometry; the charged (HIP) state should be run as a sensitivity "
            "check because its PROPKA pKa lies within 1 unit of the pH.")
    if ligand_cation_atom is None or not uncertain:
        return {"overrides": [], "uncertain_his": [f"HIS{n} pKa {p:.2f}" for _, n, p in uncertain],
                "cation_atom": ligand_cation_atom, "note": note}
    lig = read_pdb_atoms(work / "ligand.pdb", records=("HETATM", "ATOM"))
    cation = next((a for a in lig if a["name"] == ligand_cation_atom), None)
    if cation is None:
        raise ValueError(f"cation atom {ligand_cation_atom} not in ligand.pdb")
    cxyz = np.array([cation["x"], cation["y"], cation["z"]])
    src = work / "protein_h.pdb" if (work / "protein_h.pdb").exists() else work / "protein.pdb"
    prot_atoms = read_pdb_atoms(src, records=("ATOM",))
    states = prot.get("states", {})
    for _, num, pka in uncertain:
        ring = {a["name"]: np.array([a["x"], a["y"], a["z"]]) for a in prot_atoms
                if a["resnum"] == num and a["resname"] in HIS_NAMES and a["name"] in ("ND1", "NE2")}
        if len(ring) != 2:
            continue
        d_nd1 = float(np.linalg.norm(ring["ND1"] - cxyz))
        d_ne2 = float(np.linalg.norm(ring["NE2"] - cxyz))
        if min(d_nd1, d_ne2) > CATION_RANGE:
            continue
        new = "HIE" if d_nd1 < d_ne2 else "HID"
        old = states.get(num, "HIS")
        overrides.append({
            "resnum": num, "from": old, "to": new, "pka": pka, "ph": ph,
            "d_ND1_cation": round(d_nd1, 2), "d_NE2_cation": round(d_ne2, 2),
            "evidence": (f"HIS{num}: PROPKA pKa {pka:.2f} within {PKA_WINDOW} of pH {ph}; ND1 {d_nd1:.2f} Å and "
                         f"NE2 {d_ne2:.2f} Å from ligand cation {ligand_cation_atom} (range {CATION_RANGE} Å); "
                         f"{'ND1' if new == 'HIE' else 'NE2'} faces the cation and is left unprotonated -> {new}"),
        })
    return {"overrides": overrides, "uncertain_his": [f"HIS{n} pKa {p:.2f}" for _, n, p in uncertain],
            "cation_atom": ligand_cation_atom, "note": note}


# ------------------------------------------------------------ mol2 finalisation
_GAFF_ELEMENT = {"cl": "Cl", "br": "Br"}


def _mol2_element(atom_type: str, atom_name: str) -> str:
    t = atom_type.lower()
    if t[:2] in _GAFF_ELEMENT:
        return _GAFF_ELEMENT[t[:2]]
    if t[:1] in "cnohspfi":
        return t[:1].upper()
    return re.sub(r"[^A-Za-z]", "", atom_name)[:1].upper()


def parse_mol2(text: str) -> Dict[str, Any]:
    lines = text.splitlines()
    out: Dict[str, Any] = {"header": [], "atoms": [], "rest": []}
    section = None
    for line in lines:
        if line.startswith("@<TRIPOS>"):
            section = line.strip()
            if section == "@<TRIPOS>ATOM":
                out["header"].append(line)
            elif section == "@<TRIPOS>MOLECULE" or not out["atoms"]:
                out["header"].append(line)
            else:
                out["rest"].append(line)
            continue
        if section == "@<TRIPOS>ATOM":
            toks = line.split()
            if len(toks) >= 9:
                out["atoms"].append({"id": int(toks[0]), "name": toks[1], "x": float(toks[2]), "y": float(toks[3]),
                                     "z": float(toks[4]), "type": toks[5], "subst_id": toks[6], "subst": toks[7],
                                     "charge": float(toks[8]), "element": _mol2_element(toks[5], toks[1])})
            elif line.strip():
                out["header"].append(line)
        elif section in (None, "@<TRIPOS>MOLECULE") or (section and not out["atoms"]):
            out["header"].append(line)
        else:
            out["rest"].append(line)
    return out


def parse_sdf_atoms(text: str) -> List[Dict[str, Any]]:
    lines = text.splitlines()
    counts = lines[3]
    n_atoms = int(counts[:3])
    atoms = []
    for line in lines[4:4 + n_atoms]:
        toks = line.split()
        atoms.append({"x": float(toks[0]), "y": float(toks[1]), "z": float(toks[2]), "element": toks[3].capitalize()})
    return atoms


def finalise_mol2(mol2_text: str, sdf_text: str, net_charge: int) -> Tuple[str, Dict[str, Any]]:
    """Cached charges/types + this run's coordinates; refuse order mismatches and residuals >= 0.01 e."""
    mol2 = parse_mol2(mol2_text)
    sdf = parse_sdf_atoms(sdf_text)
    if len(mol2["atoms"]) != len(sdf):
        raise ValueError(f"atom count differs: mol2 {len(mol2['atoms'])} vs sdf {len(sdf)}")
    for i, (a, b) in enumerate(zip(mol2["atoms"], sdf)):
        if a["element"] != b["element"]:
            raise ValueError(f"element order differs at atom {i + 1}: mol2 {a['element']} ({a['type']}) vs sdf {b['element']}")
    total = sum(a["charge"] for a in mol2["atoms"])
    residual = net_charge - total
    if abs(residual) >= 0.01:
        raise ValueError(f"charge residual {residual:+.4f} e vs net charge {net_charge:+d} exceeds 0.01 e")
    spread = residual / len(mol2["atoms"])
    out_lines = list(mol2["header"])
    for a, b in zip(mol2["atoms"], sdf):
        out_lines.append(f"{a['id']:7d} {a['name']:<8s} {b['x']:10.4f} {b['y']:10.4f} {b['z']:10.4f} "
                         f"{a['type']:<8s} {a['subst_id']:>3s} {a['subst']:<8s} {a['charge'] + spread:10.6f}")
    out_lines.extend(mol2["rest"])
    info = {"charge_sum": round(sum(a["charge"] + spread for a in mol2["atoms"]), 6),
            "charge_residual_spread": round(residual, 6), "ligand_atoms": len(mol2["atoms"])}
    return "\n".join(out_lines) + "\n", info


# ------------------------------------------------------------ ligand_parameters
def ligand_parameters(work: Path | str, smiles: str, protonate_atom: Optional[str],
                      cache: Path | str = CACHE) -> Dict[str, Any]:
    """RDKit hydrogens in the container, then GAFF2/AM1-BCC parameters (cached by SMILES+charge)."""
    import json

    work = Path(work)
    cache = Path(cache)
    t0 = time.monotonic()
    shutil.copy(_LIGAND_SCRIPT, work / "ligand_rdkit.py")
    code, out, _ = dock(work, ["python", "ligand_rdkit.py", "ligand.pdb", smiles, protonate_atom or "-", "ligand_h.sdf"],
                        env="prep")
    (work / "ligand_rdkit.log").write_text(out, encoding="utf-8")
    if code != 0:
        raise RuntimeError(f"ligand_rdkit.py failed (exit {code}): {out[-500:]}")
    info = json.loads([l for l in out.splitlines() if l.startswith("{")][-1])
    net_charge = int(info["net_charge"])

    key = hashlib.sha256(f"{smiles}|{net_charge}|gaff2|bcc".encode()).hexdigest()[:16]
    cdir = cache / key
    cached = (cdir / "ligand.mol2").exists() and (cdir / "ligand.frcmod").exists()
    if cached:
        shutil.copy(cdir / "ligand.mol2", work / "ligand_cached.mol2")
        shutil.copy(cdir / "ligand.frcmod", work / "ligand.frcmod")
        mol2_text = (work / "ligand_cached.mol2").read_text(encoding="utf-8")
    else:
        code, out, _ = dock(work, ["antechamber", "-i", "ligand_h.sdf", "-fi", "mdl", "-o", "ligand_raw.mol2", "-fo", "mol2",
                                   "-at", "gaff2", "-c", "bcc", "-nc", str(net_charge), "-rn", "LIG", "-s", "0", "-pf", "y"])
        (work / "antechamber.log").write_text(out, encoding="utf-8")
        if code != 0 or not (work / "ligand_raw.mol2").exists():
            raise RuntimeError(f"antechamber failed (exit {code}); see {work / 'antechamber.log'}")
        code, out, _ = dock(work, ["parmchk2", "-i", "ligand_raw.mol2", "-f", "mol2", "-o", "ligand.frcmod", "-s", "gaff2"])
        (work / "parmchk2.log").write_text(out, encoding="utf-8")
        if code != 0 or not (work / "ligand.frcmod").exists():
            raise RuntimeError(f"parmchk2 failed (exit {code}); see {work / 'parmchk2.log'}")
        cdir.mkdir(parents=True, exist_ok=True)
        shutil.copy(work / "ligand_raw.mol2", cdir / "ligand.mol2")
        shutil.copy(work / "ligand.frcmod", cdir / "ligand.frcmod")
        (cdir / "key.txt").write_text(f"{smiles}|{net_charge}|gaff2|bcc\n", encoding="utf-8")
        mol2_text = (work / "ligand_raw.mol2").read_text(encoding="utf-8")

    final, finfo = finalise_mol2(mol2_text, (work / "ligand_h.sdf").read_text(encoding="utf-8"), net_charge)
    (work / "ligand.mol2").write_text(final, encoding="utf-8")
    return {**info, **finfo, "cached": cached, "cache_key": key, "seconds": round(time.monotonic() - t0, 2),
            "mol2": str(work / "ligand.mol2"), "frcmod": str(work / "ligand.frcmod")}


# --------------------------------------------------------------- build_complex
def parse_renum(path: Path | str) -> Dict[int, int]:
    """pdb4amber *_renum.txt: '<old resname> [chain] <old num> <new resname> <new num>' -> {old: new}."""
    renum: Dict[int, int] = {}
    for line in Path(path).read_text(encoding="utf-8", errors="replace").splitlines():
        toks = line.split()
        nums = [t for t in toks if re.fullmatch(r"-?\d+", t)]
        if len(nums) >= 2:
            renum[int(nums[0])] = int(nums[-1])
    return renum


TLEAP_TEMPLATE = """source leaprc.protein.ff14SB
source leaprc.gaff2
set default PBRadii mbondi2
loadamberparams ligand.frcmod
LIG = loadmol2 ligand.mol2
PROT = loadpdb protein_final.pdb
COMPLEX = combine {PROT LIG}
charge COMPLEX
saveamberparm COMPLEX complex.parm7 complex.rst7
quit
"""


def build_complex(work: Path | str, prot: Dict[str, Any], overrides: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    work = Path(work)
    code, out, s1 = dock(work, ["pdb4amber", "-i", "protein_h.pdb", "-o", "protein_amber.pdb", "--nohyd"])
    (work / "pdb4amber.log").write_text(out, encoding="utf-8")
    if code != 0 or not (work / "protein_amber.pdb").exists():
        raise RuntimeError(f"pdb4amber failed (exit {code}); see {work / 'pdb4amber.log'}")
    renum_file = next(iter(work.glob("protein_amber_renum.txt")), None)
    renum = parse_renum(renum_file) if renum_file else {}

    by_new = {}
    for o in overrides:
        new_num = renum.get(int(o["resnum"]), int(o["resnum"]))
        by_new[new_num] = o["to"]
    applied = []
    lines = []
    for line in (work / "protein_amber.pdb").read_text(encoding="utf-8").splitlines():
        if line.startswith(("ATOM", "HETATM")) and line[17:20].strip() in HIS_NAMES:
            num = int(line[22:26])
            if num in by_new:
                if line[17:20] != by_new[num]:
                    applied.append((num, line[17:20], by_new[num]))
                line = line[:17] + f"{by_new[num]:<3s}" + line[20:]
        lines.append(line)
    (work / "protein_final.pdb").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (work / "tleap.in").write_text(TLEAP_TEMPLATE, encoding="utf-8")
    code, out, s2 = dock(work, ["tleap", "-f", "tleap.in"])
    (work / "tleap.log").write_text(out, encoding="utf-8")
    m = re.search(r"Errors\s*=\s*(\d+);\s*Warnings\s*=\s*(\d+)", out)
    errors, warnings = (int(m.group(1)), int(m.group(2))) if m else (None, None)
    q = re.search(r"Total unperturbed charge:\s*([-+]?\d+\.\d+)", out)
    charge = float(q.group(1)) if q else None
    if (errors or 0) > 0 or code != 0 or not (work / "complex.parm7").exists():
        raise RuntimeError(f"tleap failed (exit {code}, errors {errors}); see {work / 'tleap.log'}")
    return {"parm7": str(work / "complex.parm7"), "rst7": str(work / "complex.rst7"), "total_charge": charge,
            "tleap_errors": errors, "tleap_warnings": warnings, "renum": renum,
            "overrides_applied": sorted({(n, f, t) for n, f, t in applied}), "seconds": round(s1 + s2, 2)}


# -------------------------------------------------------------------- minimise
def minimise(work: Path | str, steps: int = 500) -> Dict[str, Any]:
    work = Path(work)
    steps = int(steps)
    mdin = (f"ActiveSite restrained GB minimisation\n &cntrl\n  imin=1, maxcyc={steps}, ncyc={min(200, steps // 2)},\n"
            f"  ntb=0, igb=5, cut=999.0,\n  ntr=1, restraintmask='!@H=', restraint_wt=10.0,\n  ntpr=10,\n /\n")
    (work / "min.in").write_text(mdin, encoding="utf-8")
    code, out, secs = dock(work, ["sander", "-O", "-i", "min.in", "-o", "min.out", "-p", "complex.parm7",
                                  "-c", "complex.rst7", "-ref", "complex.rst7", "-r", "min.rst7"])
    text = (work / "min.out").read_text(encoding="utf-8", errors="replace") if (work / "min.out").exists() else out
    rows = []
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if "NSTEP" in line and "ENERGY" in line and "GMAX" in line and i + 1 < len(lines):
            toks = lines[i + 1].split()
            if len(toks) >= 4:
                try:
                    rows.append({"nstep": int(toks[0]), "energy": float(toks[1]), "rms": float(toks[2]), "gmax": float(toks[3])})
                except ValueError:
                    pass
    if code != 0 or not (work / "min.rst7").exists() or not rows:
        raise RuntimeError(f"sander minimisation failed (exit {code}); see {work / 'min.out'}")
    return {"first": rows[0], "last": rows[-1], "steps": steps, "seconds": secs, "rst7": str(work / "min.rst7")}


# ------------------------------------------------------------------- contacts
def _polar_pairs(lig: List[Dict[str, Any]], prot: List[Dict[str, Any]], has_h) -> List[Dict[str, Any]]:
    cutoff = HBOND + 0.2
    out = []
    lp = [a for a in lig if a["element"] in ("N", "O")]
    pp = [a for a in prot if a["element"] in ("N", "O")]
    if not lp or not pp:
        return out
    d = np.linalg.norm(_xyz(lp)[:, None, :] - _xyz(pp)[None, :, :], axis=2)
    for i, j in zip(*np.nonzero(d <= cutoff)):
        if has_h(lp[i]) or has_h(pp[j]):
            out.append({"ligand_atom": lp[i]["name"], "partner": f"{pp[j]['resname']}{pp[j]['resnum']}@{pp[j]['name']}",
                        "distance": round(float(d[i, j]), 3)})
    return sorted(out, key=lambda c: c["distance"])


def polar_contacts(work: Path | str) -> Dict[str, Any]:
    """Ligand N/O to protein N/O within HBOND+0.2 on the raw crystal files (no H present: H criterion not applicable)."""
    work = Path(work)
    lig = read_pdb_atoms(work / "ligand.pdb", records=("HETATM", "ATOM"))
    prot = read_pdb_atoms(work / "protein.pdb", records=("ATOM",))
    contacts = _polar_pairs(lig, prot, lambda a: True)
    return {"contacts": contacts, "cutoff": HBOND + 0.2, "numbering": "crystal",
            "note": "crystal files carry no hydrogens, so the donor-H criterion is not applied here"}


def built_pose(work: Path | str, coords: Path | str, renum: Dict[int, int]) -> Dict[str, Any]:
    """Ligand pose in the built complex vs the crystal ligand, with contacts in crystal numbering."""
    import parmed as pmd

    work = Path(work)
    s = pmd.load_file(str(work / "complex.parm7"), str(coords))
    inv = {v: k for k, v in renum.items()}
    lig_res = next((r for r in s.residues if r.name == "LIG"), None)
    if lig_res is None:
        raise ValueError("no LIG residue in complex.parm7")
    xyz = np.asarray(s.coordinates, dtype=float)
    lig_heavy = [a for a in lig_res.atoms if a.atomic_number > 1]
    crystal = [a for a in read_pdb_atoms(work / "ligand.pdb", records=("HETATM", "ATOM")) if a["element"] != "H"]
    if len(crystal) != len(lig_heavy):
        raise ValueError(f"ligand heavy-atom count differs: crystal {len(crystal)} vs built {len(lig_heavy)}")
    built_xyz = xyz[[a.idx for a in lig_heavy]]
    cryst_xyz = _xyz(crystal)
    shift = float(np.linalg.norm(built_xyz.mean(axis=0) - cryst_xyz.mean(axis=0)))
    rmsd = float(np.sqrt(((built_xyz - cryst_xyz) ** 2).sum(axis=1).mean()))

    prot_atoms = [a for a in s.atoms if a.residue.idx != lig_res.idx]
    prot_heavy = [a for a in prot_atoms if a.atomic_number > 1]
    d = np.linalg.norm(xyz[[a.idx for a in prot_heavy]][:, None, :] - built_xyz[None, :, :], axis=2)
    pi, li = np.unravel_index(int(d.argmin()), d.shape)
    closest = prot_heavy[pi]

    def rec(a, element):
        return {"name": a.name, "resname": a.residue.name, "resnum": inv.get(a.residue.number, a.residue.number),
                "element": element, "x": xyz[a.idx, 0], "y": xyz[a.idx, 1], "z": xyz[a.idx, 2],
                "has_h": any(p.atomic_number == 1 for p in a.bond_partners)}

    sym = {7: "N", 8: "O", 6: "C", 1: "H", 16: "S"}
    lig_rec = [rec(a, sym.get(a.atomic_number, "X")) for a in lig_res.atoms]
    prot_rec = [rec(a, sym.get(a.atomic_number, "X")) for a in prot_atoms if a.atomic_number in (7, 8)]
    contacts = _polar_pairs(lig_rec, prot_rec, lambda a: a["has_h"])
    return {"centroid_shift": round(shift, 3), "rmsd": round(rmsd, 3), "ligand_heavy_atoms": len(lig_heavy),
            "closest_protein_heavy_atom": {"atom": f"{closest.residue.name}{inv.get(closest.residue.number, closest.residue.number)}@{closest.name}",
                                           "ligand_atom": lig_heavy[li].name, "distance": round(float(d[pi, li]), 3)},
            "contacts": contacts, "cutoff": HBOND + 0.2, "numbering": "crystal", "coords": str(coords)}


# ------------------------------------------------------------------- pipeline
def prepare_complex(pdb: Path | str, ligand: str, smiles: str, ph: float, work: Path | str,
                    steps: int = 500, cache: Path | str = CACHE) -> Dict[str, Any]:
    """Full preparation; every stage's evidence dict is kept under its name."""
    work = Path(work)
    work.mkdir(parents=True, exist_ok=True)
    chain = choose_chain(pdb, ligand)
    ext = extract(pdb, chain["chain"], ligand, work)
    crystal_contacts = polar_contacts(work)
    prot = protonate(work, ph)
    site = ligand_protonation_site(work)
    review = review_uncertain(work, prot, ph, site["atom"] if site else None)
    lig = ligand_parameters(work, smiles, site["atom"] if site else None, cache=cache)
    built = build_complex(work, prot, review["overrides"])
    mini = minimise(work, steps=steps)
    pose = built_pose(work, mini["rst7"], built["renum"])
    return {"chain": chain, "extract": ext, "crystal_contacts": crystal_contacts, "protonation": prot,
            "ligand_site": site, "his_review": review, "ligand_parameters": lig, "complex": built,
            "minimisation": mini, "pose": pose, "parm7": built["parm7"], "rst7": mini["rst7"]}
