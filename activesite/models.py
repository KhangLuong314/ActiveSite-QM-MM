"""ActiveSite — Data Models & Decision Cards (Track 02: Explainable Agents)."""
from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional, Tuple
from pydantic import BaseModel, Field


class DecisionCategory(str, Enum):
    ACTIVE_SITE_RADIUS = "active_site_radius"
    RESIDUE_INCLUSION = "residue_inclusion"
    PROTONATION_STATE = "protonation_state"
    LINK_ATOM = "link_atom"
    CHARGE_AND_SPIN = "charge_and_spin"
    SOLVENT_HANDLING = "solvent_handling"
    THEORY_SELECTION = "theory_selection"
    CRITIC_CORRECTION = "critic_correction"


class AlternativeChoice(BaseModel):
    """An alternative choice evaluated and rejected by the agent."""
    name: str = Field(description="Name or description of the rejected alternative")
    rejected_reason: str = Field(description="Scientific reason for rejecting this alternative")


class DecisionCard(BaseModel):
    """Mandatory Track 02 Scientific Decision Card.

    Every autonomous decision (radius, link atom, protonation, charge, spin)
    must produce a verifiable explanation with alternatives and scientific rationale.
    """
    decision_id: str = Field(description="Unique identifier for the decision")
    category: DecisionCategory = Field(description="Category of the decision")
    target: str = Field(description="Subject entity, e.g. 'MET769', 'Cut CA-CB', 'qmcharge'")
    choice: str = Field(description="What was selected by the agent")
    alternatives: List[AlternativeChoice] = Field(
        default_factory=list,
        description="Alternatives evaluated and the reasons they were rejected",
    )
    rationale: str = Field(
        description="Scientific justification (hydrogen bonding, pKa shift, steric penalty, orbital continuity, etc.)"
    )
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="Confidence score between 0.0 and 1.0",
    )
    evidence: Dict[str, Any] = Field(
        default_factory=dict,
        description="Quantitative evidence (distances in Angstroms, pKa values, electron counts)",
    )

    def to_markdown(self) -> str:
        """Render the decision card into readable markdown."""
        alt_lines = "\n".join(
            f"  - **{alt.name}**: {alt.rejected_reason}" for alt in self.alternatives
        )
        evidence_lines = "\n".join(
            f"  - `{k}`: {v}" for k, v in self.evidence.items()
        )
        return (
            f"### 🎴 Decision Card: `{self.decision_id}` ({self.category.value})\n"
            f"- **Target:** {self.target}\n"
            f"- **Selected Choice:** **{self.choice}** (Confidence: {self.confidence:.2f})\n"
            f"- **Scientific Rationale:** {self.rationale}\n"
            f"- **Evaluated Alternatives:**\n{alt_lines if alt_lines else '  - None'}\n"
            f"- **Quantitative Evidence:**\n{evidence_lines if evidence_lines else '  - None'}\n"
        )


class LinkAtom(BaseModel):
    """Covalent link atom cutting across QM/MM boundary."""
    link_id: str = Field(description="Identifier for the link atom, e.g. 'LA_HIS119_CA_CB'")
    residue_name: str
    residue_number: int
    qm_atom: str = Field(description="Atom in the QM region (e.g. 'CB')")
    mm_atom: str = Field(description="Atom in the MM region (e.g. 'CA')")
    element: str = Field(default="H", description="Capping element, typically hydrogen")
    bond_type: str = Field(default="single_sigma", description="Type of bond severed")
    position: Optional[Tuple[float, float, float]] = Field(
        default=None, description="Calculated 3D Cartesian coordinates of the link atom (x, y, z)"
    )


class ResidueRole(str, Enum):
    LIGAND = "ligand"
    METAL = "metal"
    CATALYTIC = "catalytic"
    FIRST_SHELL_H_BOND = "first_shell_h_bond"
    SECOND_SHELL_POLAR = "second_shell_polar"
    CATALYTIC_WATER = "catalytic_water"
    BULK_SOLVENT = "bulk_solvent"


class ResidueSelection(BaseModel):
    """A residue or moiety designated for the QM or boundary region."""
    resname: str
    resid: int
    chain: Optional[str] = None
    role: ResidueRole
    is_qm: bool = True
    protonation_state: Optional[str] = Field(
        default=None, description="Assigned protonation state (e.g. HIE, HID, HIP, ASH, GLH, LYN)"
    )
    formal_charge: int = 0
    pka_calculated: Optional[float] = None
    h_bond_partners: List[str] = Field(default_factory=list)


class QMMMPartition(BaseModel):
    """Complete specification of the QM/MM partitioned active site."""
    system_name: str
    qm_residues: List[ResidueSelection] = Field(default_factory=list)
    link_atoms: List[LinkAtom] = Field(default_factory=list)
    qm_charge: int = Field(default=0, description="Total formal charge of QM region (qmcharge)")
    spin_multiplicity: int = Field(default=1, description="Spin multiplicity (2S + 1)")
    total_valence_electrons: int = Field(default=0, description="Total valence electrons in QM region")
    amber_qmmask: str = Field(default="", description="Amber format QM mask, e.g. ':371,119,139'")
    cutoff_radius_angstrom: float = Field(default=4.0, description="Active site inclusion radius")
    decision_cards: List[DecisionCard] = Field(default_factory=list)


class SimulationResult(BaseModel):
    """Result of QM/MM or semi-empirical simulation calculation."""
    success: bool
    system_name: str
    qm_theory: str = Field(default="PM6", description="QM theory level (PM6, GFN2-xTB, B3LYP)")
    energy_hartree: Optional[float] = None
    energy_kcal_mol: Optional[float] = None
    sample_mode: bool = False
    execution_time_seconds: float = 0.0
    stdout_summary: str = ""
    error_message: Optional[str] = None
    decision_cards: List[DecisionCard] = Field(default_factory=list)
    output_files: Dict[str, str] = Field(default_factory=dict)
    engine: Dict[str, Any] = Field(
        default_factory=dict,
        description="Raw parsed engine output (sander.run_single_point) when the engine ran; empty otherwise",
    )
