"""Unit tests for ChimeraXGenerator (.cxc)."""
import pytest
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
    assert "color :999 magenta" in script
    assert "color :769 cyan" in script
    assert "shape sphere center 12.500,34.200,56.100" in script
    assert "hbonds" in script
