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


class ChimeraXGenerator:
    """Generates UCSF ChimeraX command scripts (.cxc) for QM/MM simulation partitions."""

    def generate_script(
        self,
        partition: QMMMPartition,
        structure_path: str | Path,
        output_script_path: Optional[str | Path] = None,
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
            f"open {struct_path}",
            "",
            "# 2. Styling MM protein background",
            "hide",
            "cartoon",
            "color /A-Z grey(0.85)",
            "transparency 50 cartoon",
            "",
            "# 3. Highlight QM Region",
        ]

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
            "lighting soft",
            f"echo 'ActiveSite: QM/MM partitioned region displayed with {len(partition.link_atoms)} link atoms.'",
        ])

        script_content = "\n".join(lines) + "\n"

        if output_script_path:
            out_p = Path(output_script_path)
            out_p.parent.mkdir(parents=True, exist_ok=True)
            with open(out_p, "w", encoding="utf-8") as f:
                f.write(script_content)

        return script_content
