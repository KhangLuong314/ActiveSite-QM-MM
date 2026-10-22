"""Unit tests for ChemistryRunner: Amber input generation and honest no-engine results."""
from pathlib import Path

from activesite.chem.runner import ENGINE_NOT_IMPLEMENTED, ChemistryRunner
from activesite.models import QMMMPartition, ResidueRole, ResidueSelection


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


def test_generate_amber_mdin():
    runner = ChemistryRunner(sample_mode=True)
    mdin = runner.generate_amber_mdin(_partition(), qm_theory="PM6", min_steps=300)
    assert "&cntrl" in mdin
    assert "&qmmm" in mdin
    assert "qmmask=':1,769'" in mdin
    assert ",:" not in mdin
    assert "qm_theory='PM6'" in mdin
    assert "qmcharge=0" in mdin
    assert "spin=1" in mdin


def test_run_simulation_reports_engine_not_implemented(tmp_path: Path):
    """No engine exists yet: the result must say so and carry null energies."""
    runner = ChemistryRunner(sample_mode=True)
    result = runner.run_simulation(
        partition=_partition(),
        prmtop_path="dummy.parm7",
        inpcrd_path="dummy.inpcrd",
        output_dir=tmp_path / "runs",
        qm_theory="PM6",
    )

    assert result.success is False
    assert result.energy_hartree is None
    assert result.energy_kcal_mol is None
    assert result.error_message == ENGINE_NOT_IMPLEMENTED
    assert ENGINE_NOT_IMPLEMENTED in result.stdout_summary
    # Input generation still happens so the engine module can consume it later.
    assert Path(result.output_files["mdin"]).exists()
    assert "mdout" not in result.output_files
    assert not (tmp_path / "runs" / "egfr_erlotinib" / "qmmm.mdout").exists()
    assert any("THEORY" in c.decision_id for c in result.decision_cards)


def test_runner_has_no_reference_energy_table():
    import activesite.chem.runner as runner_mod

    assert not hasattr(runner_mod, "REFERENCE_ENERGIES")


SANDER_MDOUT_FIXTURE = """\
   NSTEP       ENERGY          RMS            GMAX         NAME    NUMBER
      1      -1.2345E+03     1.0000E+00     2.0000E+00     C          12

                    FINAL RESULTS
   NSTEP       ENERGY          RMS            GMAX         NAME    NUMBER
     50      -1.2300E+03     1.0000E-01     2.0000E-01     C          12

 NSTEP =       50   TIME(PS) =       0.000  TEMP(K) =     0.00  PRESS =     0.0
 Etot   =     -1230.4567  EKtot   =         0.0000  EPtot      =     -1230.4567
"""


def test_parse_sander_energy_from_text_fixture():
    energy = ChemistryRunner.parse_sander_energy_text(SANDER_MDOUT_FIXTURE)
    assert energy == -1230.4567


def test_parse_sander_energy_returns_none_when_absent(tmp_path: Path):
    """A file with no energy line yields None, never a default number."""
    assert ChemistryRunner.parse_sander_energy_text("sander: input error\n") is None
    mdout = tmp_path / "qmmm.mdout"
    mdout.write_text("no energies here\n")
    assert ChemistryRunner()._parse_sander_energy(mdout) is None
