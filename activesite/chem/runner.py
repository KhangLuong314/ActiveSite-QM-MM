"""ActiveSite — Chemistry Runner (Amber QM/MM input generation).

Generates Amber ``sander`` ``&qmmm`` input files and the THEORY_SELECTION
Decision Card. Execution of chemistry binaries belongs to a separate engine
module that runs only inside Docker (see AGENTS.md rule 3). That module does
not exist yet, so ``run_simulation`` returns an honest failure with null
energies rather than a synthesized number.
"""
from __future__ import annotations

import logging
import os
import time
from pathlib import Path
from typing import Optional

from activesite.models import (
    AlternativeChoice,
    DecisionCard,
    DecisionCategory,
    QMMMPartition,
    SimulationResult,
)

logger = logging.getLogger(__name__)

ENGINE_NOT_IMPLEMENTED = "engine not implemented yet"

# Unit conversion: 1 Hartree = 627.509 kcal/mol (CODATA, rounded).
HARTREE_TO_KCAL_MOL = 627.509


class ChemistryRunner:
    """Manages Amber QM/MM input generation and (future) simulation execution."""

    def __init__(
        self,
        docker_image: str = "activesite-engine:at26",
        sample_mode: Optional[bool] = None,
    ):
        self.docker_image = docker_image
        if sample_mode is not None:
            self.sample_mode = sample_mode
        else:
            env_sample = os.getenv("SAMPLE_MODE", "true").lower()
            self.sample_mode = env_sample in ("true", "1", "yes")

    def generate_amber_mdin(
        self,
        partition: QMMMPartition,
        qm_theory: str = "PM6",
        min_steps: int = 500,
        qmcut: float = 10.0,
    ) -> str:
        """Generate an Amber sander QM/MM input file (mdin)."""
        qmmask_str = (partition.amber_qmmask or ":1").replace(",:", ",")
        # Amber PM6 is restricted Hartree–Fock only; spin must be 1 (closed-shell singlet).
        spin = 1 if str(qm_theory).upper() == "PM6" else partition.spin_multiplicity

        mdin_content = f"""ActiveSite Automated QM/MM Simulation ({partition.system_name})
 &cntrl
    imin=1,               ! Minimization
    maxcyc={min_steps},   ! Maximum minimization cycles
    ncyc=100,             ! Steepest descent then conjugate gradient
    cut=10.0,             ! Classical nonbonded cutoff (Angstroms)
    ntpr=50,              ! Print energy every 50 steps
    ntb=0,                ! Non-periodic calculation
    ifqnt=1               ! Turn on QM/MM coupling
 /
 &qmmm
    qmmask='{qmmask_str}',
    qm_theory='{qm_theory}',
    qmcharge={partition.qm_charge},
    spin={spin},
    qmcut={qmcut:.1f},
    writepdb=1,
    qmmm_switch=1
 /
"""
        return mdin_content

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
        min_steps: int = 500,
    ) -> SimulationResult:
        """Write the Amber input and report that no engine ran.

        The Docker engine module is a later deliverable. Until it exists this
        method never produces an energy: ``success`` is False and both energy
        fields are ``None`` so every downstream renderer says so explicitly.
        """
        start_time = time.time()
        out_dir = Path(output_dir or "data/runs") / partition.system_name
        out_dir.mkdir(parents=True, exist_ok=True)

        mdin_path = out_dir / "qmmm.mdin"
        mdin_str = self.generate_amber_mdin(
            partition, qm_theory=qm_theory, min_steps=min_steps
        )
        with open(mdin_path, "w", encoding="utf-8") as f:
            f.write(mdin_str)

        all_decision_cards = list(partition.decision_cards)
        all_decision_cards.append(self.build_theory_card(partition, qm_theory))

        exec_time = time.time() - start_time
        logger.info(
            "Wrote %s for %s; no engine available (%s).",
            mdin_path, partition.system_name, ENGINE_NOT_IMPLEMENTED,
        )
        return SimulationResult(
            success=False,
            system_name=partition.system_name,
            qm_theory=qm_theory,
            energy_hartree=None,
            energy_kcal_mol=None,
            sample_mode=self.sample_mode,
            execution_time_seconds=round(exec_time, 3),
            stdout_summary=(
                f"Amber input written to {mdin_path}; no QM/MM energy computed "
                f"({ENGINE_NOT_IMPLEMENTED})."
            ),
            error_message=ENGINE_NOT_IMPLEMENTED,
            decision_cards=all_decision_cards,
            output_files={"mdin": str(mdin_path)},
        )

    @staticmethod
    def parse_sander_energy_text(mdout_text: str) -> Optional[float]:
        """Parse the final total potential energy (kcal/mol) from sander mdout text.

        Returns ``None`` when no energy line is found. Never substitutes a default.
        """
        energy: Optional[float] = None
        for line in mdout_text.splitlines():
            if "EPOT" in line or "Etot" in line:
                parts = line.split()
                for idx, part in enumerate(parts):
                    if part in ("EPOT", "Etot") and idx + 2 < len(parts) and parts[idx + 1] == "=":
                        try:
                            energy = float(parts[idx + 2])
                        except ValueError:
                            pass
        return energy

    def _parse_sander_energy(self, mdout_path: Path) -> Optional[float]:
        """Parse total QM/MM potential energy from a sander mdout file, or ``None``."""
        with open(mdout_path, "r", encoding="utf-8", errors="ignore") as f:
            return self.parse_sander_energy_text(f.read())
