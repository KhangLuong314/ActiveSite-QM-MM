"""ActiveSite — orchestrator: the retry loop for metal cases, plus a compatibility wrapper.

run_case: Planner -> DataScout -> Setup -> Critic.precheck -> Runner attempt 0 ->
Critic.diagnose -> (retry once with the fix; on success Critic.remember) ->
Critic.validate -> Explainer. Writes logs/report-<run_id>.md and
logs/cards-<run_id>.json and returns a stats dict.

``MasterOrchestrator`` keeps the old ``run_case(case_id, on_event)`` /
``run_query`` contract for the web server and CLI: metal cases go through the
loop, ligand cases through the legacy pipeline until P4 is wired in.
"""
from __future__ import annotations

import json
import os
import secrets
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from activesite.adapters.scout import DataScout as CaseLoader
from activesite.agent.core import Critic, DataScout, Explainer, NullAdapter, Planner, Runner, Setup
from activesite.agent.legacy_pipeline import LegacyPipeline, WorkflowOutput
from activesite.agent.planner import PlannerAgent
from activesite.chem.runner import HARTREE_TO_KCAL_MOL
from activesite.chem.system import MolSystem
from activesite.memory.hmem import MemoryRetrievalService, MemoryStoreService
from activesite.memory.meterless import DEFAULT_DB_PATH, DEFAULT_LEDGER_PATH, MeterlessHMEM
from activesite.models import QMMMPartition, ResidueRole, ResidueSelection, SimulationResult
from activesite.trace import Trace

__all__ = ["run_case", "new_run_id", "MasterOrchestrator", "WorkflowOutput"]


def new_run_id() -> str:
    return f"{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}-{secrets.token_hex(3)}"


def _env_sample_mode() -> bool:
    return os.getenv("SAMPLE_MODE", "true").lower() in ("true", "1", "yes")


def run_case(case: Dict[str, Any] | str, adapter: Any = None, hmem_db: Path | str | None = None,
             on_event: Optional[Callable[[Dict[str, Any]], None]] = None, *, ledger_path: Path | str | None = None,
             store: Optional[MemoryStoreService] = None, workroot: Path | str = "data/runs",
             log_dir: Path | str = "logs", llm: Any = None, sample_mode: Optional[bool] = None,
             timeout_s: int = 300, echo: bool = True) -> Dict[str, Any]:
    """Run one metal case through the retry loop and return the stats dict."""
    t0 = time.monotonic()
    if isinstance(case, str):
        case = CaseLoader().load_benchmark_case(case)
    if "metal_resid" not in case:
        raise ValueError(f"case {case.get('id')} has no metal_resid; the loop handles metal cases only")
    sample_mode = _env_sample_mode() if sample_mode is None else bool(sample_mode)
    run_id = new_run_id()
    trace = Trace(run_id, log_dir, on_event=on_event, echo=echo)
    if store is None:
        store = MemoryStoreService(hmem_db or DEFAULT_DB_PATH, ledger_path or DEFAULT_LEDGER_PATH)
    retrieval = MemoryRetrievalService(store)

    planner = Planner(llm, trace)
    plan = planner.plan(case)
    theory = plan["theory"]
    data = DataScout(adapter or NullAdapter(), trace).gather(case)

    system = MolSystem(case["parm7"], case["coords"])
    setup_agent = Setup(retrieval, trace, run_id)
    critic = Critic(store, trace, run_id)
    runner = Runner(trace, Path(workroot) / run_id, sample_mode=sample_mode, timeout_s=timeout_s)

    setup = setup_agent.build(system, case)
    checks = critic.precheck(system, case, setup, data)

    attempts: List[Dict[str, Any]] = []
    result = runner.run(case, setup, 0, theory)
    attempts.append({"attempt": 0, "setup": setup, "result": result})
    retries = 0
    memory_id: Optional[str] = None
    fix = None if result.get("ok") or result.get("skipped") else critic.diagnose(system, setup, result)
    if fix:
        attempts[0]["fix_why"] = fix["why"]
        setup = setup_agent.build(system, case, charge_override=fix["charge"],
                                  override_rule="MM partial-charge sum (Critic fix after odd-electron failure)")
        result = runner.run(case, setup, 1, theory)
        attempts.append({"attempt": 1, "setup": setup, "result": result})
        retries = 1
        if result.get("ok"):
            memory_id = critic.remember(case, attempts[0]["setup"], fix)

    validation = critic.validate(system, case, setup, data)
    explainer = Explainer(trace)
    cards = explainer.cards(system, case, setup, checks, attempts, data, validation, theory, memory_id)
    stats = {
        "run_id": run_id, "case": case.get("id"), "retries": retries, "memory_used": bool(setup["from_memory"]),
        "memory_written": memory_id, "qm_ok": bool(result.get("ok")), "qm_escf_kcal": result.get("qm_escf_kcal"),
        "total_energy_kcal": result.get("total_energy_kcal"),
        "engine_time_s": round(sum(float(a["result"].get("wall_time_s") or 0.0) for a in attempts), 2),
        "wall_time_s": None, "model_calls": planner.model_calls, "model_mode": plan["mode"],
        "trace": str(trace.path), "qmcharge": setup["charge"], "charge_rule": setup["charge_rule"],
        "mask": setup["mask"], "engine_skipped": bool(result.get("skipped")), "errors": result.get("errors") or [],
        "cut_level": setup["proposal"].cut_level, "link_atoms": setup["proposal"].charge.link_atoms,
        "checks": checks, "validation": validation, "catalog": data.get("label"), "sql": data.get("sql"),
    }
    report = explainer.report(case, run_id, stats, cards, result, validation, trace.path, setup)
    log_dir = Path(log_dir)
    (log_dir / f"report-{run_id}.md").write_text(report, encoding="utf-8")
    (log_dir / f"cards-{run_id}.json").write_text(json.dumps([c.model_dump() for c in cards], indent=2, default=str),
                                                  encoding="utf-8")
    stats["wall_time_s"] = round(time.monotonic() - t0, 2)
    stats["report"] = str(log_dir / f"report-{run_id}.md")
    stats["cards"] = str(log_dir / f"cards-{run_id}.json")
    stats["_report_markdown"] = report
    stats["_cards"] = cards
    stats["_setup"] = setup
    stats["_result"] = result
    trace.log("Orchestrator", "done", f"{case.get('id')}", f"retries {retries}, memory_used {stats['memory_used']}, qm_ok {stats['qm_ok']}",
              data={k: v for k, v in stats.items() if not k.startswith("_") and k not in ("checks", "validation", "sql")})
    return stats


class MasterOrchestrator:
    """Compatibility entry point used by the web server, the CLI and the older tests."""

    def __init__(self, hmem: Optional[MeterlessHMEM] = None, sample_mode: Optional[bool] = None, adapter: Any = None,
                 log_dir: Path | str = "logs", workroot: Path | str = "data/runs", echo: bool = False):
        self.hmem = hmem or MeterlessHMEM()
        self.sample_mode = _env_sample_mode() if sample_mode is None else bool(sample_mode)
        self.adapter = adapter
        self.log_dir = log_dir
        self.workroot = workroot
        self.echo = echo
        self.loader = CaseLoader()
        self.legacy = LegacyPipeline(hmem=self.hmem, sample_mode=self.sample_mode)
        self.last_stats: Optional[Dict[str, Any]] = None

    def run_case(self, case_id: str, on_event: Optional[Callable[[str, str], None]] = None) -> WorkflowOutput:
        case = self.loader.load_benchmark_case(case_id)
        if "metal_resid" in case:
            return self._run_loop(case, on_event)
        return self.legacy.run_case(case_id, on_event=on_event)

    def run_query(self, query: str, on_event: Optional[Callable[[str, str], None]] = None) -> WorkflowOutput:
        plan = PlannerAgent().plan_from_prompt(query)
        if plan.metal_resid is not None and "ippoi" in plan.system_name:
            case_id = "ippoi_site_b" if plan.metal_resid == 372 else "ippoi_site_a"
            return self._run_loop(self.loader.load_benchmark_case(case_id), on_event)
        return self.legacy.run_query(query, on_event=on_event)

    def _run_loop(self, case: Dict[str, Any], on_event: Optional[Callable[[str, str], None]]) -> WorkflowOutput:
        logs: List[str] = []

        def relay(entry: Dict[str, Any]) -> None:
            logs.append(f"[{entry['agent_name'].upper()}] {entry['action']}: {entry['output_summary']}")
            if on_event:
                try:
                    on_event(entry["agent_name"].lower(), f"{entry['action']}: {entry['output_summary']}")
                except Exception:
                    pass

        stats = run_case(case, adapter=self.adapter, store=self.hmem.store, on_event=relay, workroot=self.workroot,
                         log_dir=self.log_dir, sample_mode=self.sample_mode, echo=self.echo)
        self.last_stats = stats
        setup, result, cards = stats["_setup"], stats["_result"], stats["_cards"]
        prop = setup["proposal"]
        system_name = f"ippoi_active_site_{case['metal_resid']}" if "ippoi" in case.get("system", "") else case.get("system", case["id"])
        residues = [ResidueSelection(resname=re_label.rstrip("0123456789"), resid=int("".join(ch for ch in re_label if ch.isdigit())),
                                     role=ResidueRole.CATALYTIC if c.role != "metal" else ResidueRole.METAL,
                                     formal_charge=setup["formal"]["per_residue"].get(re_label, 0))
                    for c in prop.choices for re_label in [c.residue]]
        partition = QMMMPartition(system_name=system_name, qm_residues=residues, qm_charge=setup["charge"],
                                  spin_multiplicity=1, total_valence_electrons=prop.charge.electrons,
                                  amber_qmmask=prop.mask, cutoff_radius_angstrom=8.0, decision_cards=cards)
        total = result.get("total_energy_kcal")
        ok = bool(result.get("ok")) and total is not None
        sim = SimulationResult(
            success=ok, system_name=system_name, qm_theory="PM6",
            energy_kcal_mol=total if ok else None, energy_hartree=(total / HARTREE_TO_KCAL_MOL) if ok else None,
            sample_mode=self.sample_mode, execution_time_seconds=float(stats["engine_time_s"]),
            stdout_summary="; ".join(result.get("errors") or []) if not ok else f"ESCF {result.get('qm_escf_kcal')}",
            error_message=None if ok else "; ".join(result.get("errors") or ["no energy"]),
            decision_cards=cards, output_files={"report": stats["report"], "cards": stats["cards"], "trace": stats["trace"]},
            engine={k: v for k, v in result.items() if k != "command"},
        )
        plan = PlannerAgent().plan_from_case(case)
        return WorkflowOutput(success=ok, system_name=system_name, plan=plan, partition=partition, result=sim,
                              decision_cards=cards, chimerax_script_path=None, report_markdown=stats["_report_markdown"],
                              logs=logs)
