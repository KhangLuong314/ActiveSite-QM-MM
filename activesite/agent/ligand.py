"""ActiveSite — the ligand case: LigandSetup, LigandCritic, run_qmmm, ligand_cards.

Every container stage comes from ``activesite.chem.prep``; the pure stages
(chain choice, extraction, amine detection, crystal contacts) run even without
Docker so the report can still explain what was decided and why the engine
did not run.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from activesite.chem import prep, sander
from activesite.chem.prep import HBOND
from activesite.chem.sander import run_qmmm_md, run_single_point
from activesite.memory.hmem import MemoryRetrievalService, MemoryStoreService
from activesite.models import AlternativeChoice, DecisionCard, DecisionCategory
from activesite.sample import cached_engine_result, cached_md, cached_md_result, cached_prep, prep_missing_reason
from activesite.trace import Trace

HIS_MEMORY_QUERY = "histidine pka uncertain near ligand cation neutral"
HIS_MEMORY_TAGS = ["protonation", "his-near-cation"]
HIS_RULE = "his_near_cation_neutral"
POCKET_SHIFT_MAX = 1.0   # Å
POCKET_CONTACT_MAX = 4.0  # Å
GMAX_MAX = 10.0


PURE_STAGE_KEYS = ("chain", "chain_source", "chain_table", "extract", "crystal_contacts", "ligand_site")


def _clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, float(x)))


def _site_atom(site: Optional[Dict[str, Any]]) -> Optional[str]:
    return site["atom"] if site else None


def _cache_mismatch(fresh: Dict[str, Any], cached: Dict[str, Any]) -> Optional[str]:
    """Why a cached preparation does not match this run's pure-stage decisions (None when it does).

    Only decisions the cache records are compared; a cache without a ``chain`` or ``ligand_site`` key makes no claim.
    """
    why = []
    if "chain" in cached and cached["chain"] != fresh["chain"]:
        why.append(f"this run chose chain {fresh['chain']}, cache has chain {cached['chain']}")
    if "ligand_site" in cached and _site_atom(cached["ligand_site"]) != _site_atom(fresh["ligand_site"]):
        why.append(f"this run protonates {_site_atom(fresh['ligand_site']) or 'nothing (neutral)'}, "
                   f"cache protonates {_site_atom(cached.get('ligand_site')) or 'nothing (neutral)'}")
    return "; ".join(why) or None


# ---------------------------------------------------------------- LigandSetup
class LigandSetup:
    def __init__(self, recall: Optional[MemoryRetrievalService], trace: Optional[Trace], run_id: str,
                 work: Path | str, sample_mode: bool = False):
        self.recall = recall
        self.trace = trace
        self.run_id = run_id
        self.work = Path(work)
        self.sample_mode = sample_mode

    def _log(self, action: str, inp: Any, out: Any, **kw) -> None:
        if self.trace:
            self.trace.log("LigandSetup", action, inp, out, **kw)

    def build(self, case: Dict[str, Any]) -> Dict[str, Any]:
        self.work.mkdir(parents=True, exist_ok=True)
        pdb, ligand, ph = case["pdb"], case["ligand"], float(case.get("ph", 7.4))
        setup: Dict[str, Any] = {"kind": "ligand", "work": str(self.work), "mask": ":LIG", "theory": "PM6",
                                 "charge": None, "recalled": False, "prep_skipped": None, "overrides": []}

        # chain (pure)
        table = prep.choose_chain(pdb, ligand)
        if case.get("chain"):
            chain, source = str(case["chain"]), "requested"
        else:
            chain, source = table["chain"], "REMARK 465/470 pocket completeness"
        setup.update({"chain": chain, "chain_source": source, "chain_table": table["table"]})
        self._log("choose_chain", f"{Path(pdb).name} ligand {ligand}", f"chain {chain} ({source})",
                  data={"table": table["table"]}, molecule=case.get("system"))

        ext = prep.extract(pdb, chain, ligand, self.work)
        setup["extract"] = ext
        setup["crystal_contacts"] = prep.polar_contacts(self.work)
        self._log("extract", f"chain {chain}", f"{ext['protein_atoms']} protein atoms, {ext['ligand_atoms']} ligand atoms",
                  data={"crystal_polar_contacts": setup["crystal_contacts"]["contacts"][:12]})

        site = prep.ligand_protonation_site(self.work)
        setup["ligand_site"] = site
        self._log("ligand_protonation_site", "tertiary amines vs backbone O",
                  site["evidence"] if site else "no tertiary amine with a backbone-O contact; ligand kept neutral",
                  data={"site": site})

        hits = self.recall.retrieve(HIS_MEMORY_QUERY, tags=HIS_MEMORY_TAGS, actor="LigandSetup", run_id=self.run_id) \
            if self.recall is not None else []
        setup["memory_hits"] = [{"id": h["memory"]["id"], "score": h["score"], "content": h["memory"]["content"][:160]} for h in hits]
        setup["recalled"] = any((h["memory"].get("extra") or {}).get("rule") == HIS_RULE for h in hits)
        self._log("recall", HIS_MEMORY_QUERY, f"{len(hits)} hits, rule recalled: {setup['recalled']}",
                  data={"hits": setup["memory_hits"]})

        # container stages
        if self.sample_mode or not prep.prep_available():
            cached = cached_prep(case.get("id", ""), self.work)
            # The cache is keyed by case id, not by input content. The pure stages above were just recomputed from
            # this run's PDB; keep them (so the cards cite this run's evidence) and refuse the cache when they lead to
            # a different chain or ligand protonation site than the one the cached complex was built for.
            fresh = {k: setup[k] for k in PURE_STAGE_KEYS}
            mismatch = _cache_mismatch(fresh, cached) if cached is not None else None
            if mismatch:
                setup["prep_skipped"] = (f"cached preparation for {case.get('id')} not used: {mismatch}; "
                                         f"the cached complex was built for different setup decisions")
                self._log("prep", "pdb2pqr/antechamber/tleap/sander", setup["prep_skipped"], status="skipped")
                return setup
            if cached is not None:
                recalled, hits_seen = setup["recalled"], setup["memory_hits"]
                setup.update(cached)
                setup.update(fresh)
                setup["recalled"], setup["memory_hits"] = recalled, hits_seen
                setup["prep_skipped"] = None
                self._log("prep", "pdb2pqr/antechamber/tleap/sander",
                          f"loaded cached preparation from {cached['prep_cached']} (no container ran now): charge "
                          f"{setup.get('charge'):+d}, {len(setup.get('overrides') or [])} His overrides, final GMAX "
                          f"{(setup.get('minimisation') or {}).get('last', {}).get('gmax')}", status="cached")
                return setup
            reason = prep_missing_reason(case.get("id", ""))
            if not self.sample_mode:
                reason = reason.replace("SAMPLE_MODE=true and", f"Docker or {prep.PREP_IMAGE} not available and")
            setup["prep_skipped"] = reason
            self._log("prep", "pdb2pqr/antechamber/tleap/sander", setup["prep_skipped"], status="skipped")
            return setup

        prot = prep.protonate(self.work, ph)
        setup["protonation"] = prot
        his = {k: v for k, v in prot["states"].items() if v.startswith("HI")}
        self._log("protonate", f"pdb2pqr + PROPKA at pH {ph}",
                  f"{len(prot['pkas'])} pKa values, His states {his}, {len(prot['gap_warnings'])} gap warnings",
                  data={"states": prot["states"], "gap_warnings": prot["gap_warnings"][:10], "seconds": prot["seconds"]})

        review = prep.review_uncertain(self.work, prot, ph, site["atom"] if site else None)
        setup["his_review"] = review
        setup["overrides"] = review["overrides"]
        self._log("review_uncertain", f"His within {prep.PKA_WINDOW} pKa of pH, ring N within {prep.CATION_RANGE} Å of cation",
                  f"{len(review['overrides'])} overrides: " + "; ".join(o["evidence"] for o in review["overrides"]) if review["overrides"]
                  else f"no override ({len(review['uncertain_his'])} uncertain His, cation {review['cation_atom']})",
                  data=review)

        lig = prep.ligand_parameters(self.work, case["ligand_smiles"], site["atom"] if site else None)
        setup["ligand_parameters"] = lig
        setup["charge"] = int(lig["net_charge"])
        self._log("ligand_parameters", f"GAFF2 + AM1-BCC, protonate {site['atom'] if site else '-'}",
                  f"net charge {lig['net_charge']:+d}, charge sum {lig['charge_sum']:+.4f}, {'cached' if lig['cached'] else f'{lig['seconds']} s'}",
                  data={k: lig[k] for k in ("heavy_atoms", "atoms_with_h", "net_charge", "charge_sum", "charge_residual_spread", "cached", "cache_key", "seconds")})

        built = prep.build_complex(self.work, prot, review["overrides"])
        setup["complex"] = built
        self._log("build_complex", "pdb4amber + tleap ff14SB/gaff2 mbondi2",
                  f"total charge {built['total_charge']}, tleap errors {built['tleap_errors']}, overrides applied {built['overrides_applied']}",
                  data={k: built[k] for k in ("total_charge", "tleap_errors", "tleap_warnings", "overrides_applied", "seconds")})

        mini = prep.minimise(self.work, steps=int(case.get("min_steps", 500)))
        setup["minimisation"] = mini
        self._log("minimise", f"restrained GB, {mini['steps']} steps",
                  f"E {mini['first']['energy']:.1f} -> {mini['last']['energy']:.1f} kcal/mol, GMAX {mini['first']['gmax']:.2f} -> {mini['last']['gmax']:.2f}",
                  data={"first": mini["first"], "last": mini["last"], "seconds": mini["seconds"]})

        setup["pose_built"] = prep.built_pose(self.work, built["rst7"], built["renum"])
        setup["pose_min"] = prep.built_pose(self.work, mini["rst7"], built["renum"])
        for label, pose in (("built", setup["pose_built"]), ("minimised", setup["pose_min"])):
            self._log("built_pose", f"{label} model vs crystal ligand",
                      f"centroid shift {pose['centroid_shift']} Å, RMSD {pose['rmsd']} Å, closest protein heavy atom "
                      f"{pose['closest_protein_heavy_atom']['atom']} at {pose['closest_protein_heavy_atom']['distance']} Å, "
                      f"{len(pose['contacts'])} polar contacts",
                      data={"contacts": pose["contacts"][:15]})
        return setup


# --------------------------------------------------------------- LigandCritic
class LigandCritic:
    def __init__(self, store: Optional[MemoryStoreService], trace: Optional[Trace], run_id: str):
        self.store = store
        self.trace = trace
        self.run_id = run_id

    def precheck(self, setup: Dict[str, Any], expert: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        checks: List[Dict[str, Any]] = []
        if setup.get("prep_skipped"):
            checks.append({"name": "prep_available", "passed": False, "blocking": True, "detail": setup["prep_skipped"], "margin": 0.0})
        else:
            lig = setup["ligand_parameters"]
            diff = abs(float(lig["charge_sum"]) - float(lig["net_charge"]))
            checks.append({"name": "ligand_charge_sum", "passed": diff < 1e-3, "blocking": False,
                           "detail": f"|charge sum {lig['charge_sum']:+.4f} - formal {lig['net_charge']:+d}| = {diff:.2e}",
                           "margin": round(1e-3 - diff, 6)})
            for label in ("built", "min"):
                pose = setup[f"pose_{label}"]
                shift, closest = pose["centroid_shift"], pose["closest_protein_heavy_atom"]["distance"]
                ok = shift < POCKET_SHIFT_MAX and closest < POCKET_CONTACT_MAX
                checks.append({"name": f"pocket_{label}", "passed": ok, "blocking": True,
                               "detail": f"centroid shift {shift} Å (limit {POCKET_SHIFT_MAX}), closest protein heavy atom "
                                         f"{closest} Å (limit {POCKET_CONTACT_MAX})",
                               "margin": round(min(POCKET_SHIFT_MAX - shift, POCKET_CONTACT_MAX - closest), 3)})
            total = setup["complex"]["total_charge"]
            if total is None:
                checks.append({"name": "complex_integer_charge", "passed": False, "blocking": False,
                               "detail": "tleap did not report a total charge", "margin": 0.0})
            else:
                frac = abs(total - round(total))
                checks.append({"name": "complex_integer_charge", "passed": frac < 1e-3, "blocking": False,
                               "detail": f"total charge {total:+.4f}, fraction {frac:.2e}", "margin": round(1e-3 - frac, 6)})
            gmax = setup["minimisation"]["last"]["gmax"]
            checks.append({"name": "minimisation_relaxed", "passed": gmax < GMAX_MAX, "blocking": False,
                           "detail": f"final GMAX {gmax:.3f} kcal/mol/Å (limit {GMAX_MAX})", "margin": round(GMAX_MAX - gmax, 3)})
        if self.trace:
            failed = [c["name"] for c in checks if not c["passed"]]
            blocking = [c["name"] for c in checks if not c["passed"] and c["blocking"]]
            self.trace.log("LigandCritic", "precheck", f"{len(checks)} checks",
                           "all passed" if not failed else f"flagged {failed}" + (f"; BLOCKING {blocking}" if blocking else ""),
                           target_agent="Runner", status="ok" if not failed else ("blocked" if blocking else "flagged"),
                           data={"checks": checks})
        return checks

    @staticmethod
    def blocking(checks: List[Dict[str, Any]]) -> List[str]:
        return [c["name"] for c in checks if not c["passed"] and c.get("blocking")]

    def validate(self, setup: Dict[str, Any], case: Dict[str, Any]) -> Dict[str, Any]:
        contacts = (setup.get("pose_min") or {}).get("contacts") or []
        by_res: Dict[str, float] = {}
        for c in contacts:
            res = c["partner"].split("@")[0]
            by_res[res] = min(by_res.get(res, 99.0), c["distance"])
        literature = case.get("literature_contacts") or {}
        recovered = {r: by_res[r] for r in literature if r in by_res}
        missed = [r for r in literature if r not in by_res]
        absent_expected = case.get("expected_absent") or {}
        absent_ok = {r: r not in by_res for r in absent_expected}
        extra = sorted(r for r in by_res if r not in literature and r not in absent_expected)
        out = {"published": len(literature), "recovered": recovered, "missed": missed, "expected_absent": absent_ok,
               "extra": extra, "contacts": contacts, "available": bool(setup.get("pose_min"))}
        if self.trace:
            self.trace.log("LigandCritic", "validate", f"{len(literature)} published contacts",
                           f"{len(recovered)}/{len(literature)} recovered, missed {missed}, absent as expected "
                           f"{[r for r, ok in absent_ok.items() if ok]}, {len(extra)} extra" if out["available"]
                           else "no minimised model; validation skipped", target_agent="Explainer",
                           confidence=(len(recovered) / len(literature)) if literature and out["available"] else None, data=out)
        return out

    def remember(self, case: Dict[str, Any], setup: Dict[str, Any], qm_ok: bool) -> List[str]:
        """Only when QM/MM succeeded, overrides exist, and no memory was recalled."""
        ids: List[str] = []
        if not (qm_ok and setup.get("overrides") and not setup.get("recalled")) or self.store is None:
            if self.trace:
                self.trace.log("LigandCritic", "remember", f"qm_ok={qm_ok}, overrides={len(setup.get('overrides') or [])}, recalled={setup.get('recalled')}",
                               "nothing stored", target_agent="LigandSetup")
            return ids
        for o in setup["overrides"]:
            content = (f"histidine pka uncertain near ligand cation: HIS{o['resnum']} (PROPKA pKa {o['pka']:.2f}, pH {o['ph']}) "
                       f"faces the ligand cation with {'ND1' if o['to'] == 'HIE' else 'NE2'} at "
                       f"{min(o['d_ND1_cation'], o['d_NE2_cation'])} Å; keep it neutral as {o['to']}. "
                       f"Learned on {case.get('id')}; charged state still worth a sensitivity run.")
            ids.append(self.store.add(content, type="rule", layer="working", tags=HIS_MEMORY_TAGS,
                                      source=f"ligand-critic:qmmm-ok run={self.run_id}", confidence=0.7,
                                      agent_id="LigandCritic", run_id=self.run_id,
                                      extra={"rule": HIS_RULE, "case": case.get("id"), "resnum": o["resnum"], "to": o["to"]}))
        if self.trace:
            self.trace.log("LigandCritic", "remember", f"{len(setup['overrides'])} His overrides after a converged QM/MM",
                           f"stored {ids}", target_agent="LigandSetup", confidence=0.7, data={"memory_ids": ids})
        return ids


# ------------------------------------------------------------------- run_qmmm
def run_qmmm(trace: Optional[Trace], setup: Dict[str, Any], work: Path | str, case_id: str = "",
             sample_mode: bool = False) -> Dict[str, Any]:
    work = Path(work)
    parm7 = Path(setup["complex"]["parm7"])
    coords = Path(setup["minimisation"]["rst7"])
    if sample_mode or not sander.docker_available():
        result = cached_engine_result(case_id, 0, int(setup["charge"]), "PM6")
        if trace:
            trace.log("Runner", "cached_engine_output" if result.get("cached") else "run_qmmm",
                      f"qmcharge {setup['charge']:+d}, mask :LIG",
                      f"replayed {result['sample_source']} (no engine ran now)" if result.get("cached") else "; ".join(result["errors"]),
                      target_agent="LigandCritic", status="cached" if result.get("cached") else "skipped")
        return result
    if trace:
        trace.log("Runner", "run_qmmm", f"qmcharge {setup['charge']:+d}, mask :LIG (whole ligand), GB implicit solvent",
                  f"sander PM6 single point in {sander.ENGINE_IMAGE} -> {work / 'qmmm0'}")
    result = run_single_point(parm7, coords, ":LIG", int(setup["charge"]), work / "qmmm0", "PM6", solvent="gb")
    result["skipped"] = False
    if trace:
        summary = (f"ok ESCF {result['qm_escf_kcal']:.3f} kcal/mol in {result.get('wall_time_s')}s"
                   if result.get("ok") else "FAILED: " + "; ".join(result.get("errors") or ["no energy"]))
        trace.log("Runner", "qmmm_result", "attempt 0", summary, target_agent="LigandCritic",
                  status="ok" if result.get("ok") else "failed",
                  data={k: result.get(k) for k in ("qm_escf_kcal", "total_energy_kcal", "link_atoms", "exit_code", "wall_time_s")})
    return result


# ----------------------------------------------------------------- trajectory
def check_trajectory_stability(
    parm7_path: str | Path,
    traj_path: str | Path,
    contact_pair: Optional[Tuple[str, str]] = None,
    contact_max: float = 4.0,
) -> Dict[str, Any]:
    """Calculate the distance of the primary ligand-protein polar contact across sampled frames.

    Verifies retention of the ligand in the binding pocket by tracking the distance
    between the key ligand polar atom (e.g. Erlotinib N1/N2) and the kinase hinge (e.g. Met769 H/N).
    """
    import numpy as np
    import parmed as pmd

    parm_p = Path(parm7_path).resolve()
    traj_p = Path(traj_path).resolve()

    if not parm_p.exists() or not traj_p.exists():
        return {
            "available": False,
            "ligand_retained": None,
            "mean_distance": None,
            "std_distance": None,
            "min_distance": None,
            "max_distance": None,
            "frames": 0,
            "atom_a": None,
            "atom_b": None,
            "distances": [],
            "error": f"file not found: parm7={parm_p.exists()}, traj={traj_p.exists()}",
        }

    try:
        parm = pmd.load_file(str(parm_p))
    except Exception as e:
        return {"available": False, "ligand_retained": None, "mean_distance": None, "error": str(e)}

    # Load trajectory coordinates
    coords = None
    try:
        if str(traj_p).endswith(".nc"):
            try:
                nc = pmd.amber.NetCDFTraj.open_old(str(traj_p))
                coords = np.array(nc.coordinates)
                nc.close()
            except Exception:
                pass
        if coords is None:
            try:
                crd = pmd.amber.AmberMdcrd.open_old(str(traj_p))
                coords = np.array(crd.coordinates)
                crd.close()
            except Exception:
                loaded = pmd.load_file(str(parm_p), xyz=str(traj_p))
                coords = np.array([loaded.coordinates])
    except Exception as e:
        return {"available": False, "ligand_retained": None, "mean_distance": None, "error": f"failed to load traj: {e}"}

    if coords is None or len(coords) == 0:
        return {"available": False, "ligand_retained": None, "mean_distance": None, "error": "no frames loaded"}

    # Identify ligand atoms and protein partner atoms
    lig_atoms = [a for a in parm.atoms if a.residue.name in ("AQ4", "LIG", "STI", "UNL", "DRG")]
    prot_atoms = [a for a in parm.atoms if a.residue.name not in ("AQ4", "LIG", "STI", "UNL", "DRG", "WAT", "HOH")]

    atom_a = None
    atom_b = None

    if contact_pair:
        sel_a, sel_b = contact_pair
        name_a = sel_a.split("@")[-1].split(":")[-1].strip()
        name_b = sel_b.split("@")[-1].split(":")[-1].strip()

        matched_a = [a for a in lig_atoms if a.name == name_a]
        if not matched_a:
            matched_a = [a for a in lig_atoms if any(a.name.startswith(el) for el in ("N", "O"))]
        if matched_a:
            atom_a = matched_a[0]

        res_b_str = sel_b.split("@")[0].replace(":", "").strip() if "@" in sel_b else ""
        res_b_name = res_b_str[:3].upper() if len(res_b_str) >= 3 else ""
        num_part = res_b_str[3:] if len(res_b_str) > 3 else ""
        res_b_num = int(num_part) if num_part.isdigit() else None

        cands_b = [at for at in prot_atoms if at.name == name_b]
        if res_b_name:
            cands_b_name = [at for at in cands_b if at.residue.name.upper() == res_b_name]
            if res_b_num:
                cands_b_exact = [at for at in cands_b_name if at.residue.number == res_b_num]
                if cands_b_exact:
                    cands_b = cands_b_exact
                elif cands_b_name:
                    cands_b = cands_b_name
            elif cands_b_name:
                cands_b = cands_b_name

        if cands_b and atom_a is not None:
            atom_b = min(cands_b, key=lambda at: float(np.linalg.norm(coords[0][atom_a.idx] - coords[0][at.idx])))
        elif cands_b:
            atom_b = cands_b[0]

    if atom_a is None or atom_b is None:
        best_d = 999.0
        c0 = coords[0]
        lig_polar = [a for a in lig_atoms if any(a.name.startswith(el) for el in ("N", "O"))]
        prot_polar = [a for a in prot_atoms if any(a.name.startswith(el) for el in ("N", "O", "H"))]
        for la in lig_polar:
            for pa in prot_polar:
                d = np.linalg.norm(c0[la.idx] - c0[pa.idx])
                if d < best_d:
                    best_d = d
                    atom_a = la
                    atom_b = pa

    if atom_a is None or atom_b is None:
        return {"available": False, "ligand_retained": None, "mean_distance": None, "error": "no contact pair identified"}

    idx_a = atom_a.idx
    idx_b = atom_b.idx

    distances = [
        round(float(np.linalg.norm(frame[idx_a] - frame[idx_b])), 3)
        for frame in coords
    ]
    mean_d = round(float(np.mean(distances)), 3)
    std_d = round(float(np.std(distances)), 3)
    min_d = round(float(np.min(distances)), 3)
    max_d = round(float(np.max(distances)), 3)
    retained = bool(mean_d < contact_max and max_d < (contact_max + 1.5))

    return {
        "available": True,
        "ligand_retained": retained,
        "mean_distance": mean_d,
        "std_distance": std_d,
        "min_distance": min_d,
        "max_distance": max_d,
        "frames": len(distances),
        "atom_a": f":{atom_a.residue.name}{atom_a.residue.number}@{atom_a.name}",
        "atom_b": f":{atom_b.residue.name}{atom_b.residue.number}@{atom_b.name}",
        "distances": distances,
    }


def simulation_dynamics_card(
    md_res: Dict[str, Any],
    stability: Dict[str, Any],
    steps: int = 1000,
    dt: float = 0.001,
) -> DecisionCard:
    """Emit Track 02 DecisionCard justifying the 1.0 fs time step and 300 K Langevin thermostat."""
    retained = stability.get("ligand_retained")
    mean_d = stability.get("mean_distance")
    pair = f"{stability.get('atom_a')} - {stability.get('atom_b')}" if stability.get("available") else "ligand-hinge contact"

    if md_res.get("skipped"):
        choice = "1.0 fs time step, 300 K Langevin thermostat (gamma_ln=2.0 ps^-1) (offline design; engine skipped in sample mode)"
        conf = 0.85
        evidence = {
            "steps": steps,
            "dt_ps": dt,
            "total_time_ps": steps * dt,
            "temperature_k": 300.0,
            "gamma_ln": 2.0,
            "mean_contact_distance_angstrom": None,
            "ligand_retained": None,
            "engine": "skipped",
            "source": "design specification (SAMPLE_MODE=true)",
        }
    else:
        suffix = " (cached engine output)" if md_res.get("cached") else ""
        choice = (
            f"1.0 fs time step, 300 K Langevin thermostat (gamma_ln=2.0 ps^-1); "
            f"ligand retained={retained} (mean contact distance {mean_d} Å){suffix}"
        )
        conf = 0.95 if retained else 0.40
        evidence = {
            "steps": steps,
            "dt_ps": dt,
            "total_time_ps": steps * dt,
            "temperature_k": 300.0,
            "gamma_ln": 2.0,
            "mean_contact_distance_angstrom": mean_d,
            "std_contact_distance_angstrom": stability.get("std_distance"),
            "contact_atom_pair": pair,
            "ligand_retained": retained,
            "final_temperature_k": md_res.get("final_temperature_k"),
            "rms_temp_k": (md_res.get("rms_fluctuations") or {}).get("temp_k"),
            "source": f"Amber sander QM/MM MD in activesite-engine:at26{suffix}",
        }

    return DecisionCard(
        decision_id="DEC_SIMULATION_DYNAMICS_1PS",
        category=DecisionCategory.SIMULATION_DYNAMICS,
        target="QM/MM molecular dynamics (1 ps, 1000 steps)",
        choice=choice,
        alternatives=[
            AlternativeChoice(
                name="2.0 fs time step with SHAKE on QM atoms",
                rejected_reason="SHAKE on QM atoms risks orbital discontinuities and SCF non-convergence during high-frequency bond vibrations; 1.0 fs preserves unconstrained X-H stretches safely",
            ),
            AlternativeChoice(
                name="NVE microcanonical ensemble without thermostat",
                rejected_reason="Energy exchange across the QM/MM boundary in implicit solvent requires stochastic Langevin bath coupling (gamma_ln=2.0 ps^-1) to prevent temperature drift",
            ),
        ],
        rationale=(
            "A 1.0 fs time step prevents vibrational divergence in the unconstrained QM region without "
            "requiring SHAKE algorithms on quantum atoms. The 300 K Langevin thermostat (gamma_ln=2.0 ps^-1) "
            "maintains canonical thermal distribution while implicit solvent (GB) provides continuous dielectric screening."
        ),
        confidence=conf,
        evidence=evidence,
    )


def run_qmmm_md_workflow(
    trace: Optional[Trace],
    setup: Dict[str, Any],
    work: Path | str,
    case_id: str = "",
    sample_mode: bool = False,
    steps: int = 1000,
    dt: float = 0.001,
) -> Tuple[Dict[str, Any], Dict[str, Any], DecisionCard]:
    """Execute or load the 1 ps QM/MM MD demonstration, evaluate stability, and emit DecisionCard."""
    work = Path(work)
    parm7 = Path(setup["complex"]["parm7"])
    rst7 = Path(setup["minimisation"]["rst7"])

    if sample_mode or not sander.docker_available():
        md_res = cached_md_result(case_id, int(setup["charge"]), "PM6")
        if md_res.get("cached"):
            cached_files = cached_md(case_id, work)
            if cached_files:
                if cached_files.get("traj"):
                    md_res["traj"] = cached_files["traj"]
                if cached_files.get("complex_pdb"):
                    md_res["complex_pdb"] = cached_files["complex_pdb"]
                if cached_files.get("trajectory_cxc"):
                    md_res["trajectory_cxc"] = cached_files["trajectory_cxc"]
        if trace:
            trace.log("Runner", "cached_md_output" if md_res.get("cached") else "run_qmmm_md",
                      f"qmcharge {setup['charge']:+d}, mask :LIG, steps {steps}",
                      f"replayed {md_res['sample_source']}" if md_res.get("cached") else "; ".join(md_res["errors"]),
                      target_agent="LigandCritic", status="cached" if md_res.get("cached") else "skipped")
    else:
        if trace:
            trace.log("Runner", "run_qmmm_md",
                      f"qmcharge {setup['charge']:+d}, mask :LIG, steps {steps}, dt {dt} ps",
                      f"sander PM6 QM/MM MD in {sander.ENGINE_IMAGE} -> {work / 'md'}")
        md_res = run_qmmm_md(work / "md", parm7, rst7, ":LIG", int(setup["charge"]), theory="PM6", steps=steps, dt=dt)
        md_res["skipped"] = False
        if trace:
            summary = (f"ok T_final {md_res.get('final_temperature_k')} K in {md_res.get('wall_time_s')}s"
                       if md_res.get("ok") else "FAILED: " + "; ".join(md_res.get("errors") or ["no MD output"]))
            trace.log("Runner", "md_result", "1 ps MD", summary, target_agent="LigandCritic",
                      status="ok" if md_res.get("ok") else "failed",
                      data={k: md_res.get(k) for k in ("final_temperature_k", "steps_completed", "exit_code", "wall_time_s")})

    # Generate ChimeraX script with complex.pdb and format amber structureModel #1
    from activesite.chem.chimerax import ChimeraXGenerator
    cxc_file = work / "md" / "trajectory.cxc"
    traj_path = md_res.get("traj") or (work / "md" / "traj.nc")
    ChimeraXGenerator().generate_trajectory_script(
        parm7, traj_path, ligand_resname=setup.get("ligand", "AQ4"), output_script_path=cxc_file, rst7_path=rst7
    )
    md_res["chimerax_script"] = str(cxc_file)

    # Stability analysis
    if traj_path and Path(traj_path).exists():
        stability = check_trajectory_stability(parm7, traj_path)
    else:
        if rst7.exists():
            stability = check_trajectory_stability(parm7, rst7)
            stability["available"] = False  # single-point/minimized frame only
        else:
            stability = {"available": False, "ligand_retained": None, "mean_distance": None}

    card = simulation_dynamics_card(md_res, stability, steps=steps, dt=dt)
    return md_res, stability, card


# --------------------------------------------------------------- ligand_cards
def ligand_cards(case: Dict[str, Any], setup: Dict[str, Any], checks: List[Dict[str, Any]], res: Dict[str, Any],
                 val: Dict[str, Any], data: Dict[str, Any]) -> List[DecisionCard]:
    cards: List[DecisionCard] = []
    label = data.get("label", "no-catalog")
    pdb_name = Path(case["pdb"]).name

    rows = setup["chain_table"]
    best = next((r for r in rows if r["chain"] == setup["chain"]), rows[0])
    others = [r for r in rows if r["chain"] != setup["chain"]]
    cards.append(DecisionCard(
        decision_id=f"DEC_CHAIN_{setup['chain']}", category=DecisionCategory.RESIDUE_INCLUSION, target="chain",
        choice=f"chain {setup['chain']} ({setup['chain_source']})",
        alternatives=[AlternativeChoice(name=f"chain {r['chain']}", rejected_reason=f"score {r['score'][:3]} (gaps, missing-atom residues, missing residues)") for r in others],
        rationale=f"{best['pocket_residues']} CA within 12 Å of the ligand; {best['gaps_adjacent_to_pocket']} gaps adjacent, "
                  f"{len(best['missing_atom_residues_in_pocket'])} residues with missing atoms in the pocket, {best['missing_residues']} missing residues in the chain",
        confidence=round(_clamp(1 - (best["gaps_adjacent_to_pocket"] + len(best["missing_atom_residues_in_pocket"])) / max(1, best["pocket_residues"]) * 5), 3),
        evidence={"table": rows, "source": f"REMARK 465/470 of {pdb_name}"},
    ))
    if setup.get("protonation"):
        prot = setup["protonation"]
        his = {f"HIS{k}": v for k, v in prot["states"].items() if v.startswith("HI")}
        n_uncertain = len((setup.get("his_review") or {}).get("uncertain_his") or [])
        cards.append(DecisionCard(
            decision_id="DEC_PROTONATION_PDB2PQR", category=DecisionCategory.PROTONATION_STATE, target="protein protonation",
            choice=f"PDB2PQR + PROPKA at pH {prot['ph']}: {len(prot['states'])} non-default states, His {his}",
            rationale=f"{len(prot['pkas'])} titratable groups predicted; {n_uncertain} His within {prep.PKA_WINDOW} pKa of the pH",
            confidence=round(_clamp(1 - n_uncertain / max(1, len(his))), 3),
            evidence={"states": prot["states"], "pkas": prot["pkas"], "gap_warnings": prot["gap_warnings"], "source": f"pdb2pqr/propka in {prep.PREP_IMAGE}"},
        ))
    for o in setup.get("overrides") or []:
        margin = prep.PKA_WINDOW - abs(o["pka"] - o["ph"])
        cards.append(DecisionCard(
            decision_id=f"DEC_HIS_OVERRIDE_{o['resnum']}", category=DecisionCategory.PROTONATION_STATE, target=f"HIS{o['resnum']}",
            choice=f"{o['from']} -> {o['to']} (sensitivity run advised)",
            alternatives=[AlternativeChoice(name="HIP (charged)", rejected_reason=f"pKa {o['pka']:.2f} is within {prep.PKA_WINDOW} of pH {o['ph']}; a cation {min(o['d_ND1_cation'], o['d_NE2_cation'])} Å away disfavours a second positive charge")],
            rationale=o["evidence"] + (" (recalled from memory)" if setup.get("recalled") else ""),
            confidence=round(_clamp(0.2 + 0.2 * (1 - margin / prep.PKA_WINDOW)), 3),
            evidence={k: o[k] for k in ("pka", "ph", "d_ND1_cation", "d_NE2_cation")} | {"source": "PROPKA pKa + ligand geometry" + (" + H-MEM" if setup.get("recalled") else "")},
        ))
    site = setup.get("ligand_site")
    if site:
        c0 = site["contacts"][0]
        cards.append(DecisionCard(
            decision_id=f"DEC_LIGAND_PROTONATION_{site['atom']}", category=DecisionCategory.PROTONATION_STATE, target=f"ligand {site['atom']}",
            choice=f"protonate {site['atom']} (+1)",
            alternatives=[AlternativeChoice(name="neutral ligand", rejected_reason=f"tertiary amine with a backbone carbonyl at {c0['distance']} Å indicates a salt bridge")],
            rationale=site["evidence"], confidence=round(_clamp(0.5 + 0.5 * (HBOND - c0["distance"]) / HBOND), 3),
            evidence={"contacts": site["contacts"], "checked": [e["atom"] for e in site["checked"]], "source": "crystal geometry"},
        ))
    else:
        cards.append(DecisionCard(
            decision_id="DEC_LIGAND_NEUTRAL", category=DecisionCategory.PROTONATION_STATE, target="ligand",
            choice="kept neutral", rationale="no tertiary amine (N with three C neighbours) has a backbone O within 3.3 Å",
            confidence=0.8, evidence={"source": "crystal geometry", "rule": "tertiary amine + backbone O < 3.3 Å"},
        ))
    if setup.get("ligand_parameters"):
        lig = setup["ligand_parameters"]
        cards.append(DecisionCard(
            decision_id="DEC_LIGAND_PARAMETERS", category=DecisionCategory.THEORY_SELECTION, target="ligand force field",
            choice=f"GAFF2 + AM1-BCC, net charge {lig['net_charge']:+d}" + (" (cached)" if lig["cached"] else f" ({lig['seconds']} s)"),
            rationale=f"charge sum {lig['charge_sum']:+.4f}, residual spread {lig['charge_residual_spread']:+.4f} e over {lig['ligand_atoms']} atoms",
            confidence=round(_clamp(1 - abs(lig["charge_residual_spread"]) / 0.01), 3),
            evidence={k: lig[k] for k in ("charge_sum", "charge_residual_spread", "ligand_atoms", "cached", "cache_key")} | {"source": "antechamber/parmchk2"},
        ))
    cards.append(DecisionCard(
        decision_id="DEC_QM_REGION_LIGAND", category=DecisionCategory.LINK_ATOM, target="QM region",
        choice="whole ligand (:LIG), no link atoms",
        alternatives=[AlternativeChoice(name="ligand + pocket side chains", rejected_reason="covalent cuts add link atoms and PM6 cost; the question is the ligand's energy in its pocket")],
        rationale="a closed-shell whole ligand needs no boundary treatment",
        confidence=round(_clamp(1 - (res.get("link_atoms") or 0) / 4), 3), evidence={"mask": ":LIG", "link_atoms": res.get("link_atoms"), "source": "setup"},
    ))
    cards.append(DecisionCard(
        decision_id="DEC_SOLVENT_GB", category=DecisionCategory.SOLVENT_HANDLING, target="solvent",
        choice="implicit solvent (igb=5, mbondi2) for the QM/MM single point",
        alternatives=[AlternativeChoice(name="explicit TIP3P box + PME", rejected_reason="hours of equilibration; crystal waters (incl. the Thr766 bridge) are removed either way")],
        rationale="trade-off: fast and judge-runnable, but bridging waters and bulk screening are approximated",
        confidence=0.5, evidence={"igb": 5, "cut": 999.0, "source": "design choice"},
    ))
    for c in checks:
        cards.append(DecisionCard(
            decision_id=f"DEC_CHECK_{c['name'].upper()}", category=DecisionCategory.CRITIC_CORRECTION, target=c["name"],
            choice=("passed: " if c["passed"] else "flagged: ") + c["detail"], rationale="LigandCritic precheck" + (" (blocking)" if c.get("blocking") else ""),
            confidence=round(_clamp(0.5 + 0.5 * _clamp(c["margin"])), 3) if c["passed"] else 0.0,
            evidence={"margin": c["margin"], "passed": c["passed"], "blocking": c.get("blocking", False), "source": "LigandCritic.precheck"},
        ))
    if val.get("available"):
        n, m = len(val["recovered"]), val["published"]
        cards.append(DecisionCard(
            decision_id="DEC_BINDING_MODE", category=DecisionCategory.VALIDATION, target="binding mode",
            choice=f"{n}/{m} published contacts present",
            rationale="; ".join(f"{r} at {d:.2f} Å ({(case.get('literature_contacts') or {}).get(r, '')})" for r, d in val["recovered"].items())
                      + (f"; missed {val['missed']}" if val["missed"] else ""),
            confidence=round(_clamp(n / m) if m else 0.0, 3),
            evidence={"recovered": val["recovered"], "missed": val["missed"], "extra": val["extra"], "source": f"minimised model polar contacts, literature {case.get('literature_source', '')}"},
        ))
        for r, ok in val["expected_absent"].items():
            cards.append(DecisionCard(
                decision_id=f"DEC_NEGATIVE_CONTROL_{r}", category=DecisionCategory.VALIDATION, target=r,
                choice=f"{r} contact absent: {ok}", rationale=(case.get("expected_absent") or {}).get(r, ""),
                confidence=1.0 if ok else 0.0, evidence={"absent": ok, "source": "minimised model polar contacts"},
            ))
    if data.get("pdb"):
        rows = data["pdb"]
        cards.append(DecisionCard(
            decision_id="DEC_STRUCTURE_SOURCE", category=DecisionCategory.VALIDATION, target="structure source",
            choice=f"{rows[0].get('pdb_id')} at {rows[0].get('resolution')} Å (best of {len(rows)} entries)",
            rationale=f"Q3 ordered by resolution via {label}", confidence=round(_clamp(1 / max(1.0, float(rows[0].get('resolution') or 1.0))), 3),
            evidence={"rows": rows[:5], "sql": data["sql"]["q3_pdb"], "source": label},
        ))
    return cards
