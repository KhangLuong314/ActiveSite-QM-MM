"""ActiveSite — orchestrator: the retry loop for metal cases, plus a compatibility wrapper.

run_case: Planner -> DataScout -> Setup -> Critic.precheck -> Runner attempt 0 ->
Critic.diagnose -> (retry once with the fix; on success Critic.remember) ->
Critic.validate -> Explainer. Writes logs/report-<run_id>.md and
logs/cards-<run_id>.json and returns a stats dict.

``run_ligand_case`` is the ligand loop (P7). ``run_case`` routes on the case
file: ``"kind": "ligand"`` -> ligand loop, ``metal_resid`` -> metal loop.
``MasterOrchestrator`` keeps the old ``run_case(case_id, on_event)`` /
``run_query`` contract for the web server and CLI.
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
from activesite.adapters.zetaris import get_adapter
from activesite.llm import ModelClient
from pydantic import BaseModel, Field

from activesite.agent.core import Critic, DataScout, Explainer, NullAdapter, Planner, Runner, Setup
from activesite.agent.ligand import LigandCritic, LigandSetup, ligand_cards, run_qmmm
from activesite.agent.planner import ExecutionPlan, PlannerAgent
from activesite.chem.runner import HARTREE_TO_KCAL_MOL
from activesite.chem.system import MolSystem
from activesite.memory.hmem import MemoryRetrievalService, MemoryStoreService
from activesite.memory.meterless import DEFAULT_DB_PATH, DEFAULT_LEDGER_PATH, MeterlessHMEM
from activesite.models import DecisionCard, QMMMPartition, ResidueRole, ResidueSelection, SimulationResult
from activesite.sample import CACHED_LABEL, serialisable_setup
from activesite.trace import Trace

__all__ = ["run_case", "run_metal_case", "run_ligand_case", "new_run_id", "resolve_case_id", "public_stats", "MasterOrchestrator", "WorkflowOutput"]


class WorkflowOutput(BaseModel):
    """Compatibility result shape used by the web server, the CLI and older tests."""
    success: bool
    system_name: str
    plan: ExecutionPlan
    partition: QMMMPartition
    result: SimulationResult
    decision_cards: List[DecisionCard] = Field(default_factory=list)
    chimerax_script_path: Optional[str] = None
    report_markdown: str = ""
    logs: List[str] = Field(default_factory=list)
    stats: Dict[str, Any] = Field(default_factory=dict)


def new_run_id() -> str:
    return f"{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}-{secrets.token_hex(3)}"


def _env_sample_mode() -> bool:
    return os.getenv("SAMPLE_MODE", "true").lower() in ("true", "1", "yes")


def _adapter_and_llm(adapter: Any, llm: Any, case: Dict[str, Any]):
    """Default data adapter (Zetaris if configured, else the DuckDB stand-in) and model client (only with a key)."""
    if adapter is None:
        adapter = get_adapter()
    if hasattr(adapter, "prepare"):
        try:
            adapter.prepare(case)
        except Exception:
            pass
    if llm is None:
        client = ModelClient()
        llm = client if client.available else None
    return adapter, llm


ENGINE_DOCKER = "sander in Docker"
ENGINE_CACHED = CACHED_LABEL
ENGINE_UNAVAILABLE = "engine unavailable"


def _engine_label(result: Dict[str, Any]) -> str:
    if result.get("cached"):
        return ENGINE_CACHED
    if result.get("skipped"):
        return ENGINE_UNAVAILABLE
    return ENGINE_DOCKER


def public_stats(stats: Dict[str, Any]) -> Dict[str, Any]:
    """The JSON shape shared by run.py --json and POST /run."""
    return {k: v for k, v in stats.items() if not k.startswith("_")}


def resolve_case_id(query: str) -> str:
    """Map a free-text request to a benchmark case id (raises when nothing matches)."""
    plan = PlannerAgent().plan_from_prompt(query)
    if plan.metal_resid is not None and "ippoi" in plan.system_name:
        return "ippoi_site_b" if plan.metal_resid == 372 else "ippoi_site_a"
    if plan.system_name == "egfr_erlotinib":
        return "egfr_erlotinib"
    if plan.system_name == "abl_imatinib":
        return "abl_imatinib_a"
    raise ValueError(f"no benchmark case matches the query (system {plan.system_name!r}); try --case")


def _load(case: Dict[str, Any] | str) -> Dict[str, Any]:
    return CaseLoader().load_benchmark_case(case) if isinstance(case, str) else case


def run_case(case: Dict[str, Any] | str, adapter: Any = None, hmem_db: Path | str | None = None,
             on_event: Optional[Callable[[Dict[str, Any]], None]] = None, **kw: Any) -> Dict[str, Any]:
    """Route on the case file: ligand cases to the ligand loop, metal cases to the retry loop."""
    case = _load(case)
    if case.get("kind") == "ligand":
        return run_ligand_case(case, adapter, hmem_db, on_event, **kw)
    if "metal_resid" in case:
        return run_metal_case(case, adapter, hmem_db, on_event, **kw)
    raise ValueError(f"case {case.get('id')} is neither a ligand case (kind) nor a metal case (metal_resid)")


def run_metal_case(case: Dict[str, Any] | str, adapter: Any = None, hmem_db: Path | str | None = None,
                   on_event: Optional[Callable[[Dict[str, Any]], None]] = None, *, ledger_path: Path | str | None = None,
                   store: Optional[MemoryStoreService] = None, workroot: Path | str = "data/runs",
                   log_dir: Path | str = "logs", llm: Any = None, sample_mode: Optional[bool] = None,
                   timeout_s: int = 300, echo: bool = True) -> Dict[str, Any]:
    """Run one metal case through the retry loop and return the stats dict."""
    t0 = time.monotonic()
    case = _load(case)
    if "metal_resid" not in case:
        raise ValueError(f"case {case.get('id')} has no metal_resid; the loop handles metal cases only")
    sample_mode = _env_sample_mode() if sample_mode is None else bool(sample_mode)
    run_id = new_run_id()
    trace = Trace(run_id, log_dir, on_event=on_event, echo=echo)
    if store is None:
        store = MemoryStoreService(hmem_db or DEFAULT_DB_PATH, ledger_path or DEFAULT_LEDGER_PATH)
    retrieval = MemoryRetrievalService(store)

    adapter, llm = _adapter_and_llm(adapter, llm, case)
    planner = Planner(llm, trace)
    plan = planner.plan(case)
    theory = plan["theory"]
    data = DataScout(adapter, trace).gather(case)

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
        "run_id": run_id, "case": case.get("id"), "kind": "metal", "retries": retries, "memory_used": bool(setup["from_memory"]),
        "memory_written": memory_id, "qm_ok": bool(result.get("ok")), "qm_escf_kcal": result.get("qm_escf_kcal"),
        "total_energy_kcal": result.get("total_energy_kcal"),
        "engine_time_s": round(sum(float(a["result"].get("wall_time_s") or 0.0) for a in attempts), 2),
        "wall_time_s": None, "model_calls": planner.model_calls, "model_mode": plan["mode"],
        "trace": str(trace.path), "qmcharge": setup["charge"], "charge_rule": setup["charge_rule"],
        "mask": setup["mask"], "engine_skipped": bool(result.get("skipped")), "errors": result.get("errors") or [],
        "engine_label": _engine_label(result),
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


def run_ligand_case(case: Dict[str, Any] | str, adapter: Any = None, hmem_db: Path | str | None = None,
                    on_event: Optional[Callable[[Dict[str, Any]], None]] = None, *, ledger_path: Path | str | None = None,
                    store: Optional[MemoryStoreService] = None, workroot: Path | str = "data/runs",
                    log_dir: Path | str = "logs", llm: Any = None, sample_mode: Optional[bool] = None,
                    timeout_s: int = 300, echo: bool = True) -> Dict[str, Any]:
    """Prepare a protein-ligand complex, check it, run one GB single point, validate the binding mode."""
    t0 = time.monotonic()
    case = _load(case)
    if case.get("kind") != "ligand":
        raise ValueError(f"case {case.get('id')} is not a ligand case")
    sample_mode = _env_sample_mode() if sample_mode is None else bool(sample_mode)
    run_id = new_run_id()
    trace = Trace(run_id, log_dir, on_event=on_event, echo=echo)
    if store is None:
        store = MemoryStoreService(hmem_db or DEFAULT_DB_PATH, ledger_path or DEFAULT_LEDGER_PATH)
    retrieval = MemoryRetrievalService(store)
    work = Path(workroot) / run_id

    adapter, llm = _adapter_and_llm(adapter, llm, case)
    planner = Planner(llm, trace)
    plan = planner.plan(case)
    data = DataScout(adapter, trace).gather(case)
    setup = LigandSetup(retrieval, trace, run_id, work, sample_mode=sample_mode).build(case)
    if not setup.get("prep_skipped") and not setup.get("prep_cached"):
        (work / "prep.json").write_text(json.dumps(serialisable_setup(setup), indent=1), encoding="utf-8")
    critic = LigandCritic(store, trace, run_id)
    checks = critic.precheck(setup, data.get("expert"))
    blocking = critic.blocking(checks)

    if blocking:
        reason = "; ".join(c["detail"] for c in checks if c["name"] in blocking)
        trace.log("Orchestrator", "blocked", f"checks {blocking}", f"QM/MM not run: {reason}", status="error",
                  data={"blocking": blocking})
        result = {"ok": False, "skipped": True, "qm_escf_kcal": None, "total_energy_kcal": None, "link_atoms": None,
                  "errors": [f"blocked by {', '.join(blocking)}: {reason}"], "wall_time_s": 0.0, "exit_code": None}
    else:
        result = run_qmmm(trace, setup, work, case_id=case.get('id', ''), sample_mode=sample_mode)
    val = critic.validate(setup, case)
    memory_ids = critic.remember(case, setup, bool(result.get("ok")))
    cards = ligand_cards(case, setup, checks, result, val, data)
    trace.log("Explainer", "cards", f"{len(checks)} checks, {len(setup.get('overrides') or [])} overrides", f"{len(cards)} decision cards",
              data={"ids": [c.decision_id for c in cards]})

    stats = {
        "run_id": run_id, "case": case.get("id"), "kind": "ligand", "retries": 0, "memory_used": bool(setup.get("recalled")),
        "memory_written": memory_ids or None, "qm_ok": bool(result.get("ok")), "qm_escf_kcal": result.get("qm_escf_kcal"),
        "total_energy_kcal": result.get("total_energy_kcal"), "engine_time_s": round(float(result.get("wall_time_s") or 0.0), 2),
        "wall_time_s": None, "model_calls": planner.model_calls, "model_mode": plan["mode"], "trace": str(trace.path),
        "qmcharge": setup.get("charge"), "charge_rule": "ligand net charge from its protonation state", "mask": ":LIG",
        "engine_skipped": bool(result.get("skipped")), "errors": result.get("errors") or [], "blocked": blocking,
        "chain": setup.get("chain"), "overrides": setup.get("overrides"), "checks": checks, "validation": val,
        "catalog": data.get("label"), "sql": data.get("sql"), "prep_skipped": setup.get("prep_skipped"),
        "engine_label": _engine_label(result),
    }
    report = _ligand_report(case, run_id, stats, cards, result, val, trace.path, setup)
    log_dir = Path(log_dir)
    (log_dir / f"report-{run_id}.md").write_text(report, encoding="utf-8")
    (log_dir / f"cards-{run_id}.json").write_text(json.dumps([c.model_dump() for c in cards], indent=2, default=str), encoding="utf-8")
    stats["wall_time_s"] = round(time.monotonic() - t0, 2)
    stats["report"] = str(log_dir / f"report-{run_id}.md")
    stats["cards"] = str(log_dir / f"cards-{run_id}.json")
    stats["_report_markdown"] = report
    stats["_cards"] = cards
    stats["_setup"] = setup
    stats["_result"] = result
    trace.log("Orchestrator", "done", f"{case.get('id')}", f"qm_ok {stats['qm_ok']}, blocked {blocking}, memory_used {stats['memory_used']}",
              data={k: v for k, v in stats.items() if not k.startswith("_") and k not in ("checks", "validation", "sql", "overrides")})
    return stats


def _ligand_report(case, run_id, stats, cards, result, val, trace_path, setup) -> str:
    ok = bool(result.get("ok"))
    if ok:
        line = (f"**Result:** converged — ESCF {result['qm_escf_kcal']:.3f} kcal/mol, total {result['total_energy_kcal']:.2f} kcal/mol, "
                f"{result.get('link_atoms')} link atoms, {result.get('wall_time_s')} s engine time")
    else:
        line = f"**Result:** FAILED — ESCF `null`, total `null` ({'; '.join(result.get('errors') or ['no energy'])})"
    lines = [f"# ActiveSite report — `{case.get('id')}` (run `{run_id}`)", "", f"**Question:** {case.get('question', '')}", "", line, "",
             f"**Engine:** {stats.get('engine_label')}", "",
             f"**Ligand charge:** {'null' if setup.get('charge') is None else f"{setup['charge']:+d}"}; chain {setup.get('chain')} ({setup.get('chain_source')}); "
             f"His overrides {len(setup.get('overrides') or [])}; memory used: {stats['memory_used']}", "", "## Binding mode"]
    if val.get("available"):
        lines += [f"- published contacts recovered: {len(val['recovered'])}/{val['published']} " +
                  ", ".join(f"{r} {d:.2f} Å" for r, d in val["recovered"].items()),
                  f"- missed: {val['missed']}", f"- expected absent: {val['expected_absent']}", f"- extra polar contacts: {val['extra']}"]
    else:
        lines.append("- no minimised model (preparation did not run); crystal polar contacts only: " +
                     ", ".join(f"{c['partner']} {c['distance']:.2f} Å" for c in (setup.get("crystal_contacts") or {}).get("contacts", [])[:8]))
    lines += ["", "## Decision cards"]
    for i, c in enumerate(cards, start=1):
        lines.append(f"### {i}. {c.category.value}: {c.target}")
        lines.append(f"- **Choice:** {c.choice} *(confidence {c.confidence:.2f})*")
        lines.append(f"- **Why:** {c.rationale}")
        if c.alternatives:
            lines.append("- **Rejected:**")
            lines += [f"  - {a.name}: {a.rejected_reason}" for a in c.alternatives]
        lines.append("- **Evidence:** " + json.dumps({k: v for k, v in c.evidence.items() if k not in ("table", "pkas", "states")}, default=str)[:900])
        lines.append("")
    lines += ["## Trace", f"`{trace_path}`", "", "## Limitations",
              "- PM6 single point of the whole ligand in implicit solvent (igb=5); crystal waters removed; no free-energy barrier.",
              "- His states near the ligand cation are geometric calls; the charged state should be run as a sensitivity check.",
              "- Catalog is a local stand-in unless an adapter with real tables was supplied."]
    return "\n".join(lines) + "\n"


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
        self.last_stats: Optional[Dict[str, Any]] = None

    def run_case(self, case_id: str, on_event: Optional[Callable[[str, str], None]] = None) -> WorkflowOutput:
        return self._run_loop(self.loader.load_benchmark_case(case_id), on_event)

    def run_query(self, query: str, on_event: Optional[Callable[[str, str], None]] = None) -> WorkflowOutput:
        return self._run_loop(self.loader.load_benchmark_case(resolve_case_id(query)), on_event)

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
        if stats["kind"] == "metal":
            prop = setup["proposal"]
            system_name = f"ippoi_active_site_{case['metal_resid']}" if "ippoi" in case.get("system", "") else case.get("system", case["id"])
            residues = [ResidueSelection(resname=lbl.rstrip("0123456789"), resid=int("".join(ch for ch in lbl if ch.isdigit())),
                                         role=ResidueRole.CATALYTIC if c.role != "metal" else ResidueRole.METAL,
                                         formal_charge=setup["formal"]["per_residue"].get(lbl, 0))
                        for c in prop.choices for lbl in [c.residue]]
            partition = QMMMPartition(system_name=system_name, qm_residues=residues, qm_charge=setup["charge"],
                                      spin_multiplicity=1, total_valence_electrons=prop.charge.electrons,
                                      amber_qmmask=prop.mask, cutoff_radius_angstrom=8.0, decision_cards=cards)
        else:
            system_name = case.get("system", case["id"])
            residues = [ResidueSelection(resname=case["ligand"], resid=1, role=ResidueRole.LIGAND, formal_charge=setup.get("charge") or 0)]
            partition = QMMMPartition(system_name=system_name, qm_residues=residues, qm_charge=setup.get("charge") or 0,
                                      spin_multiplicity=1, amber_qmmask=":LIG", decision_cards=cards)
        total = result.get("total_energy_kcal")
        ok = bool(result.get("ok")) and total is not None
        sim = SimulationResult(
            success=ok, system_name=system_name, qm_theory="PM6",
            energy_kcal_mol=total if ok else None, energy_hartree=(total / HARTREE_TO_KCAL_MOL) if ok else None,
            sample_mode=self.sample_mode, execution_time_seconds=float(stats["engine_time_s"]),
            stdout_summary="; ".join(result.get("errors") or []) if not ok else f"ESCF {result.get('qm_escf_kcal')}",
            error_message=None if ok else "; ".join(result.get("errors") or ["no energy"]),
            decision_cards=cards, output_files={"report": stats["report"], "cards": stats["cards"], "trace": stats["trace"]},
            engine=stats["engine_label"], engine_output={k: v for k, v in result.items() if k != "command"},
        )
        plan = PlannerAgent().plan_from_case(case)
        return WorkflowOutput(success=ok, system_name=system_name, plan=plan, partition=partition, result=sim,
                              decision_cards=cards, chimerax_script_path=None, report_markdown=stats["_report_markdown"],
                              logs=logs, stats={k: v for k, v in stats.items() if not k.startswith("_")})
