"""ActiveSite — one sander QM/MM single point inside the engine container.

The only place in the code base that invokes a chemistry binary. It runs
``sander`` in ``activesite-engine:at26`` through ``docker run`` (AGENTS.md
rule 3: nothing chemical runs on the host), and parses the mdout with a pure
function so the parser can be tested on text fixtures without Docker.

Nothing here invents a number: a missing ESCF means ``ok = False`` and
``qm_escf_kcal = None``.
"""
from __future__ import annotations

import math
import re
import secrets
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

ENGINE_IMAGE = "activesite-engine:at26"

# Allow-lists: these strings are interpolated into the mdin and the docker command line.
ALLOWED_THEORIES = frozenset({"PM6", "PM3", "AM1", "RM1", "MNDO", "PM6-D", "PM6-DH+", "DFTB", "DFTB3", "EXTERN"})
_MASK_RE = re.compile(r"^[A-Za-z0-9:@&|!()<>,.\-+*'= ]+$")
SOLVENTS = ("pme", "gb")

_PME_TEMPLATE = """ActiveSite {theory} single point, qmcharge={charge:+d}, PME
 &cntrl
    imin=1, maxcyc=1, ncyc=1, ntmin=2,
    ntb=1, cut=10.0, ntpr=1, ntx=1,
    ifqnt=1,
 /
 &qmmm
    qmmask='{mask}',
    qm_theory='{theory}',
    qmcharge={charge},
    spin=1,
    qmcut=10.0,
    qm_ewald=1, qm_pme=1,
    qmmm_switch=1,
    writepdb=1,
    verbosity=0,
 /
"""

_GB_TEMPLATE = """ActiveSite {theory} single point, qmcharge={charge:+d}, GB
 &cntrl
    imin=1, maxcyc=1, ncyc=1, ntmin=2,
    ntpr=1, ntb=0, igb=5, cut=999.0,
    ifqnt=1,
 /
 &qmmm
    qmmask='{mask}',
    qm_theory='{theory}',
    qmcharge={charge},
    spin=1,
    qmgb=2,
    qmcut=999.0,
    writepdb=1,
    verbosity=0,
 /
"""

_MD_GB_TEMPLATE = """ActiveSite {theory} QM/MM MD, qmcharge={charge:+d}, GB
 &cntrl
    imin=0, nstlim={steps}, dt={dt:.3f},
    ntx=1, irest=0,
    ntt=3, gamma_ln=2.0, tempi=300.0, temp0=300.0,
    ntb=0, igb=5, cut=999.0,
    ntpr=50, ntwx=50,
    ifqnt=1,
 /
 &qmmm
    qmmask='{mask}',
    qm_theory='{theory}',
    qmcharge={charge},
    spin=1,
    qmgb=2,
    qmcut=999.0,
 /
"""


def validate_inputs(mask: str, charge: int, theory: str, solvent: str) -> None:
    if not isinstance(charge, int) or isinstance(charge, bool):
        raise ValueError(f"charge must be an int, got {charge!r}")
    if theory not in ALLOWED_THEORIES:
        raise ValueError(f"qm_theory {theory!r} not in allow-list {sorted(ALLOWED_THEORIES)}")
    if not mask or not _MASK_RE.match(mask) or "'" in mask:
        raise ValueError(f"qmmask {mask!r} contains characters outside the Amber mask grammar")
    if solvent not in SOLVENTS:
        raise ValueError(f"solvent must be one of {SOLVENTS}, got {solvent!r}")


def mdin_text(mask: str, charge: int, theory: str = "PM6", solvent: str = "pme") -> str:
    """Render the single-point mdin. The title line names the theory and charge."""
    validate_inputs(mask, charge, theory, solvent)
    template = _PME_TEMPLATE if solvent == "pme" else _GB_TEMPLATE
    return template.format(mask=mask, charge=charge, theory=theory)


def mdin_md_text(
    mask: str,
    charge: int,
    theory: str = "PM6",
    steps: int = 1000,
    dt: float = 0.001,
) -> str:
    """Render the QM/MM MD mdin template."""
    validate_inputs(mask, charge, theory, "gb")
    if not isinstance(steps, int) or steps <= 0:
        raise ValueError(f"steps must be a positive int, got {steps!r}")
    if not isinstance(dt, (int, float)) or dt <= 0:
        raise ValueError(f"dt must be a positive float, got {dt!r}")
    return _MD_GB_TEMPLATE.format(mask=mask, charge=charge, theory=theory, steps=steps, dt=dt)


# --------------------------------------------------------------------- parser
_ERROR_WORDS = ("odd", "incorrect", "Error", "error", "Unable")
_FLOAT = r"([-+]?(?:\d+\.?\d*|\.\d+)(?:[EeDd][-+]?\d+)?|NaN|nan|[-+]?Infinity|[-+]?Inf|\*+)"


def _to_float(token: str) -> Optional[float]:
    """Fortran-style float; '*****' overflow and NaN/Inf come back as non-finite, not as a number."""
    if token.startswith("*"):
        return math.nan
    try:
        return float(token.replace("D", "E").replace("d", "e"))
    except ValueError:
        return None


def parse_sander_output(text: str, theory: str = "PM6") -> Dict[str, Any]:
    """Parse a sander QM/MM mdout. Pure function; never substitutes defaults."""
    result: Dict[str, Any] = {
        "ok": False,
        "qm_escf_kcal": None,
        "total_energy_kcal": None,
        "qm_resp_charge_sum": None,
        "link_atoms": None,
        "odd_electrons": None,
        "errors": [],
    }
    lines = text.splitlines()

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("QMMM:") and any(w in stripped for w in _ERROR_WORDS):
            result["errors"].append(stripped)
        m = re.search(r"QM atom RESP charge sum \(inc MM link\)\s*=\s*" + _FLOAT, line)
        if m:
            result["qm_resp_charge_sum"] = _to_float(m.group(1))
        m = re.search(r"\bnlink\s*=\s*(\d+)", line)
        if m:
            result["link_atoms"] = int(m.group(1))
        m = re.search(r"odd number of electrons\s*\(\s*(\d+)\s*\)", line)
        if m:
            result["odd_electrons"] = int(m.group(1))

    # Block after FINAL RESULTS
    final_idx = next((i for i, line in enumerate(lines) if "FINAL RESULTS" in line), None)
    if final_idx is not None:
        block = lines[final_idx + 1:]
        escf_re = re.compile(re.escape(theory) + r"ESCF\s*=\s*" + _FLOAT, re.IGNORECASE)
        for i, line in enumerate(block):
            m = escf_re.search(line)
            if m and result["qm_escf_kcal"] is None:
                result["qm_escf_kcal"] = _to_float(m.group(1))
            if "NSTEP" in line and "ENERGY" in line and i + 1 < len(block):
                cols = block[i + 1].split()
                if len(cols) >= 2 and result["total_energy_kcal"] is None:
                    result["total_energy_kcal"] = _to_float(cols[1])

    escf = result["qm_escf_kcal"]
    if escf is not None:
        if math.isfinite(escf):
            result["ok"] = True
        else:
            result["qm_escf_kcal"] = None
            result["errors"].append("non-finite QM energy")
    if result["total_energy_kcal"] is not None and not math.isfinite(result["total_energy_kcal"]):
        result["total_energy_kcal"] = None
    return result


def parse_sander_md_output(text: str, theory: str = "PM6") -> Dict[str, Any]:
    """Parse a sander QM/MM molecular dynamics mdout. Pure function; never substitutes defaults."""
    result: Dict[str, Any] = {
        "ok": False,
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
        "errors": [],
    }
    if not text:
        return result

    lines = text.splitlines()

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("QMMM:") and any(w in stripped for w in _ERROR_WORDS):
            result["errors"].append(stripped)
        m = re.search(r"QM atom RESP charge sum \(inc MM link\)\s*=\s*" + _FLOAT, line)
        if m:
            result["qm_resp_charge_sum"] = _to_float(m.group(1))
        m = re.search(r"\bnlink\s*=\s*(\d+)", line)
        if m:
            result["link_atoms"] = int(m.group(1))
        m = re.search(r"odd number of electrons\s*\(\s*(\d+)\s*\)", line)
        if m:
            result["odd_electrons"] = int(m.group(1))

    # Split text into Progression, Averages, and RMS Fluctuations
    avg_marker = "A V E R A G E S   O V E R"
    rms_marker = "R M S  F L U C T U A T I O N S"

    prog_text = text
    avg_text = ""
    rms_text = ""

    if avg_marker in text:
        prog_text, _, rest = text.partition(avg_marker)
        if rms_marker in rest:
            avg_text, _, rms_text = rest.partition(rms_marker)
        else:
            avg_text = rest
    elif rms_marker in text:
        prog_text, _, rms_text = text.partition(rms_marker)

    # Helper regexes
    step_re = re.compile(r"NSTEP\s*=\s*(\d+)\s+TIME\(PS\)\s*=\s*" + _FLOAT + r"\s+TEMP\(K\)\s*=\s*" + _FLOAT)
    etot_re = re.compile(r"Etot\s*=\s*" + _FLOAT + r"\s+EKtot\s*=\s*" + _FLOAT + r"\s+EPtot\s*=\s*" + _FLOAT)
    escf_re = re.compile(re.escape(theory) + r"ESCF\s*=\s*" + _FLOAT, re.IGNORECASE)

    # 1. Parse progression steps
    prog_lines = prog_text.splitlines()
    i = 0
    while i < len(prog_lines):
        m_step = step_re.search(prog_lines[i])
        if m_step:
            nstep = int(m_step.group(1))
            time_ps = _to_float(m_step.group(2))
            temp_k = _to_float(m_step.group(3))
            etot, ektot, eptot, qm_escf = None, None, None, None

            # Look ahead up to 15 lines for Etot and ESCF before next NSTEP
            j = i + 1
            while j < min(len(prog_lines), i + 15):
                if step_re.search(prog_lines[j]):
                    break
                m_e = etot_re.search(prog_lines[j])
                if m_e and etot is None:
                    etot = _to_float(m_e.group(1))
                    ektot = _to_float(m_e.group(2))
                    eptot = _to_float(m_e.group(3))
                m_es = escf_re.search(prog_lines[j])
                if m_es and qm_escf is None:
                    qm_escf = _to_float(m_es.group(1))
                j += 1

            result["energy_progression"].append({
                "nstep": nstep,
                "time_ps": time_ps,
                "temp_k": temp_k,
                "etot": etot,
                "ektot": ektot,
                "eptot": eptot,
                "qm_escf": qm_escf,
            })
            i = j - 1
        i += 1

    # 2. Parse averages
    if avg_text:
        m_step = step_re.search(avg_text)
        m_e = etot_re.search(avg_text)
        m_es = escf_re.search(avg_text)
        result["averages"] = {
            "temp_k": _to_float(m_step.group(3)) if m_step else None,
            "etot": _to_float(m_e.group(1)) if m_e else None,
            "ektot": _to_float(m_e.group(2)) if m_e else None,
            "eptot": _to_float(m_e.group(3)) if m_e else None,
            "qm_escf": _to_float(m_es.group(1)) if m_es else None,
        }

    # 3. Parse RMS fluctuations
    if rms_text:
        m_step = step_re.search(rms_text)
        m_e = etot_re.search(rms_text)
        m_es = escf_re.search(rms_text)
        result["rms_fluctuations"] = {
            "temp_k": _to_float(m_step.group(3)) if m_step else None,
            "etot": _to_float(m_e.group(1)) if m_e else None,
            "ektot": _to_float(m_e.group(2)) if m_e else None,
            "eptot": _to_float(m_e.group(3)) if m_e else None,
            "qm_escf": _to_float(m_es.group(1)) if m_es else None,
        }

    # Final summary fields
    if result["energy_progression"]:
        last_entry = result["energy_progression"][-1]
        result["steps_completed"] = last_entry["nstep"]
        result["final_temperature_k"] = last_entry["temp_k"]
        result["qm_escf_kcal"] = last_entry["qm_escf"]
        result["total_energy_kcal"] = last_entry["etot"]
    elif result["averages"].get("temp_k") is not None:
        result["final_temperature_k"] = result["averages"]["temp_k"]
        result["qm_escf_kcal"] = result["averages"].get("qm_escf")
        result["total_energy_kcal"] = result["averages"].get("etot")
        m_step = step_re.search(avg_text)
        if m_step:
            result["steps_completed"] = int(m_step.group(1))

    if result["steps_completed"] > 0 and not result["errors"]:
        if result["final_temperature_k"] is not None and math.isfinite(result["final_temperature_k"]):
            result["ok"] = True
        else:
            result["ok"] = False
            result["errors"].append("non-finite MD temperature")
    else:
        result["ok"] = False

    return result


# --------------------------------------------------------------------- docker
def docker_available(image: str = ENGINE_IMAGE) -> bool:
    """True when the docker CLI works and the engine image is present locally."""
    if shutil.which("docker") is None:
        return False
    try:
        info = subprocess.run(["docker", "info"], capture_output=True, text=True, timeout=20)
        if info.returncode != 0:
            return False
        img = subprocess.run(["docker", "image", "inspect", image], capture_output=True, text=True, timeout=20)
        return img.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def build_command(name: str, refdir: Path, workdir: Path, parm7_name: str, coords_name: str,
                  image: str = ENGINE_IMAGE) -> List[str]:
    return [
        "docker", "run", "--rm", "--name", name,
        "-v", f"{refdir}:/ref:ro",
        "-v", f"{workdir}:/work",
        image,
        "sander", "-O", "-i", "sp.mdin", "-o", "sp.out", "-r", "sp.rst7",
        "-p", f"/ref/{parm7_name}", "-c", f"/ref/{coords_name}",
    ]


def run_single_point(
    parm7: Path | str,
    coords: Path | str,
    mask: str,
    charge: int,
    workdir: Path | str,
    theory: str = "PM6",
    timeout_s: int = 300,
    solvent: str = "pme",
    image: str = ENGINE_IMAGE,
) -> Dict[str, Any]:
    """Run one sander single point in the engine container and parse sp.out."""
    parm7 = Path(parm7).resolve()
    coords = Path(coords).resolve()
    workdir = Path(workdir).resolve()
    if parm7.parent != coords.parent:
        raise ValueError("parm7 and coords must live in the same directory (mounted read-only at /ref)")
    if not parm7.exists() or not coords.exists():
        raise FileNotFoundError(f"missing topology or coordinates: {parm7}, {coords}")
    validate_inputs(mask, charge, theory, solvent)

    workdir.mkdir(parents=True, exist_ok=True)
    (workdir / "sp.mdin").write_text(mdin_text(mask, charge, theory, solvent), encoding="utf-8")

    name = f"sander-{secrets.token_hex(4)}"
    cmd = build_command(name, parm7.parent, workdir, parm7.name, coords.name, image)
    base: Dict[str, Any] = {"theory": theory, "charge": charge, "workdir": str(workdir), "container": name,
                            "command": cmd}

    start = time.monotonic()
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_s)
    except subprocess.TimeoutExpired:
        subprocess.run(["docker", "rm", "-f", name], capture_output=True, text=True, timeout=30)
        return {**base, "ok": False, "qm_escf_kcal": None, "total_energy_kcal": None,
                "qm_resp_charge_sum": None, "link_atoms": None, "odd_electrons": None,
                "exit_code": None, "wall_time_s": round(time.monotonic() - start, 2),
                "errors": [f"timeout after {timeout_s}s; container {name} removed"]}
    wall = round(time.monotonic() - start, 2)

    out_path = workdir / "sp.out"
    parsed = parse_sander_output(out_path.read_text(encoding="utf-8", errors="replace"), theory) \
        if out_path.exists() else parse_sander_output("", theory)
    if proc.returncode != 0:
        parsed["ok"] = False
        if not parsed["errors"]:
            # sander wrote no diagnosable QMMM: line; fall back to what the process said.
            tail = (proc.stderr or proc.stdout or "").strip().splitlines()[-10:]
            parsed["errors"] = tail or [f"sander exited with code {proc.returncode}"]
    if not out_path.exists():
        parsed["errors"].append("sp.out was not produced")

    return {**base, **parsed, "exit_code": proc.returncode, "wall_time_s": wall,
            "mdout": str(out_path) if out_path.exists() else None}


def build_md_command(
    name: str,
    parm7_mount: str,
    rst7_mount: str,
    workdir: Path,
    refdir: Optional[Path] = None,
    image: str = ENGINE_IMAGE,
) -> List[str]:
    cmd = ["docker", "run", "--rm", "--name", name]
    if refdir and refdir != workdir:
        cmd.extend(["-v", f"{refdir}:/ref:ro"])
    cmd.extend([
        "-v", f"{workdir}:/work",
        image,
        "sander", "-O",
        "-i", "md.mdin",
        "-o", "md.out",
        "-r", "md.rst7",
        "-x", "traj.nc",
        "-p", parm7_mount,
        "-c", rst7_mount,
    ])
    return cmd


def run_qmmm_md(
    workdir: Path | str,
    parm7: Path | str,
    rst7: Path | str,
    mask: str,
    charge: int,
    theory: str = "PM6",
    steps: int = 1000,
    dt: float = 0.001,
    timeout_s: int = 600,
    image: str = ENGINE_IMAGE,
) -> Dict[str, Any]:
    """Run one short QM/MM MD simulation inside the engine container and parse md.out."""
    parm7 = Path(parm7).resolve()
    rst7 = Path(rst7).resolve()
    workdir = Path(workdir).resolve()

    if not parm7.exists() or not rst7.exists():
        raise FileNotFoundError(f"missing topology or restart: {parm7}, {rst7}")
    if parm7.parent != rst7.parent and parm7.parent != workdir and rst7.parent != workdir:
        raise ValueError("parm7 and rst7 must live in the same directory (mounted read-only at /ref) or in workdir")
    validate_inputs(mask, charge, theory, "gb")

    workdir.mkdir(parents=True, exist_ok=True)
    (workdir / "md.mdin").write_text(mdin_md_text(mask, charge, theory, steps, dt), encoding="utf-8")

    name = f"sander-md-{secrets.token_hex(4)}"

    # Determine container mounts
    if parm7.parent == workdir:
        parm7_mount = f"/work/{parm7.name}"
        refdir = None
    else:
        parm7_mount = f"/ref/{parm7.name}"
        refdir = parm7.parent

    if rst7.parent == workdir:
        rst7_mount = f"/work/{rst7.name}"
    else:
        rst7_mount = f"/ref/{rst7.name}"

    cmd = build_md_command(name, parm7_mount, rst7_mount, workdir, refdir=refdir, image=image)
    base: Dict[str, Any] = {
        "theory": theory,
        "charge": charge,
        "mask": mask,
        "steps": steps,
        "dt": dt,
        "workdir": str(workdir),
        "container": name,
        "command": cmd,
    }

    start = time.monotonic()
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_s)
    except subprocess.TimeoutExpired:
        subprocess.run(["docker", "rm", "-f", name], capture_output=True, text=True, timeout=30)
        return {
            **base,
            "ok": False,
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
            "wall_time_s": round(time.monotonic() - start, 2),
            "errors": [f"timeout after {timeout_s}s; container {name} removed"],
            "traj": None,
            "mdout": None,
        }
    wall = round(time.monotonic() - start, 2)

    out_path = workdir / "md.out"
    traj_path = workdir / "traj.nc"
    parsed = parse_sander_md_output(out_path.read_text(encoding="utf-8", errors="replace"), theory) \
        if out_path.exists() else parse_sander_md_output("", theory)

    if proc.returncode != 0:
        parsed["ok"] = False
        if not parsed["errors"]:
            tail = (proc.stderr or proc.stdout or "").strip().splitlines()[-10:]
            parsed["errors"] = tail or [f"sander exited with code {proc.returncode}"]
    if not out_path.exists():
        parsed["errors"].append("md.out was not produced")

    return {
        **base,
        **parsed,
        "exit_code": proc.returncode,
        "wall_time_s": wall,
        "mdout": str(out_path) if out_path.exists() else None,
        "traj": str(traj_path) if traj_path.exists() else None,
    }
