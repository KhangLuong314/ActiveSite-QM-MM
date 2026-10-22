"""ActiveSite — QM region proposal for Mg-dependent phosphodiester cleavage.

Every atom that enters the QM region is tied to a ``Choice`` carrying the
numeric evidence (distances in Å, angles in degrees, charges) that justified
it, so the Explainer can cite the number instead of a slogan. Nothing here
runs a chemistry binary; it is geometry over ``MolSystem``.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Set, Tuple

from activesite.chem.system import ChargeReport, MolSystem

FIRST_SHELL = 2.8          # Å, heavy atoms coordinating the metal
NUCLEOPHILE_SEARCH = 4.0   # Å, water O to scissile P
GENERAL_BASE_SEARCH = 6.0  # Å, His ring N to nucleophile O
MAX_CHARGE_FRACTION = 0.10

BACKBONE_ATOMS = frozenset({"N", "H", "CA", "HA", "C", "O", "H1", "H2", "H3", "OXT"})
PHOSPHATE_GROUP = ("P", "OP1", "OP2", "O5'", "C5'", "H5'", "H5''")
MINIMAL_LEAVING_ATOMS = ("C3'", "H3'", "O3'")
WATER_NAMES = frozenset({"WAT", "HOH", "TIP3", "SOL"})
HIS_NAMES = frozenset({"HIS", "HIE", "HID", "HIP"})
HIS_RING_N = ("ND1", "NE2")

CUT_LEVELS: Tuple[str, ...] = ("minimal", "sugar")


@dataclass(frozen=True)
class Choice:
    """One justified inclusion in the QM region."""

    residue: str                 # e.g. "ASN322"
    role: str                    # metal | first_shell | scissile_phosphate | leaving_group | nucleophile | general_base
    rule: str                    # human-readable rule that fired
    evidence: Dict[str, object]  # numeric evidence (Å, degrees, e) the Explainer can cite


@dataclass
class Proposal:
    atoms: List[int]
    mask: str
    cut_level: str
    choices: List[Choice]
    charge: ChargeReport
    notes: List[str] = field(default_factory=list)


# ---------------------------------------------------------------- residue kinds
def residue_kind(res) -> str:
    names = {a.name for a in res.atoms}
    if res.name in WATER_NAMES or (len(res.atoms) == 3 and "O" in names):
        return "water"
    if {"N", "CA", "C"} <= names:
        return "protein"
    if "P" in names or {"C3'", "O3'"} <= names:
        return "nucleic"
    if len(res.atoms) == 1:
        return "ion"
    return "other"


def side_chain(res) -> List[int]:
    """Side-chain atom indices (backbone N, H, CA, HA, C, O stay in MM; cut is CA-CB)."""
    return [a.idx for a in res.atoms if a.name not in BACKBONE_ATOMS]


def _r(x: float, nd: int = 3) -> float:
    return round(float(x), nd)


# ------------------------------------------------------------------- proposal
def propose(sys: MolSystem, metal_resid: int, cut_level: str = "auto") -> Proposal:
    """Propose a QM region around the metal in residue ``metal_resid`` (1-based)."""
    s = sys.s
    choices: List[Choice] = []
    notes: List[str] = []
    core: Set[int] = set()

    # 1. metal
    metal_res = s.residues[metal_resid - 1]
    if residue_kind(metal_res) != "ion":
        raise ValueError(f"Residue {sys.res_label(metal_resid - 1)} is not a single-atom ion.")
    metal = metal_res.atoms[0].idx
    core.add(metal)
    choices.append(Choice(
        residue=sys.res_label(metal_res.idx), role="metal",
        rule="named in the request",
        evidence={"resid": metal_resid, "atomic_number": int(s.atoms[metal].atomic_number),
                  "mm_charge": _r(s.atoms[metal].charge)},
    ))

    # 2. first shell
    shell_atoms = [j for j in sys.within(metal, FIRST_SHELL) if s.atoms[j].atomic_number > 1]
    shell_by_res: Dict[int, List[int]] = {}
    for j in shell_atoms:
        shell_by_res.setdefault(s.atoms[j].residue.idx, []).append(j)
    for ridx, js in shell_by_res.items():
        res = s.residues[ridx]
        kind = residue_kind(res)
        ev = {sys.label(j).split("@")[1] + "_dist": _r(sys.dist(metal, j)) for j in js}
        ev["cutoff"] = FIRST_SHELL
        if kind == "water":
            core.update(a.idx for a in res.atoms)
            rule = "whole water within FIRST_SHELL of the metal"
        elif kind == "protein":
            core.update(side_chain(res))
            rule = "side chain of a protein residue coordinating the metal (cut CA-CB)"
        else:
            rule = "coordinating nucleic-acid atoms; atoms assigned by the scissile-phosphate cut level"
        choices.append(Choice(residue=sys.res_label(ridx), role="first_shell", rule=rule, evidence=ev))

    # 3. scissile phosphate and leaving group
    p_candidates = [j for j in sys.within(metal, 8.0) if s.atoms[j].name == "P"]
    if not p_candidates:
        raise ValueError(f"No phosphorus within 8 Å of {sys.res_label(metal_res.idx)}.")
    p_atom = p_candidates[0]
    p_res = s.atoms[p_atom].residue
    o3_partner = next(
        (b for b in s.atoms[p_atom].bond_partners
         if b.name == "O3'" and b.residue.idx != p_res.idx), None)
    if o3_partner is None:
        raise ValueError(f"{sys.label(p_atom)} has no inter-residue O3' partner; not a phosphodiester.")
    leaving_res = o3_partner.residue
    choices.append(Choice(
        residue=sys.res_label(p_res.idx), role="scissile_phosphate",
        rule="P nearest the metal",
        evidence={"metal_P_dist": _r(sys.dist(metal, p_atom)),
                  "P_O3prime_dist": _r(sys.dist(p_atom, o3_partner.idx)),
                  "other_P_within_8A": [(sys.label(j), _r(sys.dist(metal, j))) for j in p_candidates[1:]]},
    ))
    choices.append(Choice(
        residue=sys.res_label(leaving_res.idx), role="leaving_group",
        rule="residue donating the O3' bonded to the scissile P",
        evidence={"metal_O3prime_dist": _r(sys.dist(metal, o3_partner.idx)),
                  "P_O3prime_dist": _r(sys.dist(p_atom, o3_partner.idx))},
    ))

    # 4. nucleophile
    waters = [j for j in sys.within(p_atom, NUCLEOPHILE_SEARCH)
              if s.atoms[j].name == "O" and residue_kind(s.atoms[j].residue) == "water"]
    scored = sorted(
        ((sys.angle(j, p_atom, o3_partner.idx), sys.dist(j, p_atom), j) for j in waters),
        reverse=True,
    )
    nucleophile_o: Optional[int] = None
    if scored:
        angle, dist, nucleophile_o = scored[0]
        nuc_res = s.atoms[nucleophile_o].residue
        core.update(a.idx for a in nuc_res.atoms)
        choices.append(Choice(
            residue=sys.res_label(nuc_res.idx), role="nucleophile",
            rule="water O within 4.0 Å of P with the largest O(w)-P-O3' angle (in-line attack)",
            evidence={"Ow_P_O3prime_angle": _r(angle, 1), "Ow_P_dist": _r(dist),
                      "search_radius": NUCLEOPHILE_SEARCH,
                      "rejected": [(sys.label(j), _r(a, 1), _r(d)) for a, d, j in scored[1:]]},
        ))
    else:
        notes.append(f"No water O within {NUCLEOPHILE_SEARCH} Å of {sys.label(p_atom)}; no nucleophile chosen.")

    # 5. general base
    if nucleophile_o is not None:
        ring_n = [j for j in sys.within(nucleophile_o, GENERAL_BASE_SEARCH)
                  if s.atoms[j].residue.name in HIS_NAMES and s.atoms[j].name in HIS_RING_N]
        if ring_n:
            n_atom = ring_n[0]
            his_res = s.atoms[n_atom].residue
            core.update(side_chain(his_res))
            choices.append(Choice(
                residue=sys.res_label(his_res.idx), role="general_base",
                rule="His ring N nearest the nucleophile O within 6.0 Å (side chain, cut CA-CB)",
                evidence={"N_Ow_dist": _r(sys.dist(n_atom, nucleophile_o)), "atom": s.atoms[n_atom].name,
                          "search_radius": GENERAL_BASE_SEARCH,
                          "rejected": [(sys.label(j), _r(sys.dist(j, nucleophile_o))) for j in ring_n[1:]]},
            ))
        else:
            notes.append(f"No His ring N within {GENERAL_BASE_SEARCH} Å of {sys.label(nucleophile_o)}; no general base chosen.")

    # cut levels, smallest first
    levels = CUT_LEVELS if cut_level == "auto" else (cut_level,)
    if any(lv not in CUT_LEVELS for lv in levels):
        raise ValueError(f"Unknown cut_level {cut_level!r}; expected one of {CUT_LEVELS} or 'auto'.")

    last: Optional[Tuple[str, List[int], ChargeReport]] = None
    for level in levels:
        atoms = sorted(core | set(_cut_level_atoms(sys, level, p_res, leaving_res)))
        charge = sys.charge_report(atoms)
        rings = sys.ring_bonds_cut(atoms)
        last = (level, atoms, charge)
        reasons = []
        if charge.fraction > MAX_CHARGE_FRACTION:
            reasons.append(f"charge fraction {charge.fraction:.3f} > {MAX_CHARGE_FRACTION:.2f} (mm_sum {charge.mm_sum:+.3f})")
        if rings:
            reasons.append("ring bonds cut: " + ", ".join(rings))
        if reasons:
            notes.append(f"{level} rejected: " + "; ".join(reasons))
            continue
        notes.append(f"{level} accepted: charge fraction {charge.fraction:.3f} <= {MAX_CHARGE_FRACTION:.2f}, "
                     f"no ring bonds cut, {charge.link_atoms} link atoms")
        break
    else:
        notes.append(f"all cut levels rejected; returning the last level '{last[0]}' unchanged")

    level, atoms, charge = last
    return Proposal(
        atoms=atoms, mask=MolSystem.atom_mask(atoms), cut_level=level,
        choices=choices, charge=charge, notes=notes,
    )


def _cut_level_atoms(sys: MolSystem, level: str, scissile_res, leaving_res) -> List[int]:
    phosphate = [a.idx for a in scissile_res.atoms if a.name in PHOSPHATE_GROUP]
    if level == "minimal":
        leaving = [a.idx for a in leaving_res.atoms if a.name in MINIMAL_LEAVING_ATOMS]
    elif level == "sugar":
        leaving = [a.idx for a in leaving_res.atoms if a.name not in PHOSPHATE_GROUP]
    else:
        raise ValueError(level)
    return phosphate + leaving


# -------------------------------------------------------------------- compare
def compare(sys: MolSystem, ours: Sequence[int], expert: Sequence[int]) -> Dict[str, object]:
    """Atom- and residue-level agreement between two QM selections."""
    a, b = set(int(i) for i in ours), set(int(i) for i in expert)
    shared = a & b
    union = a | b
    res = lambda idxs: sorted({sys.res_label(sys.atoms[i].residue.idx) for i in idxs})  # noqa: E731
    return {
        "atom_jaccard": (len(shared) / len(union)) if union else 1.0,
        "ours_atoms": len(a),
        "expert_atoms": len(b),
        "shared_atoms": len(shared),
        "residues_ours": res(a),
        "residues_expert": res(b),
        "only_ours": sorted(sys.label(i) for i in a - b),
        "only_expert": sorted(sys.label(i) for i in b - a),
    }
