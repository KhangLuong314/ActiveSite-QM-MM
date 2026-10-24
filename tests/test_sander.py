"""Tests for activesite.chem.sander: pure parser on fixtures, docker command construction, and (Docker only) the engine."""
import math
import subprocess
from pathlib import Path

import pytest

from activesite.chem import sander
from activesite.chem.sander import (
    ENGINE_IMAGE,
    build_command,
    build_md_command,
    docker_available,
    mdin_md_text,
    mdin_text,
    parse_sander_md_output,
    parse_sander_output,
    run_qmmm_md,
    run_single_point,
)

FIXTURES = Path(__file__).parent / "fixtures"
REF = Path("data/reference/qmmm_dft")


# --------------------------------------------------------------------- parser
def test_parse_ok_fixture():
    r = parse_sander_output((FIXTURES / "sander_ok.out").read_text(), "PM6")
    assert r["ok"] is True
    assert r["qm_escf_kcal"] == pytest.approx(-456.5628)
    assert r["total_energy_kcal"] == pytest.approx(-3.0206e5)
    assert r["qm_resp_charge_sum"] == pytest.approx(1.144)
    assert r["link_atoms"] == 4
    assert r["odd_electrons"] is None
    assert r["errors"] == []


def test_parse_odd_fixture():
    r = parse_sander_output((FIXTURES / "sander_odd.out").read_text(), "PM6")
    assert r["ok"] is False
    assert r["qm_escf_kcal"] is None
    assert r["total_energy_kcal"] is None
    assert r["odd_electrons"] == 203
    assert r["link_atoms"] == 4
    assert r["qm_resp_charge_sum"] == pytest.approx(1.144)
    assert any("odd number of electrons" in e for e in r["errors"])
    assert any("incorrectly" in e for e in r["errors"])
    assert all(e.startswith("QMMM:") for e in r["errors"])


def test_parse_only_reads_final_results_block():
    text = (FIXTURES / "sander_ok.out").read_text()
    # Change the pre-final ESCF; the parsed value must still come from the FINAL RESULTS block.
    head, _, tail = text.partition("FINAL RESULTS")
    head = head.replace("PM6ESCF =     -456.5628", "PM6ESCF =    -9999.0000")
    r = parse_sander_output(head + "FINAL RESULTS" + tail, "PM6")
    assert r["qm_escf_kcal"] == pytest.approx(-456.5628)
    # Without a FINAL RESULTS block there is no energy at all.
    assert parse_sander_output(head, "PM6")["qm_escf_kcal"] is None


def test_parse_non_finite_escf():
    text = (FIXTURES / "sander_ok.out").read_text()
    for bad in ("NaN", "Infinity", "************"):
        t = text.replace("PM6ESCF =     -456.5628", f"PM6ESCF = {bad}")
        r = parse_sander_output(t, "PM6")
        assert r["ok"] is False
        assert r["qm_escf_kcal"] is None
        assert "non-finite QM energy" in r["errors"]


def test_parse_theory_name_matters():
    text = (FIXTURES / "sander_ok.out").read_text()
    assert parse_sander_output(text, "DFTB")["ok"] is False
    assert parse_sander_output("", "PM6") == {
        "ok": False, "qm_escf_kcal": None, "total_energy_kcal": None, "qm_resp_charge_sum": None,
        "link_atoms": None, "odd_electrons": None, "errors": [],
    }


# ----------------------------------------------------------------------- mdin
def test_mdin_templates():
    pme = mdin_text("@1-3", 1, "PM6", "pme")
    assert pme.splitlines()[0] == "ActiveSite PM6 single point, qmcharge=+1, PME"
    for key in ("imin=1", "maxcyc=1", "ntmin=2", "ntb=1", "qm_ewald=1", "qm_pme=1", "qmmm_switch=1",
                "qmmask='@1-3'", "qm_theory='PM6'", "qmcharge=1", "spin=1", "verbosity=0"):
        assert key in pme
    gb = mdin_text(":1,2", -1, "PM6", "gb")
    assert gb.splitlines()[0] == "ActiveSite PM6 single point, qmcharge=-1, GB"
    for key in ("ntb=0", "igb=5", "cut=999.0", "qmgb=2", "qmcut=999.0", "qmcharge=-1"):
        assert key in gb
    assert "qm_ewald" not in gb


@pytest.mark.parametrize("mask,charge,theory,solvent", [
    ("@1-3'; rm -rf /", 0, "PM6", "pme"),
    ("@1-3", 0.5, "PM6", "pme"),
    ("@1-3", True, "PM6", "pme"),
    ("@1-3", 0, "B3LYP", "pme"),
    ("@1-3", 0, "PM6", "vacuum"),
    ("", 0, "PM6", "pme"),
])
def test_inputs_are_allow_listed(mask, charge, theory, solvent):
    with pytest.raises(ValueError):
        mdin_text(mask, charge, theory, solvent)


# --------------------------------------------------------------------- docker
def test_build_command_matches_spec(tmp_path):
    cmd = build_command("sander-deadbeef", Path("/data/ref"), Path("/data/work"), "a.parm7", "a.ncrst")
    assert cmd == [
        "docker", "run", "--rm", "--name", "sander-deadbeef",
        "-v", "/data/ref:/ref:ro", "-v", "/data/work:/work", ENGINE_IMAGE,
        "sander", "-O", "-i", "sp.mdin", "-o", "sp.out", "-r", "sp.rst7",
        "-p", "/ref/a.parm7", "-c", "/ref/a.ncrst",
    ]


def _ref_files(tmp_path):
    ref = tmp_path / "ref"
    ref.mkdir()
    (ref / "sys.parm7").write_text("%VERSION\n")
    (ref / "sys.ncrst").write_text("x\n")
    return ref


def test_run_single_point_invokes_docker_and_parses(tmp_path, monkeypatch):
    ref = _ref_files(tmp_path)
    work = tmp_path / "work"
    calls = []

    def fake_run(cmd, capture_output, text, timeout):
        calls.append((cmd, timeout))
        assert (work / "sp.mdin").exists(), "mdin must be written before docker runs"
        (work / "sp.out").write_text((FIXTURES / "sander_ok.out").read_text())
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(sander.subprocess, "run", fake_run)
    r = run_single_point(ref / "sys.parm7", ref / "sys.ncrst", "@1-3", 1, work, theory="PM6", timeout_s=42)

    cmd, timeout = calls[0]
    assert timeout == 42
    assert cmd[:4] == ["docker", "run", "--rm", "--name"] and cmd[4].startswith("sander-") and len(cmd[4]) == 15
    assert cmd[5:9] == ["-v", f"{ref.resolve()}:/ref:ro", "-v", f"{work.resolve()}:/work"]
    assert cmd[9] == ENGINE_IMAGE
    assert cmd[10:] == ["sander", "-O", "-i", "sp.mdin", "-o", "sp.out", "-r", "sp.rst7",
                        "-p", "/ref/sys.parm7", "-c", "/ref/sys.ncrst"]
    assert r["ok"] is True and r["qm_escf_kcal"] == pytest.approx(-456.5628)
    assert r["exit_code"] == 0 and r["wall_time_s"] >= 0
    assert r["theory"] == "PM6" and r["charge"] == 1 and r["workdir"] == str(work.resolve())
    assert (work / "sp.mdin").read_text().startswith("ActiveSite PM6 single point, qmcharge=+1, PME")


def test_run_single_point_timeout_removes_container(tmp_path, monkeypatch):
    ref = _ref_files(tmp_path)
    calls = []

    def fake_run(cmd, capture_output, text, timeout):
        calls.append(cmd)
        if cmd[:2] == ["docker", "run"]:
            raise subprocess.TimeoutExpired(cmd, timeout)
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(sander.subprocess, "run", fake_run)
    r = run_single_point(ref / "sys.parm7", ref / "sys.ncrst", "@1-3", 1, tmp_path / "w", timeout_s=1)
    assert r["ok"] is False and r["qm_escf_kcal"] is None and r["exit_code"] is None
    assert any("timeout" in e for e in r["errors"])
    name = calls[0][4]
    assert calls[1] == ["docker", "rm", "-f", name]


def test_run_single_point_nonzero_exit_uses_stderr_tail(tmp_path, monkeypatch):
    ref = _ref_files(tmp_path)

    def fake_run(cmd, capture_output, text, timeout):
        return subprocess.CompletedProcess(cmd, 125, stdout="", stderr="docker: Error response\nimage not found\n")

    monkeypatch.setattr(sander.subprocess, "run", fake_run)
    r = run_single_point(ref / "sys.parm7", ref / "sys.ncrst", "@1-3", 1, tmp_path / "w")
    assert r["ok"] is False and r["exit_code"] == 125
    assert "image not found" in r["errors"] and "sp.out was not produced" in r["errors"]


def test_run_single_point_rejects_split_directories(tmp_path):
    ref = _ref_files(tmp_path)
    other = tmp_path / "other"
    other.mkdir()
    (other / "sys.ncrst").write_text("x\n")
    with pytest.raises(ValueError):
        run_single_point(ref / "sys.parm7", other / "sys.ncrst", "@1-3", 1, tmp_path / "w")


# ----------------------------------------------------------------------- MD
SAMPLE_MD_OUT = """
          -------------------------------------------------------
          Amber 26 SANDER                              2026
          -------------------------------------------------------
LOADING THE QUANTUM ATOMS AS GROUPS
     Mask :LIG; matches    52 atoms
 QM atom RESP charge sum (inc MM link) =    1.002
 nlink =    0

 NSTEP =       50   TIME(PS) =       0.050  TEMP(K) =   295.42  PRESS =     0.0
 Etot   =   -1520.1234  EKtot   =     210.1234  EPtot      =   -1730.2468
 PM6ESCF=    -350.5432
------------------------------------------------------------------------------
 NSTEP =      100   TIME(PS) =       0.100  TEMP(K) =   299.85  PRESS =     0.0
 Etot   =   -1518.2345  EKtot   =     212.4567  EPtot      =   -1730.6912
 PM6ESCF=    -351.1200
------------------------------------------------------------------------------
                    A V E R A G E S   O V E R     100 S T E P S


 NSTEP =      100   TIME(PS) =       0.100  TEMP(K) =   297.64  PRESS =     0.0
 Etot   =   -1519.1789  EKtot   =     211.2900  EPtot      =   -1730.4690
 PM6ESCF=    -350.8316
------------------------------------------------------------------------------


                    R M S  F L U C T U A T I O N S


 NSTEP =      100   TIME(PS) =       0.100  TEMP(K) =     3.12  PRESS =     0.0
 Etot   =       1.3450  EKtot   =       1.6500  EPtot      =       0.3142
 PM6ESCF=       0.4078
------------------------------------------------------------------------------
"""


def test_mdin_md_template():
    md = mdin_md_text(":LIG", 1, "PM6", steps=1000, dt=0.001)
    assert md.splitlines()[0] == "ActiveSite PM6 QM/MM MD, qmcharge=+1, GB"
    expected_cntrl = [
        "imin=0", "nstlim=1000", "dt=0.001",
        "ntx=1", "irest=0",
        "ntt=3", "gamma_ln=2.0", "tempi=300.0", "temp0=300.0",
        "ntb=0", "igb=5", "cut=999.0",
        "ntpr=50", "ntwx=50",
        "ifqnt=1",
    ]
    for key in expected_cntrl:
        assert key in md, f"missing cntrl key: {key}"

    expected_qmmm = [
        "qmmask=':LIG'",
        "qm_theory='PM6'",
        "qmcharge=1",
        "spin=1",
        "qmgb=2",
        "qmcut=999.0",
    ]
    for key in expected_qmmm:
        assert key in md, f"missing qmmm key: {key}"

    with pytest.raises(ValueError):
        mdin_md_text(":LIG", 1, "PM6", steps=-5)
    with pytest.raises(ValueError):
        mdin_md_text(":LIG", 1, "PM6", dt=0.0)


def test_parse_sander_md_output():
    r = parse_sander_md_output(SAMPLE_MD_OUT, "PM6")
    assert r["ok"] is True
    assert r["steps_completed"] == 100
    assert r["final_temperature_k"] == pytest.approx(299.85)
    assert r["qm_escf_kcal"] == pytest.approx(-351.1200)
    assert r["total_energy_kcal"] == pytest.approx(-1518.2345)
    assert r["qm_resp_charge_sum"] == pytest.approx(1.002)
    assert r["link_atoms"] == 0
    assert len(r["energy_progression"]) == 2
    assert r["energy_progression"][0]["nstep"] == 50
    assert r["energy_progression"][0]["temp_k"] == pytest.approx(295.42)
    assert r["energy_progression"][1]["nstep"] == 100
    assert r["averages"]["temp_k"] == pytest.approx(297.64)
    assert r["averages"]["qm_escf"] == pytest.approx(-350.8316)
    assert r["rms_fluctuations"]["temp_k"] == pytest.approx(3.12)
    assert r["rms_fluctuations"]["qm_escf"] == pytest.approx(0.4078)
    assert r["errors"] == []


def test_parse_sander_md_output_errors():
    empty = parse_sander_md_output("", "PM6")
    assert empty["ok"] is False
    assert empty["steps_completed"] == 0
    assert empty["final_temperature_k"] is None

    odd_text = SAMPLE_MD_OUT + "\n QMMM: odd number of electrons (203) incorrectly specified\n"
    r_odd = parse_sander_md_output(odd_text, "PM6")
    assert r_odd["ok"] is False
    assert r_odd["odd_electrons"] == 203
    assert any("odd number of electrons" in e for e in r_odd["errors"])


def test_build_md_command_matches_spec():
    cmd = build_md_command("sander-md-1234", "/ref/sys.parm7", "/ref/sys.rst7", Path("/data/work"), refdir=Path("/data/ref"))
    assert cmd == [
        "docker", "run", "--rm", "--name", "sander-md-1234",
        "-v", "/data/ref:/ref:ro",
        "-v", "/data/work:/work",
        ENGINE_IMAGE,
        "sander", "-O",
        "-i", "md.mdin",
        "-o", "md.out",
        "-r", "md.rst7",
        "-x", "traj.nc",
        "-p", "/ref/sys.parm7",
        "-c", "/ref/sys.rst7",
    ]


def test_run_qmmm_md_invokes_docker_and_parses(tmp_path, monkeypatch):
    ref = _ref_files(tmp_path)
    work = tmp_path / "work"
    calls = []

    def fake_run(cmd, capture_output, text, timeout):
        calls.append((cmd, timeout))
        assert (work / "md.mdin").exists(), "md.mdin must be written before docker runs"
        (work / "md.out").write_text(SAMPLE_MD_OUT)
        (work / "traj.nc").write_bytes(b"dummy_netcdf_bytes")
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(sander.subprocess, "run", fake_run)
    r = run_qmmm_md(work, ref / "sys.parm7", ref / "sys.ncrst", "@1-3", 1, theory="PM6", steps=100, dt=0.001, timeout_s=120)

    cmd, timeout = calls[0]
    assert timeout == 120
    assert cmd[:4] == ["docker", "run", "--rm", "--name"]
    assert cmd[4].startswith("sander-md-")
    assert "-x" in cmd and "traj.nc" in cmd
    assert r["ok"] is True
    assert r["steps_completed"] == 100
    assert r["final_temperature_k"] == pytest.approx(299.85)
    assert r["traj"] == str((work / "traj.nc").resolve())
    assert r["mdout"] == str((work / "md.out").resolve())


def test_trajectory_stability_and_dynamics_card():
    from activesite.agent.ligand import check_trajectory_stability, simulation_dynamics_card
    from activesite.models import DecisionCategory

    parm = Path("data/sample/egfr_erlotinib/prep/complex.parm7")
    min_rst = Path("data/sample/egfr_erlotinib/prep/min.rst7")

    # Single-point / min.rst7 geometry test
    stab = check_trajectory_stability(parm, min_rst, contact_pair=(":AQ4@N2", ":MET97@H"))
    assert stab["available"] is True
    assert stab["frames"] == 1
    assert stab["mean_distance"] < 2.5
    assert stab["ligand_retained"] is True

    md_res = {
        "ok": True,
        "steps_completed": 1000,
        "final_temperature_k": 301.2,
        "rms_fluctuations": {"temp_k": 4.5},
        "traj": str(min_rst),
    }
    card = simulation_dynamics_card(md_res, stab, steps=1000, dt=0.001)
    assert card.category == DecisionCategory.SIMULATION_DYNAMICS
    assert "1.0 fs time step" in card.choice
    assert "300 K Langevin thermostat" in card.choice
    assert "2.0 fs time step with SHAKE" in card.alternatives[0].name
    assert card.confidence >= 0.90
    assert card.evidence["temperature_k"] == 300.0


def test_chimerax_trajectory_script(tmp_path):
    from activesite.chem.chimerax import ChimeraXGenerator

    gen = ChimeraXGenerator()
    out_file = tmp_path / "trajectory.cxc"
    script = gen.generate_trajectory_script(
        "complex.parm7",
        "traj.nc",
        ligand_resname="AQ4",
        output_script_path=out_file,
    )
    assert out_file.exists()
    assert "open " in script and "complex.parm7" in script
    assert "open " in script and "traj.nc" in script
    assert "coordset slider #1" in script
    assert "color :AQ4 magenta" in script
    assert "view" in script


# --------------------------------------------------------------------- engine
ENGINE_READY = docker_available() and (REF / "step3_pbcsetup.parm7").exists() and (REF / "prod00.ncrst").exists()


@pytest.mark.slow
@pytest.mark.skipif(not ENGINE_READY, reason="Docker engine image or reference files not available")
def test_engine_site_a_single_point():
    from activesite.chem.qmregion import propose
    from activesite.chem.system import MolSystem

    sys_ = MolSystem(REF / "step3_pbcsetup.parm7", REF / "prod00.ncrst")
    mask = propose(sys_, 371).mask
    runs = Path("data/runs") / "sander_engine_test"

    odd = run_single_point(REF / "step3_pbcsetup.parm7", REF / "prod00.ncrst", mask, 0, runs / "charge0")
    assert odd["ok"] is False
    assert odd["odd_electrons"] is not None
    assert odd["qm_escf_kcal"] is None

    good = run_single_point(REF / "step3_pbcsetup.parm7", REF / "prod00.ncrst", mask, 1, runs / "charge1")
    assert good["ok"] is True, good["errors"]
    assert good["qm_escf_kcal"] is not None and math.isfinite(good["qm_escf_kcal"])
    assert good["link_atoms"] == 4
    assert (runs / "charge1" / "sp.out").exists()
