"""ActiveSite — Chemistry Runner.

Turns a ``QMMMPartition`` into one sander QM/MM single point executed inside
the engine container (``activesite.chem.sander``) and maps the parsed output
onto ``SimulationResult``. There is no placeholder energy path: when the
engine does not run, ``success`` is False, both energies are ``None`` and
``error_message`` says why.
"""
from __future__ import annotations

import logging
import os
import time
from pathlib import Path
from typing import Optional

from activesite.chem import sander
from activesite.models import (
    AlternativeChoice,
    DecisionCard,
    DecisionCategory,
    QMMMPartition,
    SimulationResult,
)

logger = logging.getLogger(__name__)

# Unit conversion: 1 Hartree = 627.509 kcal/mol (CODATA, rounded).
HARTREE_TO_KCAL_MOL = 627.509

ENGINE_SKIPPED_SAMPLE_MODE = "engine not run: SAMPLE_MODE=true (set SAMPLE_MODE=false or pass --docker on a Docker host)"
ENGINE_SKIPPED_NO_DOCKER = f"engine not run: Docker or the {sander.ENGINE_IMAGE} image is not available"
ENGINE_SKIPPED_NO_TOPOLOGY = "engine not run: no Amber topology (.parm7/.prmtop) for this system yet"

AMBER_TOPOLOGY_SUFFIXES = (".parm7", ".prmtop", ".top")


class ChemistryRunner:
    """Runs one PM6 (or other allow-listed theory) single point through the engine container."""

    def __init__(
        self,
        docker_image: str = sander.ENGINE_IMAGE,
        sample_mode: Optional[bool] = None,
        timeout_s: int = 300,
    ):
        self.docker_image = docker_image
        self.timeout_s = timeout_s
        if sample_mode is not None:
            self.sample_mode = sample_mode
        else:
            env_sample = os.getenv("SAMPLE_MODE", "true").lower()
            self.sample_mode = env_sample in ("true", "1", "yes")

    @staticmethod
    def sanitize_mask(mask: str) -> str:
        """Collapse ',:' into ',' (``:1,:769`` -> ``:1,769``); the engine allow-list does the rest."""
        return (mask or ":1").replace(",:", ",")

    @staticmethod
    def solvent_for(parm7: Path) -> str:
        """PME when the topology carries box dimensions, otherwise GB."""
        try:
            with open(parm7, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    if line.startswith("%FLAG BOX_DIMENSIONS"):
                        return "pme"
        except OSError:
            pass
        return "gb"

    def build_theory_card(self, partition: QMMMPartition, qm_theory: str) -> DecisionCard:
        """Track 02 Decision Card justifying the QM Hamiltonian choice."""
        return DecisionCard(
            decision_id=f"DEC_THEORY_{qm_theory}",
            category=DecisionCategory.THEORY_SELECTION,
            target=f"QM Hamiltonian for {partition.system_name}",
            choice=f"Selected {qm_theory} semi-empirical method",
            alternatives=[
                AlternativeChoice(
                    name="DFT (B3LYP/def2-TZVP)",
                    rejected_reason="Requires GPU cluster or hours of compute; impractical for rapid interactive drug design.",
                ),
                AlternativeChoice(
                    name="Classical MM without QM",
                    rejected_reason="Fixed point charges cannot model chemical bond polarization, charge transfer, or orbital hybridization.",
                ),
            ],
            rationale=(
                f"{qm_theory} includes parameterized core-core repulsions and NDDO integral approximations, "
                f"giving qualitative active-site electronic polarization at a cost of seconds on ordinary CPU."
            ),
            confidence=0.96,
            evidence={
                "qm_theory": qm_theory,
                "qm_residues": len(partition.qm_residues),
                "total_qm_charge": partition.qm_charge,
            },
        )

    def run_simulation(
        self,
        partition: QMMMPartition,
        prmtop_path: str | Path,
        inpcrd_path: str | Path,
        output_dir: Optional[str | Path] = None,
        qm_theory: str = "PM6",
        min_steps: int = 1,
    ) -> SimulationResult:
        """Run one single point in the engine container, or say honestly why it did not run.

        ``min_steps`` is accepted for API compatibility; only single points are implemented.
        """
        start = time.time()
        out_dir = Path(output_dir or "data/runs") / partition.system_name
        cards = list(partition.decision_cards) + [self.build_theory_card(partition, qm_theory)]
        prmtop = Path(prmtop_path)
        coords = Path(inpcrd_path)

        def skipped(reason: str) -> SimulationResult:
            logger.info("%s (%s)", reason, partition.system_name)
            return SimulationResult(
                success=False, system_name=partition.system_name, qm_theory=qm_theory,
                energy_hartree=None, energy_kcal_mol=None, sample_mode=self.sample_mode,
                execution_time_seconds=round(time.time() - start, 3),
                stdout_summary=reason, error_message=reason, decision_cards=cards,
            )

        if self.sample_mode:
            return skipped(ENGINE_SKIPPED_SAMPLE_MODE)
        if prmtop.suffix.lower() not in AMBER_TOPOLOGY_SUFFIXES:
            return skipped(ENGINE_SKIPPED_NO_TOPOLOGY)
        if not sander.docker_available(self.docker_image):
            return skipped(ENGINE_SKIPPED_NO_DOCKER)

        try:
            engine = sander.run_single_point(
                parm7=prmtop, coords=coords, mask=self.sanitize_mask(partition.amber_qmmask),
                charge=int(partition.qm_charge), workdir=out_dir, theory=qm_theory,
                timeout_s=self.timeout_s, solvent=self.solvent_for(prmtop), image=self.docker_image,
            )
        except (ValueError, FileNotFoundError) as exc:
            return skipped(f"engine not run: {exc}")

        exec_time = round(time.time() - start, 3)
        total = engine.get("total_energy_kcal")
        ok = bool(engine.get("ok")) and total is not None
        outputs = {"mdin": str(out_dir / "sp.mdin")}
        if engine.get("mdout"):
            outputs["mdout"] = engine["mdout"]
        if ok:
            summary = (
                f"sander {qm_theory} single point finished in {engine.get('wall_time_s')}s: "
                f"E(QM/MM) = {total:.4f} kcal/mol, {qm_theory}ESCF = {engine['qm_escf_kcal']:.4f} kcal/mol, "
                f"{engine.get('link_atoms')} link atoms."
            )
            error = None
        else:
            errors = engine.get("errors") or ["sander produced no QM energy"]
            summary = "sander did not produce a QM energy: " + " | ".join(errors)
            error = summary
        return SimulationResult(
            success=ok, system_name=partition.system_name, qm_theory=qm_theory,
            energy_kcal_mol=total if ok else None,
            energy_hartree=(total / HARTREE_TO_KCAL_MOL) if ok else None,
            sample_mode=False, execution_time_seconds=exec_time,
            stdout_summary=summary, error_message=error, decision_cards=cards,
            output_files=outputs, engine="sander in Docker", engine_output=engine,
        )
