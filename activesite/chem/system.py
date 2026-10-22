"""ActiveSite — geometry and charge layer over parmed for Amber systems.

Pure functions over an in-memory ``parmed.Structure``: labels, Amber-mask
selection, distances/angles, neighbour search, QM-region charge accounting and
ring-bond detection at the QM/MM boundary. No chemistry binaries, no I/O at
import time, no module-level state beyond constants.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Sequence, Set

import numpy as np
import parmed as pmd
from parmed.amber import AmberMask

# Atomic numbers for the elements that appear in the benchmark systems.
ATOMIC_Z = {
    "H": 1,
    "C": 6,
    "N": 7,
    "O": 8,
    "P": 15,
    "S": 16,
    "Mg": 12,
    "Zn": 30,
    "Na": 11,
    "Cl": 17,
    "K": 19,
}


@dataclass(frozen=True)
class ChargeReport:
    """Charge accounting for a QM atom selection.

    mm_sum:      sum of the MM partial charges over the QM atoms.
    nearest_int: ``round(mm_sum)``, the integer charge the force field implies.
    fraction:    ``|mm_sum - nearest_int|``; large values mean the cut splits a charge group.
    electrons:   total electrons in the QM region, ``sum(Z) - nearest_int``.
    link_atoms:  number of bonds with exactly one end inside the QM region.
    """

    mm_sum: float
    nearest_int: int
    fraction: float
    electrons: int
    link_atoms: int


class MolSystem:
    """Topology + coordinates of an Amber system with geometry and charge helpers."""

    def __init__(self, parm7: Path | str, coords: Path | str):
        self._init_from_structure(pmd.load_file(str(parm7), str(coords)))

    @classmethod
    def from_structure(cls, structure: pmd.Structure) -> "MolSystem":
        """Build a MolSystem from an in-memory Structure (used by tests and prep code)."""
        obj = cls.__new__(cls)
        obj._init_from_structure(structure)
        return obj

    def _init_from_structure(self, structure: pmd.Structure) -> None:
        if structure.coordinates is None:
            raise ValueError("Structure has no coordinates; a coordinate file is required.")
        self.s = structure
        self.atoms = structure.atoms
        self.xyz = np.asarray(structure.coordinates, dtype=float).reshape(-1, 3)
        if len(self.xyz) != len(self.atoms):
            raise ValueError(
                f"Coordinate count {len(self.xyz)} does not match atom count {len(self.atoms)}."
            )

    # ------------------------------------------------------------------ labels
    def label(self, i: int) -> str:
        """``RESNAME<resid 1-based>@ATOMNAME`` for atom index ``i`` (0-based)."""
        a = self.atoms[i]
        return f"{a.residue.name}{a.residue.idx + 1}@{a.name}"

    def res_label(self, ridx: int) -> str:
        """``RESNAME<ridx+1>`` for residue index ``ridx`` (0-based)."""
        return f"{self.s.residues[ridx].name}{ridx + 1}"

    # --------------------------------------------------------------- selection
    def select(self, mask: str) -> List[int]:
        """Atom indices (0-based) matching an Amber mask such as ``:371`` or ``@CA``."""
        selection = AmberMask(self.s, mask).Selection()
        return [i for i, flag in enumerate(selection) if flag]

    # ---------------------------------------------------------------- geometry
    def dist(self, i: int, j: int) -> float:
        """Distance between atoms ``i`` and ``j`` in Å (no periodic imaging)."""
        return float(np.linalg.norm(self.xyz[i] - self.xyz[j]))

    def angle(self, i: int, j: int, k: int) -> float:
        """Angle i-j-k in degrees, vertex at ``j``."""
        v1 = self.xyz[i] - self.xyz[j]
        v2 = self.xyz[k] - self.xyz[j]
        n1 = np.linalg.norm(v1)
        n2 = np.linalg.norm(v2)
        if n1 == 0.0 or n2 == 0.0:
            raise ValueError("Angle undefined: coincident atoms.")
        cos_theta = float(np.dot(v1, v2) / (n1 * n2))
        return float(np.degrees(np.arccos(np.clip(cos_theta, -1.0, 1.0))))

    def within(self, i: int, cutoff: float) -> List[int]:
        """Indices of atoms within ``cutoff`` Å of atom ``i``, nearest first, excluding ``i``."""
        d = np.linalg.norm(self.xyz - self.xyz[i], axis=1)
        d[i] = np.inf
        hits = np.flatnonzero(d <= cutoff)
        order = np.argsort(d[hits], kind="stable")
        return [int(x) for x in hits[order]]

    # ------------------------------------------------------------------ charge
    def _boundary_bonds(self, qm_set: Set[int]):
        """Bonds with exactly one end in ``qm_set``."""
        for b in self.s.bonds:
            a1, a2 = b.atom1.idx, b.atom2.idx
            if (a1 in qm_set) != (a2 in qm_set):
                yield b

    def charge_report(self, qm: Sequence[int]) -> ChargeReport:
        """Charge and electron accounting for the QM atoms ``qm`` (0-based indices)."""
        qm_set = set(int(i) for i in qm)
        mm_sum = float(sum(self.atoms[i].charge for i in qm_set))
        nearest_int = int(round(mm_sum))
        fraction = abs(mm_sum - nearest_int)
        z_total = sum(self._atomic_number(i) for i in qm_set)
        electrons = int(z_total - nearest_int)
        link_atoms = sum(1 for _ in self._boundary_bonds(qm_set))
        return ChargeReport(
            mm_sum=mm_sum,
            nearest_int=nearest_int,
            fraction=fraction,
            electrons=electrons,
            link_atoms=link_atoms,
        )

    def _atomic_number(self, i: int) -> int:
        a = self.atoms[i]
        z = int(getattr(a, "atomic_number", 0) or 0)
        if z > 0:
            return z
        # Fall back to the element symbol when the topology carries no atomic number.
        element = getattr(a, "element_name", None) or a.name[:1]
        try:
            return ATOMIC_Z[element.capitalize()]
        except KeyError as exc:
            raise ValueError(f"Unknown element for atom {self.label(i)}") from exc

    # ------------------------------------------------------------------- rings
    def ring_bonds_cut(self, qm: Sequence[int]) -> List[str]:
        """Boundary bonds inside one residue that are part of a ring.

        A boundary bond (one end in ``qm``) whose two atoms belong to the same
        residue is a ring bond if the atoms remain connected through that
        residue's bond graph after the bond is removed. Cutting such a bond
        with a link atom is unphysical, so the caller should move the boundary.
        Returned as ``"<label(i)>-<name(j)>"`` with ``i`` the QM-side atom.
        """
        qm_set = set(int(i) for i in qm)
        cut: List[str] = []
        for b in self._boundary_bonds(qm_set):
            a1, a2 = b.atom1, b.atom2
            if a1.residue.idx != a2.residue.idx:
                continue
            qm_atom, mm_atom = (a1, a2) if a1.idx in qm_set else (a2, a1)
            if self._connected_within_residue(qm_atom.idx, mm_atom.idx, a1.residue.idx):
                cut.append(f"{self.label(qm_atom.idx)}-{mm_atom.name}")
        return cut

    def _connected_within_residue(self, start: int, goal: int, ridx: int) -> bool:
        """BFS from ``start`` to ``goal`` over the residue's bonds, skipping the start-goal bond."""
        residue_atoms = {a.idx for a in self.s.residues[ridx].atoms}
        seen = {start}
        queue = deque([start])
        while queue:
            cur = queue.popleft()
            for partner in self.atoms[cur].bond_partners:
                p = partner.idx
                if p not in residue_atoms or p in seen:
                    continue
                if cur == start and p == goal:
                    continue  # the bond under test
                if p == goal:
                    return True
                seen.add(p)
                queue.append(p)
        return False

    # -------------------------------------------------------------------- mask
    @staticmethod
    def atom_mask(indices: Iterable[int]) -> str:
        """Compact 1-based Amber atom mask, e.g. ``[0,1,2,8,11,12,13] -> "@1-3,9,12-14"``."""
        ids = sorted({int(i) + 1 for i in indices})
        if not ids:
            return ""
        parts: List[str] = []
        start = prev = ids[0]
        for n in ids[1:]:
            if n == prev + 1:
                prev = n
                continue
            parts.append(f"{start}-{prev}" if start != prev else f"{start}")
            start = prev = n
        parts.append(f"{start}-{prev}" if start != prev else f"{start}")
        return "@" + ",".join(parts)
