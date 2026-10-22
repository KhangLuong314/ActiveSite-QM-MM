"""ActiveSite — legacy radius-based pipeline (ligand cases only).

Kept for the EGFR/ABL ligand cases until the P4 preparation is wired into the
retry loop. Metal cases go through ``activesite.agent.orchestrator.run_case``.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Callable, Dict, Generator, List, Optional
from pydantic import BaseModel, Field

from activesite.adapters.scout import DataScout
from activesite.agent.critic import CriticAgent
from activesite.agent.explainer import ExplainerAgent
from activesite.agent.planner import ExecutionPlan, PlannerAgent
from activesite.chem.chimerax import ChimeraXGenerator
from activesite.chem.partitioning import QMMMPartitioner
from activesite.chem.protonation import ProtonationAgent
from activesite.chem.runner import ChemistryRunner
from activesite.memory.meterless import MeterlessHMEM
from activesite.models import DecisionCard, QMMMPartition, SimulationResult

logger = logging.getLogger(__name__)


class WorkflowOutput(BaseModel):
    success: bool
    system_name: str
    plan: ExecutionPlan
    partition: QMMMPartition
    result: SimulationResult
    decision_cards: List[DecisionCard] = Field(default_factory=list)
    chimerax_script_path: Optional[str] = None
    report_markdown: str = ""
    logs: List[str] = Field(default_factory=list)


class LegacyPipeline:
    """Master workflow orchestrator executing the end-to-end Track 02 pipeline."""

    def __init__(
        self,
        hmem: Optional[MeterlessHMEM] = None,
        sample_mode: Optional[bool] = None,
    ):
        self.hmem = hmem or MeterlessHMEM()
        self.scout = DataScout()
        self.planner = PlannerAgent()
        self.protonation_agent = ProtonationAgent()
        self.partitioner = QMMMPartitioner(self.protonation_agent)
        self.critic = CriticAgent(self.hmem)
        self.runner = ChemistryRunner(sample_mode=sample_mode)
        self.chimerax = ChimeraXGenerator()
        self.explainer = ExplainerAgent()

    def run_case(
        self, case_id: str, on_event: Optional[Callable[[str, str], None]] = None
    ) -> WorkflowOutput:
        """Execute a predefined benchmark case by ID."""
        case_dict = self.scout.load_benchmark_case(case_id)
        plan = self.planner.plan_from_case(case_dict)
        return self._execute_plan(plan, on_event=on_event)

    def run_query(
        self, query: str, on_event: Optional[Callable[[str, str], None]] = None
    ) -> WorkflowOutput:
        """Execute a conversational natural language simulation request."""
        plan = self.planner.plan_from_prompt(query)
        return self._execute_plan(plan, on_event=on_event)

    def _notify(
        self, on_event: Optional[Callable[[str, str], None]], stage: str, message: str, logs: List[str]
    ) -> None:
        log_entry = f"[{stage.upper()}] {message}"
        logs.append(log_entry)
        if on_event:
            try:
                on_event(stage, message)
            except Exception:
                pass

    def _execute_plan(
        self, plan: ExecutionPlan, on_event: Optional[Callable[[str, str], None]] = None
    ) -> WorkflowOutput:
        logs: List[str] = []

        # 1. Scout Structure
        self._notify(on_event, "scout", f"Scouting structure for system {plan.system_name}...", logs)
        structure_path: Optional[Path] = None

        if plan.parm7_path:
            structure_path = Path(plan.parm7_path)
        elif plan.pdb_id:
            try:
                meta = self.scout.resolve_pdb(plan.pdb_id)
                structure_path = Path(meta.local_pdb_path) if meta.local_pdb_path else None
                self._notify(on_event, "scout", f"Resolved PDB {plan.pdb_id} ({meta.title[:40]}...)", logs)
            except Exception as exc:
                self._notify(on_event, "scout", f"PDB lookup fallback: {exc}", logs)

        if not structure_path or not structure_path.exists():
            # Check default case references
            if plan.system_name == "egfr_erlotinib":
                structure_path = Path("data/reference/egfr/1m17.pdb")
            elif plan.system_name == "abl_imatinib":
                structure_path = Path("data/reference/abl/2hyy.pdb")
            elif "ippoi" in plan.system_name:
                structure_path = Path("data/reference/qmmm_dft/step3_pbcsetup.parm7")
            else:
                raise FileNotFoundError(f"Could not locate structure file for {plan.system_name}")

        # 2. Partition Active Site & Link Atoms
        self._notify(
            on_event,
            "partition",
            f"Partitioning active site (cutoff {plan.cutoff_radius:.1f} A, pH {plan.ph:.1f})...",
            logs,
        )

        if plan.metal_resid is not None or "ippoi" in plan.system_name:
            metal_resid = plan.metal_resid or 371
            coords = plan.coords_path or "data/reference/qmmm_dft/prod00.ncrst"
            partition = self.partitioner.partition_metal_system(
                parm7_path=structure_path,
                coords_path=coords,
                metal_resid=metal_resid,
                cutoff_radius=plan.cutoff_radius,
                ph=plan.ph,
            )
        else:
            ligand_name = plan.ligand_name or "AQ4"
            partition = self.partitioner.partition_ligand_system(
                pdb_path=structure_path,
                ligand_resname=ligand_name,
                cutoff_radius=plan.cutoff_radius,
                ph=plan.ph,
                literature_contacts=plan.literature_contacts,
                expected_absent=plan.expected_absent,
            )

        self._notify(
            on_event,
            "partition",
            f"Selected {len(partition.qm_residues)} QM residues and placed {len(partition.link_atoms)} link atoms.",
            logs,
        )

        # 3. Critic Verification & Self-Correction
        self._notify(
            on_event,
            "critic",
            "Critic inspecting electron parity, spin multiplicity, and boundary cuts...",
            logs,
        )
        report = self.critic.inspect_and_correct(partition, qm_theory=plan.qm_theory)
        if report.corrections_applied:
            for corr in report.corrections_applied:
                self._notify(on_event, "critic_correction", f"Applied self-correction: {corr}", logs)
        else:
            self._notify(
                on_event,
                "critic",
                f"Verified: Closed-shell singlet ({report.electron_count} valence electrons, qmcharge={partition.qm_charge:+d}).",
                logs,
            )

        # 4. Chemistry runner (input generation; engine execution is a later module)
        self._notify(
            on_event,
            "runner",
            f"Running {plan.qm_theory} QM/MM single point (sander inside the activesite-engine:at26 container)...",
            logs,
        )
        coords_arg = plan.coords_path or structure_path
        sim_result = self.runner.run_simulation(
            partition=partition,
            prmtop_path=structure_path,
            inpcrd_path=coords_arg,
            qm_theory=plan.qm_theory,
            min_steps=plan.min_steps,
        )
        if sim_result.success and sim_result.energy_kcal_mol is not None and sim_result.energy_hartree is not None:
            runner_msg = (
                f"Calculation finished: E = {sim_result.energy_kcal_mol:,.2f} kcal/mol "
                f"({sim_result.energy_hartree:.5f} Ha) in {sim_result.execution_time_seconds:.3f}s."
            )
        else:
            runner_msg = (
                f"No energy computed: {sim_result.error_message or 'engine did not run'} "
                f"(Amber input written: {sim_result.output_files.get('mdin', 'n/a')})."
            )
        self._notify(on_event, "runner", runner_msg, logs)

        # 5. Generate ChimeraX Script
        cxc_path = Path("data/runs") / partition.system_name / "visualize.cxc"
        self.chimerax.generate_script(partition, structure_path, output_script_path=cxc_path)
        self._notify(on_event, "viz", f"Generated ChimeraX 3D script at {cxc_path}", logs)

        # 6. Explainer Report
        self._notify(on_event, "explainer", "Compiling Track 02 Decision Cards and explanation report...", logs)
        all_cards = sim_result.decision_cards or partition.decision_cards
        report_md = self.explainer.generate_report(
            system_name=plan.system_name,
            result=sim_result,
            partition=partition,
            chimerax_script_path=str(cxc_path),
        )

        return WorkflowOutput(
            success=sim_result.success,
            system_name=plan.system_name,
            plan=plan,
            partition=partition,
            result=sim_result,
            decision_cards=all_cards,
            chimerax_script_path=str(cxc_path),
            report_markdown=report_md,
            logs=logs,
        )
