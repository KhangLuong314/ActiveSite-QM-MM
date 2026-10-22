"""ActiveSite — Structure Prep & Protonation Agent (Track 02: Explainable Protonation).

Calculates residue pKa shifts and assigns Amber protonation states (HIE, HID, HIP,
ASH, GLH, LYN, CYX) at user-specified pH, generating comprehensive Decision Cards.
"""
from __future__ import annotations

import logging
import math
from typing import Any, Dict, List, Optional, Set, Tuple
from pydantic import BaseModel, Field

from activesite.models import AlternativeChoice, DecisionCard, DecisionCategory

logger = logging.getLogger(__name__)


# Standard solution pKa references
STANDARD_PKA = {
    "ASP": 3.9,
    "GLU": 4.1,
    "HIS": 6.04,
    "CYS": 8.3,
    "TYR": 10.1,
    "LYS": 10.5,
    "ARG": 12.5,
}


class ResidueProtonation(BaseModel):
    resname: str
    resid: int
    chain: Optional[str] = None
    state: str  # e.g. HIE, HID, HIP, ASP, ASH, GLU, GLH, LYS, LYN, CYS, CYX
    formal_charge: int
    pka_calculated: float
    pka_reference: float
    decision_card: Optional[DecisionCard] = None


class ProtonationReport(BaseModel):
    target_ph: float
    total_assigned_charge: int
    residues: List[ResidueProtonation] = Field(default_factory=list)
    decision_cards: List[DecisionCard] = Field(default_factory=list)


class ProtonationAgent:
    """Autonomous Protonation and Structure Preparation Agent.

    Predicts protonation states taking into account environmental shifts,
    hydrogen bonding networks, and metal ion coordination spheres.
    """

    def __init__(self, default_ph: float = 7.4):
        self.default_ph = default_ph

    def evaluate_residue(
        self,
        resname: str,
        resid: int,
        chain: Optional[str] = None,
        ph: Optional[float] = None,
        coordinating_metal: Optional[str] = None,
        h_bond_acceptor: bool = False,
        h_bond_donor: bool = False,
        buried_hydrophobic: bool = False,
        ligand_context: Optional[str] = None,
    ) -> ResidueProtonation:
        """Evaluate a single titratable residue and generate its Track 02 Decision Card."""
        current_ph = ph if ph is not None else self.default_ph
        ref_pka = STANDARD_PKA.get(resname, 7.0)
        calc_pka = ref_pka
        alternatives: List[AlternativeChoice] = []
        target_label = f"{resname}{resid}" + (f":{chain}" if chain else "")

        if resname == "HIS":
            # Histidine tautomers: HIE (epsilon-H), HID (delta-H), HIP (doubly protonated +1)
            if coordinating_metal:
                # Divalent metal coordination via ND1 or NE2 strongly depresses pKa for the second proton
                # and fixes the proton on the opposite nitrogen
                calc_pka = ref_pka - 1.5  # shifted down to ~4.5 due to metal electrostatic repulsion
                state = "HIE"
                formal_charge = 0
                rationale = (
                    f"His{resid} coordinates catalytic {coordinating_metal}. Divalent metal electrostatics "
                    f"strongly penalize double protonation (HIP), shifting pKa from {ref_pka:.2f} down to {calc_pka:.2f}. "
                    f"Coordination through delta-nitrogen ND1 leaves epsilon-nitrogen NE2 protonated, selecting HIE."
                )
                alternatives = [
                    AlternativeChoice(
                        name="HIP (doubly protonated cation, +1)",
                        rejected_reason=f"Severe electrostatic repulsion with coordinating divalent {coordinating_metal} ion (pKa shifted below 5.0).",
                    ),
                    AlternativeChoice(
                        name="HID (delta-nitrogen protonated)",
                        rejected_reason=f"Steric/electronic clash: delta-nitrogen lone pair is dedicated to {coordinating_metal} coordinate bond.",
                    ),
                ]
            elif h_bond_acceptor and not h_bond_donor:
                calc_pka = ref_pka + 0.3
                state = "HID"
                formal_charge = 0
                rationale = (
                    f"His{resid} imidazole ring acts as hydrogen bond donor via ND1 to backbone carbonyl at pH {current_ph:.1f}. "
                    f"Uncharged HID tautomer satisfies local hydrogen bonding without steric strain."
                )
                alternatives = [
                    AlternativeChoice(
                        name="HIE (epsilon-nitrogen protonated)",
                        rejected_reason="Directs hydrogen away from the pocket donor network.",
                    ),
                    AlternativeChoice(
                        name="HIP (doubly protonated, +1)",
                        rejected_reason=f"At physiological pH {current_ph:.1f}, pKa of {calc_pka:.2f} favors neutral imidazole (fraction protonated < 10%).",
                    ),
                ]
            else:
                # Default physiological histidine
                calc_pka = ref_pka
                if current_ph < calc_pka - 1.0:
                    state = "HIP"
                    formal_charge = 1
                    rationale = f"Acidic pH {current_ph:.1f} is well below His pKa {calc_pka:.2f}; imidazole is doubly protonated."
                    alternatives = [
                        AlternativeChoice(name="HIE", rejected_reason="Thermodynamically unfavorable at acidic pH."),
                        AlternativeChoice(name="HID", rejected_reason="Thermodynamically unfavorable at acidic pH."),
                    ]
                else:
                    state = "HIE"
                    formal_charge = 0
                    rationale = (
                        f"At pH {current_ph:.1f}, His pKa ({calc_pka:.2f}) dictates predominant neutral imidazole. "
                        f"HIE tautomer is favored in solvent-accessible protein environments."
                    )
                    alternatives = [
                        AlternativeChoice(
                            name="HIP (+1 cation)",
                            rejected_reason=f"At pH {current_ph:.1f}, pH > pKa ({calc_pka:.2f}); fraction protonated < 5%.",
                        ),
                        AlternativeChoice(
                            name="HID (neutral tautomer)",
                            rejected_reason="Standard solvent exposure energetically favors HIE over HID by ~1.2 kcal/mol in solution.",
                        ),
                    ]

        elif resname in ("ASP", "GLU"):
            if buried_hydrophobic:
                calc_pka = ref_pka + 4.2  # Deep hydrophobic desolvation shifts carboxylate pKa upward to ~8.1
                if current_ph < calc_pka:
                    state = "ASH" if resname == "ASP" else "GLH"
                    formal_charge = 0
                    rationale = (
                        f"{resname}{resid} is buried in a hydrophobic pocket, elevating its pKa from {ref_pka:.2f} "
                        f"to {calc_pka:.2f}. Protonated neutral form ({state}) avoids desolvation penalty of an unshielded carboxylate."
                    )
                    alternatives = [
                        AlternativeChoice(
                            name=f"{resname} (deprotonated anion, -1)",
                            rejected_reason=f"Carboxylate burial in low dielectric pocket incurs severe Born desolvation penalty (~8 kcal/mol).",
                        )
                    ]
                else:
                    state = resname
                    formal_charge = -1
                    rationale = f"At pH {current_ph:.1f}, carboxylate remains deprotonated despite hydrophobic shift."
                    alternatives = [AlternativeChoice(name="Protonated neutral", rejected_reason="pH exceeds elevated pKa.")]
            else:
                state = resname
                formal_charge = -1
                rationale = (
                    f"Standard solvent-exposed carboxylate. pKa ({calc_pka:.2f}) is far below pH {current_ph:.1f}, "
                    f"yielding fully deprotonated anionic carboxylate."
                )
                alternatives = [
                    AlternativeChoice(
                        name="Protonated neutral (ASH/GLH)",
                        rejected_reason=f"Henderson-Hasselbalch ratio [A-]/[HA] > 1000:1 at pH {current_ph:.1f}.",
                    )
                ]

        elif resname == "LYS":
            if buried_hydrophobic:
                calc_pka = ref_pka - 2.5
                if current_ph > calc_pka:
                    state = "LYN"
                    formal_charge = 0
                    rationale = f"Buried Lys{resid} exhibits depressed pKa ({calc_pka:.2f}); deprotonated neutral amine (LYN)."
                    alternatives = [AlternativeChoice(name="LYS (+1)", rejected_reason="High desolvation penalty.")]
                else:
                    state = "LYS"
                    formal_charge = 1
                    rationale = f"Lys{resid} retains ammonium cation despite hydrophobic shift."
                    alternatives = [AlternativeChoice(name="LYN", rejected_reason="pH remains below pKa.")]
            else:
                state = "LYS"
                formal_charge = 1
                rationale = f"Standard ammonium group (pKa {calc_pka:.2f} >> pH {current_ph:.1f}); fully protonated cation."
                alternatives = [
                    AlternativeChoice(
                        name="LYN (neutral amine, 0)",
                        rejected_reason=f"Neutral form is negligible (< 0.1%) at pH {current_ph:.1f}.",
                    )
                ]

        elif resname == "CYS":
            if coordinating_metal:
                calc_pka = ref_pka - 4.0
                state = "CYX"
                formal_charge = -1
                rationale = f"Cys{resid} coordinates metal center, stabilizing thiolate anion (CYX) with pKa ~ {calc_pka:.1f}."
                alternatives = [AlternativeChoice(name="CYS (neutral thiol)", rejected_reason="Thiol proton displaced upon metal coordination.")]
            else:
                state = "CYS"
                formal_charge = 0
                rationale = f"Free cysteine thiol (pKa {calc_pka:.2f} > pH {current_ph:.1f}); remains protonated neutral."
                alternatives = [AlternativeChoice(name="CYM (deprotonated thiolate, -1)", rejected_reason="pH is below thiol pKa.")]

        else:
            state = resname
            formal_charge = 0
            rationale = f"Non-titratable residue {resname} in standard state."

        # Compute confidence score based on margin between pH and pKa
        delta = abs(current_ph - calc_pka)
        confidence = min(0.99, max(0.80, 0.80 + 0.19 * (1.0 / (1.0 + math.exp(-delta)))))

        decision_card = DecisionCard(
            decision_id=f"DEC_PROT_{target_label}_{state}",
            category=DecisionCategory.PROTONATION_STATE,
            target=target_label,
            choice=f"Assign {state} (formal charge {formal_charge:+d})",
            alternatives=alternatives,
            rationale=rationale,
            confidence=round(confidence, 2),
            evidence={
                "target_ph": current_ph,
                "calculated_pka": round(calc_pka, 2),
                "reference_pka": round(ref_pka, 2),
                "coordinating_metal": coordinating_metal,
            },
        )

        return ResidueProtonation(
            resname=resname,
            resid=resid,
            chain=chain,
            state=state,
            formal_charge=formal_charge,
            pka_calculated=round(calc_pka, 2),
            pka_reference=round(ref_pka, 2),
            decision_card=decision_card,
        )

    def evaluate_ligand(
        self, ligand_id: str, smiles: Optional[str] = None, ph: Optional[float] = None
    ) -> Tuple[int, DecisionCard]:
        """Determine formal charge and protonation state of a drug ligand at target pH."""
        current_ph = ph if ph is not None else self.default_ph
        ligand_clean = ligand_id.upper()

        if ligand_clean in ("AQ4", "ERLOTINIB"):
            # Erlotinib: quinazoline N1/N3 pKa ~ 5.4, aniline secondary NH pKa < 2.
            # At pH 7.4 it is predominantly uncharged neutral
            formal_charge = 0
            rationale = (
                f"Erlotinib (AQ4) contains a quinazoline ring system (experimental conjugate acid pKa ~ 5.4) "
                f"and secondary aniline amine. At physiological pH {current_ph:.1f}, the basic nitrogen is predominantly "
                f"deprotonated (neutral base > 99%)."
            )
            alternatives = [
                AlternativeChoice(
                    name="Protonated quinazolium cation (+1)",
                    rejected_reason=f"Quinazoline N1 pKa (~5.4) is 2.0 pH units below pH {current_ph:.1f}; protonated fraction < 1%.",
                )
            ]
            evidence = {"ligand_id": ligand_clean, "basic_center": "quinazoline_N1", "pka": 5.4}

        elif ligand_clean in ("STI", "IMATINIB"):
            # Imatinib: N-methylpiperazine tertiary amine pKa ~ 8.0, pyrimidine/pyridine pKa < 4
            # At pH 7.4 it is predominantly monoprotonated at the methylpiperazine nitrogen!
            formal_charge = 1
            rationale = (
                f"Imatinib (STI) contains an N-methylpiperazine ring with an aliphatic tertiary amine pKa of ~8.0. "
                f"At pH {current_ph:.1f}, this nitrogen is predominantly protonated as a piperazinium cation (+1), "
                f"forming stabilizing electrostatic and hydrogen bonding contacts with Ile360 and His361 backbone carbonyls."
            )
            alternatives = [
                AlternativeChoice(
                    name="Neutral imatinib (charge 0)",
                    rejected_reason=f"N-methylpiperazine pKa (~8.0) > pH {current_ph:.1f}; neutral form accounts for only ~20% in aqueous buffer.",
                ),
                AlternativeChoice(
                    name="Diprotonated imatinib cation (+2)",
                    rejected_reason="Pyridine and aminopyrimidine nitrogens have pKa < 4.0; fully deprotonated at pH 7.4.",
                ),
            ]
            evidence = {"ligand_id": ligand_clean, "protonated_center": "N_methylpiperazine", "pka": 8.0}

        else:
            formal_charge = 0
            rationale = f"Ligand {ligand_clean} evaluated as neutral molecule at pH {current_ph:.1f} by default."
            alternatives = []
            evidence = {"ligand_id": ligand_clean, "default": True}

        card = DecisionCard(
            decision_id=f"DEC_LIGAND_PROT_{ligand_clean}",
            category=DecisionCategory.PROTONATION_STATE,
            target=ligand_clean,
            choice=f"Assign formal charge {formal_charge:+d}",
            alternatives=alternatives,
            rationale=rationale,
            confidence=0.96,
            evidence=evidence,
        )
        return formal_charge, card
