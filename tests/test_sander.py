"""Tests for activesite.chem.sander: pure parser on fixtures, docker command construction, and (Docker only) the engine."""
import math
import subprocess
from pathlib import Path

import pytest

from activesite.chem import sander
from activesite.chem.sander import (
    ENGINE_IMAGE,
    build_command,
    docker_available,
    mdin_text,
    parse_sander_output,
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
