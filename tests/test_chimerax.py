"""Unit tests for ChimeraXGenerator (.cxc)."""
from pathlib import Path
from activesite.chem.chimerax import ChimeraXGenerator
from activesite.models import LinkAtom, QMMMPartition, ResidueRole, ResidueSelection


def test_chimerax_script_generation(tmp_path: Path):
    gen = ChimeraXGenerator()
    partition = QMMMPartition(
        system_name="egfr_erlotinib",
        qm_residues=[
            ResidueSelection(resname="AQ4", resid=999, role=ResidueRole.LIGAND, formal_charge=0),
            ResidueSelection(resname="MET", resid=769, role=ResidueRole.FIRST_SHELL_H_BOND, formal_charge=0),
        ],
        link_atoms=[
            LinkAtom(
                link_id="LA_MET769",
                residue_name="MET",
                residue_number=769,
                qm_atom="CB",
                mm_atom="CA",
                position=(12.5, 34.2, 56.1),
            )
        ],
        qm_charge=0,
        spin_multiplicity=1,
    )

    out_file = tmp_path / "egfr.cxc"
    script = gen.generate_script(partition, "data/reference/egfr/1m17.pdb", output_script_path=out_file)

    assert out_file.exists()
    assert "open " in script
    assert "grey(0.85)" not in script
    assert "color #1 lightgray" in script
    assert "color :999 magenta" in script
    assert "color :769 cyan" in script
    assert "shape sphere center 12.500,34.200,56.100" in script
    assert "hbonds" in script
    assert "clip off" in script
    assert "lighting soft shadows false depthCue false" in script


def test_chimerax_trajectory_script_format(tmp_path: Path):
    gen = ChimeraXGenerator()
    out_file = tmp_path / "traj.cxc"
    parm_file = Path("data/sample/egfr_erlotinib/prep/complex.parm7")
    rst_file = Path("data/sample/egfr_erlotinib/prep/min.rst7")

    script = gen.generate_trajectory_script(
        parm_file,
        tmp_path / "traj.nc",
        ligand_resname="AQ4",
        output_script_path=out_file,
        rst7_path=rst_file,
    )

    assert out_file.exists()
    assert (tmp_path / "complex.pdb").exists()
    assert "AQ4" in (tmp_path / "complex.pdb").read_text()
    assert "grey(0.85)" not in script
    assert "color #1 lightgray" in script
    assert f'open "{tmp_path / "complex.pdb"}"' in script or f"open {tmp_path / 'complex.pdb'}" in script
    assert f'open "{tmp_path / "traj.nc"}" format amber structureModel #1' in script or f"open {tmp_path / 'traj.nc'} format amber structureModel #1" in script
    assert "coordset slider #1" in script
    assert "color :AQ4 magenta" in script
    assert "cartoon" in script
    assert "hbonds :AQ4 reveal true makePseudobonds true color yellow radius 0.08" in script
    assert "view :AQ4" in script
    assert "clip off" in script
    assert "lighting soft shadows false depthCue false" in script
