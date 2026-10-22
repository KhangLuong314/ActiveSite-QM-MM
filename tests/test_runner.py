"""Unit tests for ChemistryRunner: Amber input generation and honest no-engine results."""
from pathlib import Path

import pytest

from activesite.chem import runner as runner_mod
from activesite.chem import sander
from activesite.chem.runner import (
    ENGINE_SKIPPED_NO_DOCKER,
    ENGINE_SKIPPED_NO_TOPOLOGY,
    ENGINE_SKIPPED_SAMPLE_MODE,
    ChemistryRunner,
)
from activesite.models import QMMMPartition, ResidueRole, ResidueSelection

FIXTURES = Path(__file__).parent / "fixtures"


def _partition() -> QMMMPartition:
    return QMMMPartition(
        system_name="egfr_erlotinib",
        qm_residues=[
            ResidueSelection(resname="AQ4", resid=1, role=ResidueRole.LIGAND, formal_charge=0),
            ResidueSelection(resname="MET", resid=769, role=ResidueRole.FIRST_SHELL_H_BOND, formal_charge=0),
        ],
        qm_charge=0,
        spin_multiplicity=2,  # Amber PM6 RHF still requires spin=1
        amber_qmmask=":1,:769",
    )


def test_sanitize_mask():
    assert ChemistryRunner.sanitize_mask(":1,:769") == ":1,769"
    assert ChemistryRunner.sanitize_mask("") == ":1"


def test_solvent_detection(tmp_path: Path):
    boxed = tmp_path / "boxed.parm7"
    boxed.write_text("%VERSION\n%FLAG BOX_DIMENSIONS\n%FORMAT(5E16.8)\n")
    dry = tmp_path / "dry.parm7"
    dry.write_text("%VERSION\n%FLAG POINTERS\n")
    assert ChemistryRunner.solvent_for(boxed) == "pme"
    assert ChemistryRunner.solvent_for(dry) == "gb"
    assert ChemistryRunner.solvent_for(tmp_path / "missing.parm7") == "gb"


def test_run_simulation_sample_mode_is_honest(tmp_path: Path):
    """SAMPLE_MODE never fabricates: the result says the engine was skipped and carries null energies."""
    runner = ChemistryRunner(sample_mode=True)
    result = runner.run_simulation(
        partition=_partition(), prmtop_path="dummy.parm7", inpcrd_path="dummy.inpcrd",
        output_dir=tmp_path / "runs", qm_theory="PM6",
    )
    assert result.success is False
    assert result.energy_hartree is None and result.energy_kcal_mol is None
    assert result.error_message == ENGINE_SKIPPED_SAMPLE_MODE
    assert result.engine == {}
    assert not (tmp_path / "runs").exists()
    assert any("THEORY" in c.decision_id for c in result.decision_cards)


def test_run_simulation_needs_amber_topology(tmp_path: Path):
    runner = ChemistryRunner(sample_mode=False)
    result = runner.run_simulation(_partition(), "data/reference/egfr/1m17.pdb", "data/reference/egfr/1m17.pdb",
                                   output_dir=tmp_path)
    assert result.success is False and result.error_message == ENGINE_SKIPPED_NO_TOPOLOGY


def test_run_simulation_without_docker(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(sander, "docker_available", lambda image: False)
    runner = ChemistryRunner(sample_mode=False)
    result = runner.run_simulation(_partition(), tmp_path / "x.parm7", tmp_path / "x.ncrst", output_dir=tmp_path)
    assert result.success is False and result.error_message == ENGINE_SKIPPED_NO_DOCKER
    assert result.energy_kcal_mol is None


def test_run_simulation_maps_engine_output(tmp_path: Path, monkeypatch):
    """With the engine mocked at the sander boundary, the result carries the parsed energies verbatim."""
    parm = tmp_path / "x.parm7"
    parm.write_text("%FLAG BOX_DIMENSIONS\n")
    (tmp_path / "x.ncrst").write_text("x\n")
    monkeypatch.setattr(sander, "docker_available", lambda image: True)
    seen = {}

    def fake_run_single_point(**kw):
        seen.update(kw)
        parsed = sander.parse_sander_output((FIXTURES / "sander_ok.out").read_text(), kw["theory"])
        return {**parsed, "exit_code": 0, "wall_time_s": 36.9, "theory": kw["theory"], "charge": kw["charge"],
                "workdir": str(kw["workdir"]), "mdout": str(Path(kw["workdir"]) / "sp.out")}

    monkeypatch.setattr(sander, "run_single_point", fake_run_single_point)
    runner = ChemistryRunner(sample_mode=False)
    result = runner.run_simulation(_partition(), parm, tmp_path / "x.ncrst", output_dir=tmp_path / "runs")

    assert seen["mask"] == ":1,769" and seen["charge"] == 0 and seen["solvent"] == "pme"
    assert seen["workdir"] == tmp_path / "runs" / "egfr_erlotinib"
    assert result.success is True
    assert result.energy_kcal_mol == pytest.approx(-2.3471e5)
    assert result.energy_hartree == pytest.approx(-2.3471e5 / 627.509)
    assert result.engine["qm_escf_kcal"] == pytest.approx(-1442.3127)
    assert result.engine["link_atoms"] == 4
    assert result.error_message is None
    assert "mdout" in result.output_files


def test_run_simulation_reports_engine_failure(tmp_path: Path, monkeypatch):
    parm = tmp_path / "x.parm7"
    parm.write_text("%FLAG POINTERS\n")
    (tmp_path / "x.ncrst").write_text("x\n")
    monkeypatch.setattr(sander, "docker_available", lambda image: True)
    monkeypatch.setattr(sander, "run_single_point", lambda **kw: {
        **sander.parse_sander_output((FIXTURES / "sander_odd.out").read_text(), "PM6"),
        "exit_code": 1, "wall_time_s": 3.0, "theory": "PM6", "charge": 0, "workdir": str(kw["workdir"]),
        "mdout": None,
    })
    result = ChemistryRunner(sample_mode=False).run_simulation(_partition(), parm, tmp_path / "x.ncrst",
                                                                output_dir=tmp_path / "runs")
    assert result.success is False
    assert result.energy_kcal_mol is None and result.energy_hartree is None
    assert "odd number of electrons" in result.error_message
    assert result.engine["odd_electrons"] == 203


def test_runner_has_no_placeholder_energy_path():
    src = Path(runner_mod.__file__).read_text()
    assert "REFERENCE_ENERGIES" not in src
    assert "ENGINE_NOT_IMPLEMENTED" not in src
    assert "parse_sander_energy" not in src          # the old lenient parser is gone; sander.py owns parsing
