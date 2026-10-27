"""ActiveSite — the six agents of the retry loop (metal case).

Planner, DataScout, Setup, Runner, Critic, Explainer. Every action is traced
through ``activesite.trace.Trace``. Decision Cards use the existing
``activesite.models.DecisionCard``; every confidence is computed from a
measured margin (a distance, an angle gap, a charge fraction, a Jaccard),
never typed in as a constant.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from activesite.chem import sander
from activesite.chem.qmregion import FIRST_SHELL, MAX_CHARGE_FRACTION, Proposal, compare, propose
from activesite.chem.system import MolSystem
from activesite.memory.hmem import MemoryRetrievalService, MemoryStoreService
from activesite.models import AlternativeChoice, DecisionCard, DecisionCategory
from activesite.sample import cached_engine_result
from activesite.trace import Trace

ALLOWED_STEPS = ["gather_data", "propose_qm_region", "precheck", "run_qmmm", "postcheck", "explain"]
SANE_DISTANCE = 8.0
MEMORY_QUERY = "qm charge rule nucleotide phosphate cut mg partial charge sum"
MEMORY_TAGS = ["qm-charge", "nucleotide-cut"]
MEMORY_RULE = "mm_partial_sum"
_ID_RE = re.compile(r"^[a-z0-9_]+$")
_SITE_RE = re.compile(r"^[A-Z]$")
_BARE_RESLIST = re.compile(r"^:\d+(,\d+)*$")
PM6_ELEMENTS = frozenset({1, 6, 7, 8, 9, 12, 15, 16, 17, 30, 35, 53})  # elements with PM6 parameters


def _clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, float(x)))


# ------------------------------------------------------------------- adapters
class NullAdapter:
    """Catalog stand-in until P8: every query returns no rows."""

    label = "no-catalog"
    tables = {"lab_runs": "lab_runs", "eda": "eda_residues", "pdb": "pdb_entries"}

    def run_sql(self, sql: str) -> List[Dict[str, Any]]:
        return []


# -------------------------------------------------------------------- Planner
class Planner:
    def __init__(self, llm: Any = None, trace: Optional[Trace] = None):
        self.llm = llm
        self.trace = trace
        self.model_calls = 0

    def plan(self, case: Dict[str, Any]) -> Dict[str, Any]:
        plan = {"steps": list(ALLOWED_STEPS), "theory": "PM6", "mode": "fallback", "dropped": []}
        raw = None
        if self.llm is not None:
            try:
                self.model_calls += 1
                raw = self.llm.plan_json(case)
            except Exception as exc:  # the model is optional; never let it stop the run
                plan["model_error"] = str(exc)[:200]
        if isinstance(raw, dict):
            steps = [s for s in raw.get("steps", []) if isinstance(s, str) and s in ALLOWED_STEPS]
            plan["dropped"] = [s for s in raw.get("steps", []) if s not in steps]
            theory = str(raw.get("theory", "PM6")).upper()
            if steps == ALLOWED_STEPS:
                plan["mode"] = "model"
                plan["steps"] = steps
            if theory in sander.ALLOWED_THEORIES:
                plan["theory"] = theory
        if self.trace:
            self.trace.log("Planner", "plan", f"case {case.get('id')}",
                           f"{len(plan['steps'])} steps, theory {plan['theory']}, mode {plan['mode']}",
                           target_agent="DataScout", data={"plan": plan, "model_calls": self.model_calls})
        return plan


# ------------------------------------------------------------------ DataScout
class DataScout:
    def __init__(self, adapter: Any = None, trace: Optional[Trace] = None):
        self.adapter = adapter or NullAdapter()
        self.trace = trace

    def gather(self, case: Dict[str, Any]) -> Dict[str, Any]:
        system = str(case.get("system", ""))
        site = str(case.get("site", "A"))
        family = str(case.get("family", system))
        if not _ID_RE.match(system) or not _ID_RE.match(family):
            raise ValueError(f"system id {system!r} must match [a-z0-9_]+")
        if not _SITE_RE.match(site):
            raise ValueError(f"site {site!r} must match [A-Z]")
        t = self.adapter.tables
        sql = {
            "q1_expert": f"SELECT * FROM {t['lab_runs']} WHERE system = '{system}' AND site = '{site}' LIMIT 1",
            "q2_analogy": (f"SELECT residue, total FROM {t['eda']} WHERE family = '{family}' "
                           f"ORDER BY abs(total) DESC LIMIT 6"),
            "q3_pdb": f"SELECT pdb_id, resolution, title FROM {t['pdb']} WHERE system = '{system}' ORDER BY resolution ASC",
        }
        out: Dict[str, Any] = {"expert": None, "analogy": [], "pdb": [], "sql": sql, "label": self.adapter.label,
                               "errors": []}
        for key, q in sql.items():
            try:
                rows = self.adapter.run_sql(q) or []
            except Exception as exc:
                out["errors"].append(f"{key}: {exc}")
                rows = []
            if key == "q1_expert":
                out["expert"] = rows[0] if rows else None
            elif key == "q2_analogy":
                out["analogy"] = rows[:6]
            else:
                out["pdb"] = rows
        if self.trace:
            self.trace.log("DataScout", "gather_data", f"{system} site {site} via {self.adapter.label}",
                           f"expert={'yes' if out['expert'] else 'none'} analogy_rows={len(out['analogy'])} pdb_rows={len(out['pdb'])}",
                           target_agent="Setup", status="ok" if not out["errors"] else "partial",
                           data={"sql": sql, "errors": out["errors"]})
        return out


# ---------------------------------------------------------------------- Setup
def residues_touched(system: MolSystem, atoms: Sequence[int]) -> List[int]:
    return sorted({system.atoms[i].residue.idx for i in atoms})


def formal_charge_sum(system: MolSystem, atoms: Sequence[int]) -> Dict[str, Any]:
    """Textbook default: sum of the rounded MM charge of every residue the mask touches (whole residues)."""
    per = {}
    for ridx in residues_touched(system, atoms):
        res = system.s.residues[ridx]
        per[system.res_label(ridx)] = int(round(sum(a.charge for a in res.atoms)))
    return {"total": int(sum(per.values())), "per_residue": per}


class Setup:
    def __init__(self, recall: Optional[MemoryRetrievalService], trace: Optional[Trace], run_id: str):
        self.recall = recall
        self.trace = trace
        self.run_id = run_id

    def build(self, system: MolSystem, case: Dict[str, Any], charge_override: Optional[int] = None,
              override_rule: Optional[str] = None) -> Dict[str, Any]:
        metal = int(case["metal_resid"])
        proposal = propose(system, metal)
        if self.trace:
            self.trace.log("Setup", "propose_qm_region", f"metal residue {metal}",
                           f"{len(proposal.atoms)} atoms, cut level {proposal.cut_level}, {proposal.charge.link_atoms} link atoms",
                           target_agent="Critic", molecule=case.get("system"),
                           data={"mask": proposal.mask, "notes": proposal.notes})
        formal = formal_charge_sum(system, proposal.atoms)
        hits = []
        if self.recall is not None:
            hits = self.recall.retrieve(MEMORY_QUERY, tags=MEMORY_TAGS, actor="Setup", run_id=self.run_id)
        memory_hit = next((h for h in hits if (h["memory"].get("extra") or {}).get("rule") == MEMORY_RULE), None)
        if charge_override is not None:
            charge, rule, from_memory = int(charge_override), override_rule or "override", False
        elif memory_hit is not None:
            charge = proposal.charge.nearest_int
            rule = (f"MM partial-charge sum (recalled from H-MEM {memory_hit['memory']['id']}, "
                    f"score {memory_hit['score']:.2f})")
            from_memory = True
        else:
            charge = formal["total"]
            rule = "formal charges of the residues touched (textbook default)"
            from_memory = False
        setup = {
            "proposal": proposal, "mask": proposal.mask, "atoms": proposal.atoms, "charge": charge, "charge_rule": rule,
            "from_memory": from_memory, "memory_id": memory_hit["memory"]["id"] if memory_hit else None,
            "memory_score": memory_hit["score"] if memory_hit else None, "formal": formal,
            "mm_partial_sum": proposal.charge.mm_sum, "nearest_int": proposal.charge.nearest_int,
            "fraction": proposal.charge.fraction, "metal_resid": metal,
        }
        if self.trace:
            self.trace.log("Setup", "choose_charge", f"formal sum {formal['total']:+d}, MM sum {proposal.charge.mm_sum:+.3f}",
                           f"qmcharge {charge:+d} by {rule}", target_agent="Runner",
                           confidence=_clamp(1 - proposal.charge.fraction / MAX_CHARGE_FRACTION) if from_memory else None,
                           data={"from_memory": from_memory, "memory_id": setup["memory_id"], "hits": len(hits)})
        return setup


# --------------------------------------------------------------------- Runner
class Runner:
    def __init__(self, trace: Optional[Trace], workroot: Path | str, sample_mode: bool = False,
                 timeout_s: int = 300):
        self.trace = trace
        self.workroot = Path(workroot)
        self.sample_mode = sample_mode
        self.timeout_s = timeout_s

    def run(self, case: Dict[str, Any], setup: Dict[str, Any], attempt: int, theory: str = "PM6") -> Dict[str, Any]:
        workdir = self.workroot / f"attempt{attempt}"
        if self.trace:
            self.trace.log("Runner", "run_qmmm", f"attempt {attempt}: qmcharge {setup['charge']:+d}, {len(setup['atoms'])} QM atoms",
                           f"sander {theory} single point in {sander.ENGINE_IMAGE} -> {workdir}", retry_count=attempt,
                           data={"mask": setup["mask"], "charge": setup["charge"]})
        if self.sample_mode or not sander.docker_available():
            result = cached_engine_result(case.get("id", ""), attempt, int(setup["charge"]), theory)
            if result.get("cached") and self.trace:
                self.trace.log("Runner", "cached_engine_output", f"attempt {attempt}: qmcharge {setup['charge']:+d}",
                               f"replayed {result['sample_source']} (no engine ran now)", retry_count=attempt, status="cached")
            if not self.sample_mode and result.get("skipped"):
                result["errors"] = [e.replace("SAMPLE_MODE=true and", f"Docker or {sander.ENGINE_IMAGE} not available and")
                                    for e in result["errors"]]
        else:
            result = sander.run_single_point(case["parm7"], case["coords"], setup["mask"], int(setup["charge"]),
                                             workdir, theory=theory, timeout_s=self.timeout_s)
            result["skipped"] = False
        if self.trace:
            summary = (f"ok ESCF {result['qm_escf_kcal']:.3f} kcal/mol in {result.get('wall_time_s')}s"
                       if result.get("ok") else "FAILED: " + "; ".join(result.get("errors") or ["no energy"]))
            self.trace.log("Runner", "qmmm_result", f"attempt {attempt}", summary, target_agent="Critic",
                           retry_count=attempt, status="ok" if result.get("ok") else "failed",
                           data={k: result.get(k) for k in ("qm_escf_kcal", "total_energy_kcal", "odd_electrons",
                                                            "link_atoms", "exit_code", "wall_time_s")})
        return result


# --------------------------------------------------------------------- Critic
class Critic:
    def __init__(self, store: Optional[MemoryStoreService], trace: Optional[Trace], run_id: str):
        self.store = store
        self.trace = trace
        self.run_id = run_id

    def precheck(self, system: MolSystem, case: Dict[str, Any], setup: Dict[str, Any],
                 data: Dict[str, Any]) -> List[Dict[str, Any]]:
        metal = system.select(f":{case['metal_resid']}")[0]
        atoms = set(setup["atoms"])
        checks: List[Dict[str, Any]] = []

        worst = []
        for ridx in residues_touched(system, setup["atoms"]):
            res_atoms = [i for i in atoms if system.atoms[i].residue.idx == ridx]
            worst.append((min(system.dist(metal, i) for i in res_atoms), system.res_label(ridx)))
        far = [(lbl, round(d, 2)) for d, lbl in worst if d > SANE_DISTANCE]
        dmax = max(d for d, _ in worst)
        checks.append({"name": "qm_residues_near_metal", "passed": not far,
                       "detail": f"farthest QM residue nearest-atom distance {dmax:.2f} Å (limit {SANE_DISTANCE})" +
                                 (f"; too far: {far}" if far else ""),
                       "margin": round(SANE_DISTANCE - dmax, 3)})

        shell = [j for j in system.within(metal, FIRST_SHELL) if system.atoms[j].atomic_number > 1]
        missing = [system.label(j) for j in shell if j not in atoms]
        checks.append({"name": "first_shell_in_qm", "passed": not missing,
                       "detail": f"{len(shell)} heavy atoms within {FIRST_SHELL} Å of the metal, {len(shell) - len(missing)} in QM" +
                                 (f"; missing {missing}" if missing else ""),
                       "margin": round((len(shell) - len(missing)) / max(1, len(shell)), 3)})

        frac = setup["fraction"]
        checks.append({"name": "boundary_fraction", "passed": frac <= MAX_CHARGE_FRACTION,
                       "detail": f"|MM sum - nearest integer| = {frac:.3f} e (limit {MAX_CHARGE_FRACTION})",
                       "margin": round(MAX_CHARGE_FRACTION - frac, 4)})

        expert = data.get("expert") or {}
        mask = str(expert.get("qmmask") or expert.get("mask") or "")
        if mask and _BARE_RESLIST.match(mask.strip()):
            flagged = []
            names = {}
            for tok in str(expert.get("residues") or "").split():
                m = re.match(r"([A-Z0-9]+?)(\d+)$", tok)
                if m:
                    names[int(m.group(2))] = m.group(1)
            for rid in (int(x) for x in mask.strip()[1:].split(",")):
                if rid < 1 or rid > len(system.s.residues):
                    flagged.append(f"{rid}: not in topology")
                    continue
                res = system.s.residues[rid - 1]
                d = min(system.dist(metal, a.idx) for a in res.atoms)
                if d > SANE_DISTANCE:
                    flagged.append(f"{system.res_label(rid - 1)}: {d:.1f} Å from the metal")
                if rid in names and names[rid] != res.name:
                    flagged.append(f"{rid}: expert says {names[rid]}, topology has {res.name}")
            checks.append({"name": "expert_mask_provenance", "passed": not flagged,
                           "detail": "expert residue list checked against this topology" +
                                     (f"; flagged {flagged}" if flagged else "; all residues near the metal with matching names"),
                           "margin": round(1 - len(flagged) / max(1, mask.count(",") + 1), 3)})
        if self.trace:
            failed = [c["name"] for c in checks if not c["passed"]]
            self.trace.log("Critic", "precheck", f"{len(checks)} checks", "all passed" if not failed else f"flagged {failed}",
                           target_agent="Runner", status="ok" if not failed else "flagged", data={"checks": checks})
        return checks

    def diagnose(self, system: MolSystem, setup: Dict[str, Any], result: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        fix = None
        if result.get("odd_electrons") is not None and setup["charge"] != setup["nearest_int"]:
            prop: Proposal = setup["proposal"]
            fix = {
                "charge": setup["nearest_int"],
                "why": (f"sander reported an odd electron count ({result['odd_electrons']}) at qmcharge {setup['charge']:+d}. "
                        f"The mask cuts nucleotides at the phosphate ({prop.cut_level} level), so whole-residue formal "
                        f"charges ({setup['formal']['total']:+d}) do not apply; the MM partial-charge sum over the QM atoms is "
                        f"{setup['mm_partial_sum']:+.3f} e, nearest integer {setup['nearest_int']:+d} "
                        f"(fraction {setup['fraction']:.3f})."),
            }
        elif result.get("odd_electrons") is not None:
            fix = None  # already at the MM-sum integer; a different fix is needed, not a retry
        if self.trace:
            self.trace.log("Critic", "diagnose", "attempt failed" if not result.get("ok") else "attempt ok",
                           fix["why"] if fix else "no fix proposed", target_agent="Runner",
                           status="ok" if fix or result.get("ok") else "unresolved", data={"fix": fix})
        return fix

    def remember(self, case: Dict[str, Any], first_setup: Dict[str, Any], fix: Dict[str, Any]) -> Optional[str]:
        """Only after the retry succeeded."""
        if self.store is None:
            return None
        content = (f"qm charge rule for mg phosphodiester sites: when the QM mask cuts a nucleotide at the phosphate, "
                   f"take qmcharge from the MM partial charge sum over the QM atoms (nearest integer), not from the formal "
                   f"charges of whole residues. Learned on {case.get('id')}: formal sum {first_setup['formal']['total']:+d} "
                   f"gave an odd electron count; MM sum {first_setup['mm_partial_sum']:+.3f} -> {fix['charge']:+d} converged.")
        mem_id = self.store.add(content, type="rule", layer="long_term",
                                tags=["qm-charge", "nucleotide-cut", "mg-phosphodiester"],
                                source=f"critic:sander-retry run={self.run_id}", confidence=0.9, agent_id="Critic",
                                run_id=self.run_id, extra={"rule": MEMORY_RULE, "case": case.get("id"),
                                                           "first_charge": first_setup["charge"], "fixed_charge": fix["charge"]})
        if self.trace:
            self.trace.log("Critic", "remember", f"retry succeeded with qmcharge {fix['charge']:+d}", f"stored {mem_id}",
                           target_agent="Setup", confidence=0.9, data={"memory_id": mem_id})
        return mem_id

    def validate(self, system: MolSystem, case: Dict[str, Any], setup: Dict[str, Any],
                 data: Dict[str, Any]) -> Dict[str, Any]:
        expert = data.get("expert") or {}
        mask = expert.get("qmmask") or expert.get("mask")
        out: Dict[str, Any] = {"expert_mask_present": bool(mask), "expert_qmcharge": expert.get("qmcharge")}
        if mask:
            try:
                exp_atoms = system.select(str(mask))
                cmp = compare(system, setup["atoms"], exp_atoms)
                out.update({"jaccard": cmp["atom_jaccard"], "only_ours": cmp["only_ours"], "only_expert": cmp["only_expert"],
                            "expert_atoms": cmp["expert_atoms"]})
            except Exception as exc:
                out["error"] = f"could not select expert mask: {exc}"
        if expert.get("qmcharge") is not None:
            out["charge_match"] = int(expert["qmcharge"]) == int(setup["charge"])
        if self.trace:
            self.trace.log("Critic", "postcheck", "expert mask present" if mask else "no expert record",
                           f"jaccard {out.get('jaccard')}" if mask else "validation skipped (no expert)",
                           target_agent="Explainer", confidence=out.get("jaccard"), data=out)
        return out


# ------------------------------------------------------------------ Explainer
_ROLE_RULE = {"metal": 1, "first_shell": 2, "scissile_phosphate": 3, "leaving_group": 3, "nucleophile": 4, "general_base": 5}
_ROLE_ALTERNATIVES = {
    "first_shell": [AlternativeChoice(name="Leave it in MM", rejected_reason="a ligand inside the first shell polarises the metal; point charges cannot describe it")],
    "nucleophile": [AlternativeChoice(name="Another water near P", rejected_reason="smaller O(w)-P-O3' angle, not in line for attack")],
    "general_base": [AlternativeChoice(name="No general base", rejected_reason="the nucleophile needs a proton acceptor within hydrogen-bond range")],
    "scissile_phosphate": [AlternativeChoice(name="Another phosphate", rejected_reason="farther from the metal")],
}


class Explainer:
    def __init__(self, trace: Optional[Trace] = None):
        self.trace = trace

    @staticmethod
    def _choice_confidence(choice, proposal: Proposal) -> float:
        ev = choice.evidence
        rule = _ROLE_RULE.get(choice.role, 5)
        if choice.role == "metal":
            return _clamp(0.8 + 0.2 * min(1.0, len([c for c in proposal.choices if c.role == "first_shell"]) / 6))
        if choice.role == "first_shell":
            d = min(v for k, v in ev.items() if k.endswith("_dist"))
            return _clamp(0.8 + 0.2 * (FIRST_SHELL - d) / FIRST_SHELL)
        if choice.role in ("scissile_phosphate", "leaving_group"):
            others = ev.get("other_P_within_8A") or []
            gap = (others[0][1] - ev["metal_P_dist"]) if others else 8.0 - ev.get("metal_P_dist", ev.get("metal_O3prime_dist", 0))
            return _clamp(0.8 + 0.2 * _clamp(gap / 4.0))
        if choice.role == "nucleophile":
            rejected = ev.get("rejected") or []
            gap = ev["Ow_P_O3prime_angle"] - (rejected[0][1] if rejected else 90.0)
            return _clamp(0.5 + 0.3 * _clamp(gap / 90.0))
        if choice.role == "general_base":
            return _clamp(0.5 + 0.3 * (1 - ev["N_Ow_dist"] / 6.0))
        return 0.5 if rule >= 4 else 0.8

    def cards(self, system: MolSystem, case: Dict[str, Any], setup: Dict[str, Any], checks: List[Dict[str, Any]],
              attempts: List[Dict[str, Any]], data: Dict[str, Any], validation: Dict[str, Any], theory: str,
              memory_id: Optional[str] = None) -> List[DecisionCard]:
        prop: Proposal = setup["proposal"]
        coords = Path(case["coords"]).name
        cards: List[DecisionCard] = []
        for i, ch in enumerate(prop.choices, start=1):
            rule_n = _ROLE_RULE.get(ch.role, 5)
            cards.append(DecisionCard(
                decision_id=f"DEC_REGION_{i:02d}_{ch.role.upper()}_{ch.residue}",
                category=DecisionCategory.RESIDUE_INCLUSION, target=ch.residue,
                choice=f"{ch.residue} in QM as {ch.role.replace('_', ' ')}",
                alternatives=_ROLE_ALTERNATIVES.get(ch.role, []), rationale=ch.rule,
                confidence=round(self._choice_confidence(ch, prop), 3),
                evidence={**ch.evidence, "source": f"geometry of {coords} (rule {rule_n})"},
            ))
        cards.append(DecisionCard(
            decision_id="DEC_CUT_LEVEL", category=DecisionCategory.CUT_LEVEL, target="QM/MM boundary",
            choice=f"cut level '{prop.cut_level}' ({prop.charge.link_atoms} link atoms)",
            alternatives=[AlternativeChoice(name=n.split(" rejected")[0], rejected_reason=n.split(": ", 1)[-1])
                          for n in prop.notes if "rejected" in n],
            rationale="; ".join(prop.notes),
            confidence=round(_clamp(0.5 + 0.5 * (1 - prop.charge.fraction / MAX_CHARGE_FRACTION)), 3),
            evidence={"mask": prop.mask, "mm_sum": round(prop.charge.mm_sum, 4), "fraction": round(prop.charge.fraction, 4),
                      "link_atoms": prop.charge.link_atoms, "notes": prop.notes, "source": f"geometry of {coords}"},
        ))
        rejected = [a for a in attempts if not a["result"].get("ok")]
        final = attempts[-1]
        alt = []
        for a in rejected:
            why = "; ".join(a["result"].get("errors") or ["no energy"])
            alt.append(AlternativeChoice(name=f"qmcharge {a['setup']['charge']:+d} by {a['setup']['charge_rule']}",
                                         rejected_reason=f"attempt {a['attempt']}: {why}"))
        involved = len(attempts) > 1 or setup["from_memory"]
        ok = bool(final["result"].get("ok"))
        q_conf = _clamp(1 - prop.charge.fraction / MAX_CHARGE_FRACTION) * (1.0 if ok else 0.5)
        cards.append(DecisionCard(
            decision_id="DEC_QMCHARGE", category=DecisionCategory.CHARGE_AND_SPIN, target="qmcharge",
            choice=f"qmcharge {setup['charge']:+d} (spin 1)", alternatives=alt,
            rationale=setup["charge_rule"] + (f". First attempt rejected: {rejected[0]['fix_why']}" if rejected and rejected[0].get("fix_why") else ""),
            confidence=round(q_conf, 3),
            evidence={"mm_partial_sum": round(setup["mm_partial_sum"], 4), "nearest_int": setup["nearest_int"],
                      "formal_sum": setup["formal"]["total"], "per_residue_formal": setup["formal"]["per_residue"],
                      "attempts": [{"attempt": a["attempt"], "charge": a["setup"]["charge"], "ok": bool(a["result"].get("ok")),
                                    "odd_electrons": a["result"].get("odd_electrons")} for a in attempts],
                      "memory_id": memory_id or setup.get("memory_id"),
                      "source": "sander validation + H-MEM" if involved else "MM partial-charge sum"},
        ))
        z = [system.atoms[i].atomic_number for i in setup["atoms"]]
        covered = sum(1 for x in z if x in PM6_ELEMENTS) / max(1, len(z))
        cards.append(DecisionCard(
            decision_id=f"DEC_THEORY_{theory}", category=DecisionCategory.THEORY_SELECTION, target="level of theory",
            choice=f"{theory} semi-empirical single point (PME, spin 1)",
            alternatives=[AlternativeChoice(name="DFT (B3LYP/6-31G*) via QMHub", rejected_reason="hours per point; outside the judge CPU budget"),
                          AlternativeChoice(name="Pure MM", rejected_reason="fixed charges cannot describe the in-line attack")],
            rationale=f"{covered * 100:.0f}% of QM atoms have {theory} parameters; the expert protocol uses PM6 as its low-level method",
            confidence=round(_clamp(covered), 3),
            evidence={"qm_atoms": len(z), "parameterised_fraction": round(covered, 3), "source": "qmhub.ini low level"},
        ))
        for c in checks:
            cards.append(DecisionCard(
                decision_id=f"DEC_CHECK_{c['name'].upper()}", category=DecisionCategory.CRITIC_CORRECTION,
                target=c["name"], choice=("passed: " if c["passed"] else "flagged: ") + c["detail"],
                rationale="Critic precheck on the proposed region", confidence=round(_clamp(0.5 + 0.5 * _clamp(c["margin"] / (SANE_DISTANCE if "metal" in c["name"] else 1.0))), 3) if c["passed"] else 0.0,
                evidence={"margin": c["margin"], "passed": c["passed"], "source": "Critic.precheck"},
            ))
        if validation.get("expert_mask_present"):
            j = validation.get("jaccard")
            cards.append(DecisionCard(
                decision_id="DEC_VALIDATION_EXPERT", category=DecisionCategory.VALIDATION, target="expert agreement",
                choice=f"atom Jaccard {j}" if j is not None else "expert mask could not be selected",
                rationale="comparison with the laboratory record for this site",
                confidence=round(_clamp(j or 0.0), 3), evidence={**validation, "source": data.get("label")},
            ))
        if data.get("analogy"):
            rows = data["analogy"]
            cards.append(DecisionCard(
                decision_id="DEC_ANALOGY_EDA", category=DecisionCategory.ANALOGY, target="analogy only",
                choice=f"{len(rows)} residues from a same-family energy decomposition (analogy only)",
                rationale="not evidence for this system; shows which residues mattered in a related one",
                confidence=round(_clamp(min(0.5, len(rows) / 12)), 3), evidence={"rows": rows, "sql": data["sql"]["q2_analogy"], "source": data.get("label")},
            ))
        if self.trace:
            self.trace.log("Explainer", "cards", f"{len(prop.choices)} choices, {len(checks)} checks, {len(attempts)} attempts",
                           f"{len(cards)} decision cards", data={"ids": [c.decision_id for c in cards]})
        return cards

    def report(self, case: Dict[str, Any], run_id: str, stats: Dict[str, Any], cards: List[DecisionCard],
               result: Dict[str, Any], validation: Dict[str, Any], trace_path: Path | str,
               setup: Dict[str, Any]) -> str:
        ok = bool(result.get("ok"))
        esc = result.get("qm_escf_kcal")
        tot = result.get("total_energy_kcal")
        line = (f"**Result:** {'converged' if ok else 'FAILED'} — "
                f"ESCF {esc:.3f} kcal/mol, total {tot:.2f} kcal/mol, " if ok else
                f"**Result:** FAILED — ESCF `null`, total `null` ({'; '.join(result.get('errors') or ['no energy'])}), ")
        line += f"{result.get('link_atoms') if result.get('link_atoms') is not None else '?'} link atoms, {result.get('wall_time_s', 0)} s engine time"
        lines = [f"# ActiveSite report — `{case.get('id')}` (run `{run_id}`)", "",
                 f"**Question:** {case.get('question', '')}", "", line, "",
                 f"**Engine:** {stats.get('engine_label')}", "",
                 f"**qmcharge:** {setup['charge']:+d} by {setup['charge_rule']}; retries {stats.get('retries')}; "
                 f"memory used: {stats.get('memory_used')}", "", "## Expert agreement"]
        if validation.get("expert_mask_present"):
            lines += [f"- atom Jaccard vs expert mask: {validation.get('jaccard')}",
                      f"- only ours: {validation.get('only_ours')}", f"- only expert: {validation.get('only_expert')}",
                      f"- expert qmcharge: {validation.get('expert_qmcharge')} (match: {validation.get('charge_match')})"]
        else:
            lines.append("- no expert record in the catalog for this site (no-catalog or no row); nothing to compare")
        lines += ["", "## Decision cards"]
        for i, c in enumerate(cards, start=1):
            lines.append(f"### {i}. {c.category.value}: {c.target}")
            lines.append(f"- **Choice:** {c.choice} *(confidence {c.confidence:.2f})*")
            lines.append(f"- **Why:** {c.rationale}")
            if c.alternatives:
                lines.append("- **Rejected:**")
                lines += [f"  - {a.name}: {a.rejected_reason}" for a in c.alternatives]
            lines.append("- **Evidence:** " + json.dumps({k: v for k, v in c.evidence.items() if k != "notes"}, default=str)[:900])
            lines.append("")
        lines += ["## Trace", f"`{trace_path}`", "", "## Limitations",
                  "- PM6 single point only; no free-energy barrier computed locally.",
                  "- Catalog is a local stand-in unless an adapter with real tables was supplied."]
        md = "\n".join(lines) + "\n"
        if self.trace:
            self.trace.log("Explainer", "report", f"{len(cards)} cards", f"{len(md)} chars of markdown")
        return md
