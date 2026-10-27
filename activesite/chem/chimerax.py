"""ActiveSite — UCSF ChimeraX Script Generator (.cxc).

Generates automated, publication-ready ChimeraX command scripts for interactive 3D visualization
of QM/MM boundaries, link atoms, hydrogen bonding networks, and electronic polarization regions.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from activesite.models import QMMMPartition, ResidueRole

logger = logging.getLogger(__name__)


def _quote_path(p: Path | str) -> str:
    s = str(p)
    return f'"{s}"' if not (s.startswith('"') and s.endswith('"')) else s


class ChimeraXGenerator:
    """Generates UCSF ChimeraX command scripts (.cxc) for QM/MM simulation partitions."""

    def generate_script(
        self,
        partition: QMMMPartition,
        structure_path: str | Path,
        output_script_path: Optional[str | Path] = None,
        traj_path: Optional[str | Path] = None,
    ) -> str:
        """Create a complete ChimeraX command script visualizing the QM/MM partitioned system."""
        struct_path = Path(structure_path).resolve()
        
        # Build selection strings for ChimeraX
        qm_residue_spec = []
        ligand_spec = []
        metal_spec = []

        for r in partition.qm_residues:
            chain_prefix = f"/{r.chain}:" if r.chain else ":"
            spec = f"{chain_prefix}{r.resid}"
            if r.role == ResidueRole.LIGAND:
                ligand_spec.append(spec)
            elif r.role == ResidueRole.METAL:
                metal_spec.append(spec)
            else:
                qm_residue_spec.append(spec)

        lig_cmd = " ".join(ligand_spec) if ligand_spec else ""
        metal_cmd = " ".join(metal_spec) if metal_spec else ""
        qm_res_cmd = " ".join(qm_residue_spec) if qm_residue_spec else ""

        all_qm_spec = " ".join(filter(None, [lig_cmd, metal_cmd, qm_res_cmd]))

        lines = [
            "# ActiveSite UCSF ChimeraX Visualization Script",
            f"# System: {partition.system_name}",
            f"# Total QM Residues: {len(partition.qm_residues)} | QM Charge: {partition.qm_charge:+d} | Spin: {partition.spin_multiplicity}",
            "",
            "# 1. Load molecular structure",
            f'open {_quote_path(struct_path)}',
        ]

        if traj_path:
            lines.extend([
                f'open {_quote_path(Path(traj_path).resolve())} format amber structureModel #1',
                "coordset slider #1",
            ])

        lines.extend([
            "",
            "# 2. Styling MM protein background",
            "hide",
            "cartoon",
            "color #1 lightgray",
            "",
            "# 3. Highlight QM Region",
        ])

        if all_qm_spec:
            lines.extend([
                f"show {all_qm_spec} atoms",
                f"style {all_qm_spec} stick",
            ])

        if lig_cmd:
            lines.extend([
                "# Ligand: Magenta sticks",
                f"color {lig_cmd} magenta",
                f"style {lig_cmd} ball",
            ])

        if metal_cmd:
            lines.extend([
                "# Catalytic Metal: Bright Green sphere",
                f"show {metal_cmd} atoms",
                f"color {metal_cmd} light green",
                f"style {metal_cmd} sphere",
            ])

        if qm_res_cmd:
            lines.extend([
                "# First-shell QM Residues: Cyan sticks",
                f"color {qm_res_cmd} cyan",
                f"label {qm_res_cmd} text {{res_name}}{{res_number}} offset 0,0,1.5",
            ])

        # Link atoms
        if partition.link_atoms:
            lines.append("")
            lines.append("# 4. Covalent Link Atoms (Yellow Spheres along C_alpha - C_beta cuts)")
            for la in partition.link_atoms:
                if la.position:
                    x, y, z = la.position
                    lines.append(
                        f"# Link Atom: {la.link_id} capping {la.residue_name}{la.residue_number} {la.qm_atom}"
                    )
                    lines.append(
                        f"shape sphere center {x:.3f},{y:.3f},{z:.3f} radius 0.35 color gold name '{la.link_id}'"
                    )

        # Hydrogen bonds detection
        lines.extend([
            "",
            "# 5. Display Hydrogen Bonds in the Active Site",
            f"hbonds {all_qm_spec} reveal true makePseudobonds true color yellow radius 0.08",
            "",
            "# 6. Center view on QM region",
            f"view {all_qm_spec}",
            "clip off",
            "lighting soft shadows false depthCue false",
            f"echo 'ActiveSite: QM/MM partitioned region displayed with {len(partition.link_atoms)} link atoms.'",
        ])

        script_content = "\n".join(lines) + "\n"

        if output_script_path:
            out_p = Path(output_script_path)
            out_p.parent.mkdir(parents=True, exist_ok=True)
            with open(out_p, "w", encoding="utf-8") as f:
                f.write(script_content)

        return script_content

    def generate_trajectory_script(
        self,
        parm7_path: str | Path,
        traj_path: str | Path,
        ligand_resname: str = "AQ4",
        output_script_path: Optional[str | Path] = None,
        rst7_path: Optional[str | Path] = None,
    ) -> str:
        """Create a ChimeraX script to load complex PDB reference, MD trajectory, and slider."""
        target_dir = Path(output_script_path).parent if output_script_path else Path(traj_path).parent
        struct_p = Path(parm7_path).resolve()
        pdb_path = None

        def _save_pdb_with_ligand_name(struct, out_path: Path):
            if ligand_resname and ligand_resname != "LIG":
                for res in struct.residues:
                    if res.name == "LIG":
                        res.name = ligand_resname
            struct.save(str(out_path), overwrite=True)

        if struct_p.suffix.lower() == ".pdb" and struct_p.exists():
            pdb_path = struct_p
        elif rst7_path is not None and struct_p.exists() and Path(rst7_path).exists():
            import parmed
            pdb_out = target_dir / "complex.pdb"
            try:
                parm = parmed.load_file(str(struct_p), str(rst7_path))
                _save_pdb_with_ligand_name(parm, pdb_out)
                pdb_path = pdb_out.resolve()
            except Exception:
                pdb_path = struct_p
        else:
            if (target_dir / "complex.pdb").exists():
                pdb_path = (target_dir / "complex.pdb").resolve()
            elif (struct_p.parent / "complex.pdb").exists():
                pdb_path = (struct_p.parent / "complex.pdb").resolve()
            elif struct_p.suffix.lower() in (".parm7", ".prmtop"):
                rst_candidates = [struct_p.parent / "min.rst7", struct_p.parent / "complex.rst7", target_dir / "min.rst7"]
                found_rst = next((c for c in rst_candidates if c.exists()), None)
                if found_rst:
                    import parmed
                    pdb_out = target_dir / "complex.pdb"
                    try:
                        parm = parmed.load_file(str(struct_p), str(found_rst))
                        _save_pdb_with_ligand_name(parm, pdb_out)
                        pdb_path = pdb_out.resolve()
                    except Exception:
                        pdb_path = struct_p
                else:
                    pdb_path = struct_p
            else:
                pdb_path = struct_p

        # If complex.pdb exists but has generic 'LIG' residues, update to ligand_resname
        if pdb_path and pdb_path.exists() and pdb_path.suffix.lower() == ".pdb":
            try:
                content = pdb_path.read_text(encoding="utf-8")
                if " LIG " in content and ligand_resname and ligand_resname != "LIG":
                    pdb_path.write_text(content.replace(" LIG ", f" {ligand_resname:3s} "), encoding="utf-8")
            except Exception as exc:
                logger.debug("Could not rename LIG in %s: %s", pdb_path, exc)

        lines = [
            "# ActiveSite UCSF ChimeraX Trajectory Visualization Script",
            f'open {_quote_path(Path(pdb_path).resolve())}',
            f'open {_quote_path(Path(traj_path).resolve())} format amber structureModel #1',
            "coordset slider #1",
            "",
            "# Styling: ribbon for protein, magenta ball/stick for ligand, yellow pseudobonds for hbonds",
            "hide",
            "cartoon",
            "color #1 lightgray",
            f"show :{ligand_resname} atoms",
            f"color :{ligand_resname} magenta",
            f"style :{ligand_resname} ball",
            f"hbonds :{ligand_resname} reveal true makePseudobonds true color yellow radius 0.08",
            f"view :{ligand_resname}",
            "clip off",
            "lighting soft shadows false depthCue false",
        ]
        script_content = "\n".join(lines) + "\n"

        if output_script_path:
            out_p = Path(output_script_path)
            out_p.parent.mkdir(parents=True, exist_ok=True)
            with open(out_p, "w", encoding="utf-8") as f:
                f.write(script_content)

        return script_content
