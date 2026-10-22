"""ActiveSite — QM/MM Active Site Partitioning & Link Atom Placement.

Identifies active site pocket residues around ligands or catalytic metal centers,
places covalent hydrogen link atoms across severed single bonds, balances formal charges,
and generates Track 02 Decision Cards explaining every boundary choice.
"""
from __future__ import annotations

import logging
import math
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple
import numpy as np
import parmed as pmd

from activesite.chem.protonation import ProtonationAgent
from activesite.models import (
    AlternativeChoice,
    DecisionCard,
    DecisionCategory,
    LinkAtom,
    QMMMPartition,
    ResidueRole,
    ResidueSelection,
)

logger = logging.getLogger(__name__)


def format_amber_qmmask(resids: List[int]) -> str:
    """Build an Amber residue mask with a single leading colon.

    Amber ``qmmask`` syntax is ``:371,34,137``, not ``:371,:34,:137``.
    """
    if not resids:
        return ""
    return ":" + ",".join(str(resid) for resid in resids)


# Valence electron counts for neutral elements commonly in bio-molecules
ELEMENT_VALENCE = {
    "H": 1,
    "C": 4,
    "N": 5,
    "O": 6,
    "F": 7,
    "P": 5,
    "S": 6,
    "CL": 7,
    "BR": 7,
    "I": 7,
    "MG": 2,
    "ZN": 2,
    "CA": 2,
    "FE": 8,
}


def compute_link_atom_coords(
    qm_pos: np.ndarray, mm_pos: np.ndarray, bond_length: float = 1.09
) -> Tuple[float, float, float]:
    """Calculate 3D Cartesian coordinates for a capping hydrogen link atom."""
    vec = mm_pos - qm_pos
    dist = np.linalg.norm(vec)
    if dist < 1e-4:
        direction = np.array([1.0, 0.0, 0.0])
    else:
        direction = vec / dist
    la_pos = qm_pos + direction * bond_length
    return (float(la_pos[0]), float(la_pos[1]), float(la_pos[2]))


class QMMMPartitioner:
    """Partitions macromolecular structures into QM and MM sub-systems with verifiable rationale."""

    def __init__(self, protonation_agent: Optional[ProtonationAgent] = None):
        self.protonation_agent = protonation_agent or ProtonationAgent()

    def partition_ligand_system(
        self,
        pdb_path: str | Path,
        ligand_resname: str,
        cutoff_radius: float = 4.0,
        ph: float = 7.4,
        target_chain: Optional[str] = None,
        literature_contacts: Optional[Dict[str, str]] = None,
        expected_absent: Optional[Dict[str, str]] = None,
    ) -> QMMMPartition:
        """Partition a ligand-protein complex into QM and MM regions."""
        pdb_path = Path(pdb_path)
        struct = pmd.load_file(str(pdb_path))

        # 1. Locate ligand atoms
        ligand_atoms = [
            a for a in struct.atoms
            if a.residue.name.upper() == ligand_resname.upper()
            and (target_chain is None or a.residue.chain == target_chain)
        ]
        if not ligand_atoms:
            # Fallback to any ligand match without chain filter
            ligand_atoms = [
                a for a in struct.atoms if a.residue.name.upper() == ligand_resname.upper()
            ]

        if not ligand_atoms:
            raise ValueError(f"Ligand '{ligand_resname}' not found in structure {pdb_path}")

        lig_coords = np.array([[a.xx, a.xy, a.xz] for a in ligand_atoms])
        lig_residue = ligand_atoms[0].residue

        decision_cards: List[DecisionCard] = []

        # Decision Card: Radius Selection
        radius_card = DecisionCard(
            decision_id=f"DEC_RADIUS_{cutoff_radius:.1f}A",
            category=DecisionCategory.ACTIVE_SITE_RADIUS,
            target=f"Active Site around {ligand_resname}",
            choice=f"Partition at {cutoff_radius:.1f} Angstrom cutoff radius",
            alternatives=[
                AlternativeChoice(
                    name="Tight 3.0 Angstrom cutoff",
                    rejected_reason="Truncates critical second-sphere hydrogen bonds and active-site dipole polarization.",
                ),
                AlternativeChoice(
                    name="Broad 6.0 Angstrom cutoff",
                    rejected_reason="Increases QM atom count > 150 atoms, incurring unacceptable ~10x computational scaling without thermodynamic gain.",
                ),
            ],
            rationale=(
                f"A {cutoff_radius:.1f} A cutoff captures direct hydrogen bonds and short-range polarization forces "
                f"between {ligand_resname} and the binding pocket, while allowing classical MM point charges to treat "
                f"long-range bulk electrostatics efficiently."
            ),
            confidence=0.95,
            evidence={"cutoff_radius_angstrom": cutoff_radius, "num_ligand_atoms": len(ligand_atoms)},
        )
        decision_cards.append(radius_card)

        # 2. Evaluate all other residues in structure for proximity
        qm_residues: List[ResidueSelection] = []
        link_atoms: List[LinkAtom] = []

        # Add the ligand itself
        lig_charge, lig_card = self.protonation_agent.evaluate_ligand(ligand_resname, ph=ph)
        decision_cards.append(lig_card)

        qm_residues.append(
            ResidueSelection(
                resname=lig_residue.name,
                resid=lig_residue.number,
                chain=lig_residue.chain,
                role=ResidueRole.LIGAND,
                is_qm=True,
                formal_charge=lig_charge,
            )
        )

        # Group non-ligand atoms by residue
        residues_by_id: Dict[Tuple[str, int], List[pmd.Atom]] = {}
        for a in struct.atoms:
            if a.residue == lig_residue:
                continue
            key = (a.residue.name, a.residue.number)
            residues_by_id.setdefault(key, []).append(a)

        included_res_keys: Set[Tuple[str, int]] = set()

        for (resname, resid), atoms in residues_by_id.items():
            # Skip bulk water unless catalytic
            if resname in ("HOH", "WAT"):
                continue

            res_coords = np.array([[a.xx, a.xy, a.xz] for a in atoms])
            # Minimum distance between any residue atom and any ligand atom
            diffs = res_coords[:, np.newaxis, :] - lig_coords[np.newaxis, :, :]
            dists = np.sqrt(np.sum(diffs ** 2, axis=-1))
            min_dist = float(np.min(dists))

            res_label = f"{resname}{resid}"
            is_lit_contact = literature_contacts and any(
                k.upper() in res_label.upper() for k in literature_contacts
            )
            is_expected_absent = expected_absent and any(
                k.upper() in res_label.upper() for k in expected_absent
            )

            # Inclusion criteria: within cutoff OR specifically highlighted in literature contacts
            if (min_dist <= cutoff_radius or is_lit_contact) and not is_expected_absent:
                included_res_keys.add((resname, resid))
                # Evaluate protonation state
                prot = self.protonation_agent.evaluate_residue(
                    resname=resname,
                    resid=resid,
                    chain=atoms[0].residue.chain,
                    ph=ph,
                    h_bond_donor=(min_dist < 3.2),
                )
                if prot.decision_card:
                    decision_cards.append(prot.decision_card)

                role = ResidueRole.FIRST_SHELL_H_BOND if min_dist < 3.2 else ResidueRole.SECOND_SHELL_POLAR
                qm_residues.append(
                    ResidueSelection(
                        resname=resname,
                        resid=resid,
                        chain=atoms[0].residue.chain,
                        role=role,
                        is_qm=True,
                        protonation_state=prot.state,
                        formal_charge=prot.formal_charge,
                        pka_calculated=prot.pka_calculated,
                    )
                )

                # Decision card for residue inclusion
                contact_note = (
                    literature_contacts.get(res_label, "")
                    if literature_contacts and res_label in literature_contacts
                    else f"Heavy atom within {min_dist:.2f} A of ligand"
                )
                res_card = DecisionCard(
                    decision_id=f"DEC_INC_{res_label}",
                    category=DecisionCategory.RESIDUE_INCLUSION,
                    target=res_label,
                    choice=f"Include {res_label} in QM region",
                    alternatives=[
                        AlternativeChoice(
                            name=f"Keep {res_label} in MM region",
                            rejected_reason=f"Close contact ({min_dist:.2f} A) produces orbital overlap and charge transfer requiring quantum treatment.",
                        )
                    ],
                    rationale=f"{res_label} is located {min_dist:.2f} A from ligand: {contact_note}.",
                    confidence=0.96,
                    evidence={"min_distance_angstrom": round(min_dist, 2), "contact_note": contact_note},
                )
                decision_cards.append(res_card)

                # Link atom placement: sever CA - CB single bond
                ca_atom = next((a for a in atoms if a.name == "CA"), None)
                cb_atom = next((a for a in atoms if a.name == "CB"), None)
                if ca_atom and cb_atom:
                    la_pos = compute_link_atom_coords(
                        np.array([cb_atom.xx, cb_atom.xy, cb_atom.xz]),
                        np.array([ca_atom.xx, ca_atom.xy, ca_atom.xz]),
                        bond_length=1.09,
                    )
                    link_atom = LinkAtom(
                        link_id=f"LA_{res_label}_CA_CB",
                        residue_name=resname,
                        residue_number=resid,
                        qm_atom="CB",
                        mm_atom="CA",
                        element="H",
                        bond_type="single_sigma",
                        position=la_pos,
                    )
                    link_atoms.append(link_atom)

            elif is_expected_absent:
                # Residue explicitly evaluated and excluded (e.g., Thr766 in EGFR)
                absent_reason = expected_absent.get(res_label, f"Excluded at {min_dist:.2f} A")
                exc_card = DecisionCard(
                    decision_id=f"DEC_EXC_{res_label}",
                    category=DecisionCategory.RESIDUE_INCLUSION,
                    target=res_label,
                    choice=f"Exclude {res_label} from QM region",
                    alternatives=[
                        AlternativeChoice(
                            name=f"Include {res_label} in QM",
                            rejected_reason=f"Indirect interaction: {absent_reason}.",
                        )
                    ],
                    rationale=f"{res_label} exclusion justified: {absent_reason}.",
                    confidence=0.94,
                    evidence={"min_distance_angstrom": round(min_dist, 2), "reason": absent_reason},
                )
                decision_cards.append(exc_card)

        # Decision Card: Link Atom Cut Selection
        if link_atoms:
            la_card = DecisionCard(
                decision_id="DEC_LINK_ATOM_CUT_SELECTION",
                category=DecisionCategory.LINK_ATOM,
                target="QM/MM Boundary Bond Cuts",
                choice="Place capping hydrogen link atoms along C_alpha - C_beta single sigma bonds",
                alternatives=[
                    AlternativeChoice(
                        name="Cut peptide backbone C - N amide bond",
                        rejected_reason="Cutting the conjugated peptide amide bond disrupts resonance, causes artificial charge accumulation, and unphysically alters backbone dipole moments.",
                    ),
                    AlternativeChoice(
                        name="Include entire amino acid residue without cutting",
                        rejected_reason="Requires cutting peptide bonds on both sides or propagating QM region through the entire backbone chain.",
                    ),
                ],
                rationale=(
                    "The C_alpha - C_beta single sigma bond possesses low dipole polarity and negligible conjugation, "
                    "making it the gold-standard QM/MM boundary cut that minimizes orbital truncation artifacts."
                ),
                confidence=0.98,
                evidence={"num_link_atoms_placed": len(link_atoms), "capping_element": "H", "bond_length_A": 1.09},
            )
            decision_cards.append(la_card)

        # 3. Calculate total QM charge
        total_qm_charge = sum(r.formal_charge for r in qm_residues)

        # 4. Generate Amber QM mask (:resid1,resid2,... — one leading colon)
        amber_qmmask = format_amber_qmmask([r.resid for r in qm_residues])

        # Decision Card: QM Charge
        charge_card = DecisionCard(
            decision_id="DEC_QMCHARGE_ASSIGNMENT",
            category=DecisionCategory.CHARGE_AND_SPIN,
            target="qmcharge",
            choice=f"Set qmcharge = {total_qm_charge}",
            alternatives=[
                AlternativeChoice(
                    name=f"Set qmcharge = {total_qm_charge + 1 if total_qm_charge <= 0 else total_qm_charge - 1}",
                    rejected_reason="Violates formal charge sum of partitioned active site components.",
                )
            ],
            rationale=(
                f"Sum of formal charges across {len(qm_residues)} QM moieties: "
                f"{ligand_resname} ({lig_charge:+d}) + protein residues ({total_qm_charge - lig_charge:+d}) = {total_qm_charge:+d}."
            ),
            confidence=0.97,
            evidence={"total_charge": total_qm_charge, "num_qm_residues": len(qm_residues)},
        )
        decision_cards.append(charge_card)

        return QMMMPartition(
            system_name=f"{pdb_path.stem}_{ligand_resname.lower()}",
            qm_residues=qm_residues,
            link_atoms=link_atoms,
            qm_charge=total_qm_charge,
            spin_multiplicity=1,
            cutoff_radius_angstrom=cutoff_radius,
            amber_qmmask=amber_qmmask,
            decision_cards=decision_cards,
        )

    def partition_metal_system(
        self,
        parm7_path: str | Path,
        coords_path: Optional[str | Path] = None,
        metal_resid: int = 371,
        cutoff_radius: float = 4.0,
        ph: float = 7.4,
    ) -> QMMMPartition:
        """Partition an enzymatic metallonuclease active site (e.g. I-PpoI endonuclease)."""
        parm7_path = Path(parm7_path)
        if coords_path:
            struct = pmd.load_file(str(parm7_path), str(coords_path))
        else:
            struct = pmd.load_file(str(parm7_path))

        decision_cards: List[DecisionCard] = []

        # Find metal atom
        metal_atoms = [a for a in struct.atoms if a.residue.number == metal_resid]
        if not metal_atoms:
            # Try searching by element MG
            metal_atoms = [a for a in struct.atoms if a.name.upper() in ("MG", "ZN", "CA", "FE")]

        if not metal_atoms:
            raise ValueError(f"Metal residue :{metal_resid} not found in {parm7_path}")

        metal_atom = metal_atoms[0]
        metal_coords = np.array([metal_atom.xx, metal_atom.xy, metal_atom.xz])

        qm_residues: List[ResidueSelection] = []
        link_atoms: List[LinkAtom] = []

        # 1. Add metal center (Mg2+ has formal charge +2)
        metal_charge = 2 if metal_atom.name.upper().startswith("MG") else 2
        qm_residues.append(
            ResidueSelection(
                resname=metal_atom.residue.name,
                resid=metal_atom.residue.number,
                chain=metal_atom.residue.chain,
                role=ResidueRole.METAL,
                is_qm=True,
                formal_charge=metal_charge,
            )
        )

        metal_card = DecisionCard(
            decision_id=f"DEC_METAL_INC_{metal_atom.residue.name}{metal_resid}",
            category=DecisionCategory.RESIDUE_INCLUSION,
            target=f"{metal_atom.residue.name}{metal_resid}",
            choice=f"Include {metal_atom.residue.name} in QM region with charge {metal_charge:+d}",
            alternatives=[
                AlternativeChoice(
                    name="Treat metal as classical +2.0 point charge",
                    rejected_reason="Point charge fails to model charge transfer, ligand-field polarization, and chemical bond activation in DNA cleavage.",
                )
            ],
            rationale=f"Catalytic divalent {metal_atom.name} directly coordinates the scissile phosphate and nucleophilic water, requiring quantum orbital treatment.",
            confidence=0.99,
            evidence={"metal_element": metal_atom.name, "formal_charge": metal_charge},
        )
        decision_cards.append(metal_card)

        # 2. Find coordinating residues within cutoff radius
        residues_by_id: Dict[Tuple[str, int], List[pmd.Atom]] = {}
        for a in struct.atoms:
            if a.residue == metal_atom.residue:
                continue
            key = (a.residue.name, a.residue.number)
            residues_by_id.setdefault(key, []).append(a)

        for (resname, resid), atoms in residues_by_id.items():
            res_coords = np.array([[a.xx, a.xy, a.xz] for a in atoms])
            diffs = res_coords - metal_coords
            dists = np.sqrt(np.sum(diffs ** 2, axis=-1))
            min_dist = float(np.min(dists))

            if min_dist <= cutoff_radius:
                res_label = f"{resname}{resid}"
                if resname in ("WAT", "HOH"):
                    # Catalytic coordinated water
                    qm_residues.append(
                        ResidueSelection(
                            resname=resname,
                            resid=resid,
                            chain=atoms[0].residue.chain,
                            role=ResidueRole.CATALYTIC_WATER,
                            is_qm=True,
                            formal_charge=0,
                        )
                    )
                elif resname in ("DA", "DG", "DC", "DT"):
                    # DNA scissile phosphate moiety (-1 formal charge)
                    qm_residues.append(
                        ResidueSelection(
                            resname=resname,
                            resid=resid,
                            chain=atoms[0].residue.chain,
                            role=ResidueRole.CATALYTIC,
                            is_qm=True,
                            formal_charge=-1,
                        )
                    )
                else:
                    # Amino acid residue coordinating metal (e.g. His119, Asn160, Gln139)
                    prot = self.protonation_agent.evaluate_residue(
                        resname=resname,
                        resid=resid,
                        chain=atoms[0].residue.chain,
                        ph=ph,
                        coordinating_metal="Mg2+",
                    )
                    if prot.decision_card:
                        decision_cards.append(prot.decision_card)

                    qm_residues.append(
                        ResidueSelection(
                            resname=resname,
                            resid=resid,
                            chain=atoms[0].residue.chain,
                            role=ResidueRole.CATALYTIC,
                            is_qm=True,
                            protonation_state=prot.state,
                            formal_charge=prot.formal_charge,
                            pka_calculated=prot.pka_calculated,
                        )
                    )

                    # Link atom cut
                    ca_atom = next((a for a in atoms if a.name == "CA"), None)
                    cb_atom = next((a for a in atoms if a.name == "CB"), None)
                    if ca_atom and cb_atom:
                        la_pos = compute_link_atom_coords(
                            np.array([cb_atom.xx, cb_atom.xy, cb_atom.xz]),
                            np.array([ca_atom.xx, ca_atom.xy, ca_atom.xz]),
                        )
                        link_atoms.append(
                            LinkAtom(
                                link_id=f"LA_{res_label}_CA_CB",
                                residue_name=resname,
                                residue_number=resid,
                                qm_atom="CB",
                                mm_atom="CA",
                                element="H",
                                position=la_pos,
                            )
                        )

        # 3. Calculate preliminary QM charge
        net_charge = sum(r.formal_charge for r in qm_residues)

        amber_qmmask = format_amber_qmmask([r.resid for r in qm_residues])

        charge_card = DecisionCard(
            decision_id=f"DEC_METAL_ACTIVE_SITE_CHARGE_{metal_resid}",
            category=DecisionCategory.CHARGE_AND_SPIN,
            target="qmcharge",
            choice=f"Assign preliminary qmcharge = {net_charge:+d}",
            alternatives=[
                AlternativeChoice(
                    name="Neutral QM region (qmcharge = 0)",
                    rejected_reason="Violates valence electron neutrality with coordinated Mg2+ cation.",
                )
            ],
            rationale=f"Coordination sphere charge balance with Mg2+ (+2) and coordinating active site moieties sums to {net_charge:+d}.",
            confidence=0.92,
            evidence={"net_charge": net_charge, "num_residues": len(qm_residues)},
        )
        decision_cards.append(charge_card)

        return QMMMPartition(
            system_name=f"ippoi_active_site_{metal_resid}",
            qm_residues=qm_residues,
            link_atoms=link_atoms,
            qm_charge=net_charge,
            spin_multiplicity=1,
            cutoff_radius_angstrom=cutoff_radius,
            amber_qmmask=amber_qmmask,
            decision_cards=decision_cards,
        )
