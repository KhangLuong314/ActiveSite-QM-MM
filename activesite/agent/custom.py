"""Custom runs on user-uploaded structures: build a ligand case dict on the fly and explain its provenance.

The case goes through the normal ligand loop (``run_ligand_case``): chain choice, protonation, ligand protonation,
GAFF2/AM1-BCC parameters, tleap complex, minimisation, LigandCritic precheck, PM6 single point. A custom case never
replays cached sample output: in SAMPLE_MODE (or without Docker) the engine does not run, energies are null and the
run is labelled PROPOSAL_LABEL.

Metal-only uploads are refused (METAL_UNSUPPORTED): the metal QM-region rules (activesite.chem.qmregion /
partitioning) work on an Amber topology with MM charges, and there is no step yet that builds one from an uploaded PDB.
"""
from __future__ import annotations

import re

from typing import Any, Dict, List, Optional

from activesite.adapters.chemcomp import SMILES_RE, lookup_smiles
from activesite.chem.uploads import CHAIN_RE, RESNAME_RE, UploadError, load_record, structure_file
from activesite.models import AlternativeChoice, DecisionCard, DecisionCategory

PROPOSAL_LABEL = "proposal only: engine not run (sample mode)"
METAL_UNSUPPORTED = ("metal sites from uploaded files: QM-region proposal not supported yet (the metal QM-region rules "
                     "need an Amber topology with MM charges, which is not built from uploads yet); upload a structure "
                     "with a ligand, or use the I-PpoI metal cases")


def build_custom_case(spec: Dict[str, Any], lookup=lookup_smiles) -> Dict[str, Any]:
    """Validate a custom-run request and return the ligand case dict. Raises UploadError with a user-facing message."""
    sid = spec.get("structure_id")
    record = load_record(sid)
    path, fmt = structure_file(sid)
    if fmt != "pdb" or not record.get("runnable", True):
        raise UploadError("this structure is stored as mmCIF only (it could not be written as PDB); it cannot be run")
    chain = spec.get("chain")
    if chain is not None and not (isinstance(chain, str) and CHAIN_RE.match(chain)):
        raise UploadError("chain must be a single letter or digit")
    try:
        ph = float(spec.get("ph", 7.4) if spec.get("ph") is not None else 7.4)
    except (TypeError, ValueError):
        raise UploadError("ph must be a number")
    if not 0.0 <= ph <= 14.0:
        raise UploadError("ph must be between 0 and 14")
    # the user's own question (free text from the composer): display/report text only, never parsed or executed
    user_q = " ".join(re.sub(r"[\x00-\x1f\x7f]", " ", str(spec.get("question") or "")).split())
    if len(user_q) > 500:
        raise UploadError("the question is longer than 500 characters")
    resname = spec.get("ligand_resname")
    ligands = record.get("ligands") or []
    picked_automatically = False
    if resname is None:
        if spec.get("metal_resi") is not None:
            raise UploadError(METAL_UNSUPPORTED, status=422)
        names = sorted({lg["resname"] for lg in ligands})
        if len(names) != 1:
            raise UploadError("give ligand_resname: the structure has " +
                              (f"several ligand candidates {names}" if names else "no ligand candidate"))
        resname, picked_automatically = names[0], True
    if not isinstance(resname, str) or not RESNAME_RE.match(resname):
        raise UploadError("ligand_resname must be 1-3 uppercase letters or digits (a PDB residue name)")
    copies = [lg for lg in ligands if lg["resname"] == resname and (chain is None or lg["chain"] == chain)]
    if not copies:
        additive = any(a["resname"] == resname for a in record.get("additives") or [])
        raise UploadError(f"no ligand {resname}" + (f" in chain {chain}" if chain else "") + " in this structure" +
                          (f" ({resname} is a buffer/cryo additive)" if additive else ""))
    per_chain: Dict[str, int] = {}
    for lg in copies:
        per_chain[lg["chain"]] = per_chain.get(lg["chain"], 0) + 1
    multi = [c for c, n in per_chain.items() if n > 1]
    if multi and (chain is None or chain in multi):
        raise UploadError(f"ligand {resname} occurs more than once in chain {multi[0]}; selecting one copy is not "
                          f"supported yet" + ("" if chain else "; pass another chain if it has a single copy"))
    smiles = spec.get("ligand_smiles")
    if smiles:
        if not isinstance(smiles, str) or not SMILES_RE.match(smiles):
            raise UploadError("ligand_smiles contains characters that are not valid in SMILES")
        smiles_source = "user"
    else:
        try:
            smiles, smiles_source = lookup(resname)
        except LookupError as exc:
            raise UploadError(f"{exc}. Send ligand_smiles with the request.")
    short = sid[:12]
    name = record["name"]
    mutations = record.get("mutations_applied") or []
    provenance = {"structure_id": sid, "name": name, "root_name": record.get("root_name") or name,
                  "parent_id": record.get("parent_id"), "mutations": mutations, "method": record.get("method"),
                  "smiles": smiles, "smiles_source": smiles_source, "ligand_resname": resname,
                  "ligand_picked_automatically": picked_automatically, "format": record.get("format"),
                  "upload_warnings": record.get("warnings") or [], "user_question": user_q or None}
    return {
        "id": f"custom_{short}", "kind": "ligand", "system": f"custom_{short}", "site": "A", "chain": chain,
        "question": (f"{user_q} " if user_q else "") + (f"Prepare your uploaded structure {name}" + (f" (mutations {', '.join(mutations)})" if mutations else "")
                     + f" with ligand {resname} and compute the PM6 QM/MM energy of the ligand in its pocket at pH {ph}. "
                       "Explain every protonation and setup choice."),
        "pdb": str(path), "ligand": resname, "ligand_smiles": smiles, "smiles_source": smiles_source,
        "literature_contacts": {}, "expected_absent": {}, "ph": ph, "min_steps": 500, "custom": provenance,
    }


def custom_cards(case: Dict[str, Any], setup: Dict[str, Any], result: Dict[str, Any], val: Dict[str, Any],
                 sample_mode: bool) -> List[DecisionCard]:
    """Provenance cards for a custom run (structure, mutations, SMILES source, engine status, contacts)."""
    p = case["custom"]
    cards: List[DecisionCard] = []
    muts = p.get("mutations") or []
    cards.append(DecisionCard(
        decision_id="DEC_CUSTOM_STRUCTURE", category=DecisionCategory.VALIDATION, target="structure source",
        choice=f"your uploaded structure {p['name']}" + (f" (mutant of {p['root_name']}: {', '.join(muts)})" if muts else ""),
        alternatives=[AlternativeChoice(name="a published benchmark case", rejected_reason="you asked for your own structure; "
                                        "no literature contacts exist for it, so binding-mode validation is limited to geometry")],
        rationale=f"uploaded as {p['format']}, stored server-side as structure {p['structure_id']}; "
                  + ("; ".join(p.get("upload_warnings") or []) or "no upload warnings"),
        confidence=0.5 if p.get("upload_warnings") else 0.8,
        evidence={"structure_id": p["structure_id"], "parent_id": p.get("parent_id"), "warnings": p.get("upload_warnings"),
                  "source": "user upload (untrusted input, validated on upload)"},
    ))
    for tok in muts:
        cards.append(DecisionCard(
            decision_id=f"DEC_MUTATION_{tok.replace(':', '_')}", category=DecisionCategory.RESIDUE_INCLUSION, target=f"mutation {tok}",
            choice=f"{tok} by template rebuild (no rotamer search, no repacking)",
            alternatives=[AlternativeChoice(name="rotamer-library placement + neighbour repacking (e.g. SCWRL4, Rosetta)",
                                            rejected_reason="not available in the pinned containers; the rebuilt side chain "
                                                            "takes template geometry and only the restrained minimisation relaxes it")],
            rationale=p.get("method") or "template rebuild",
            confidence=0.4,
            evidence={"mutation": tok, "rebuild": "PDB2PQR missing-heavy-atom repair, then tleap ff14SB template",
                      "source": "activesite.chem.uploads.mutate"},
        ))
    cards.append(DecisionCard(
        decision_id="DEC_LIGAND_SMILES_SOURCE", category=DecisionCategory.CHARGE_AND_SPIN, target=f"ligand {p['ligand_resname']} chemistry",
        choice=f"SMILES from {'you (user-supplied)' if p['smiles_source'] == 'user' else p['smiles_source']}: {p['smiles']}",
        alternatives=[AlternativeChoice(name="bond orders guessed from crystal geometry",
                                        rejected_reason="PDB coordinates carry no bond orders or charges; guessing them silently "
                                                        "changes the formal charge and so the QM charge")],
        rationale="the SMILES fixes bond orders and formal charge; RDKit assigns them to the uploaded ligand atoms"
                  + ("; the ligand residue was picked automatically (the only ligand candidate)" if p.get("ligand_picked_automatically") else ""),
        confidence=0.9 if p["smiles_source"] == "user" or "RCSB" in p["smiles_source"] else 0.5,
        evidence={"smiles": p["smiles"], "source": p["smiles_source"]},
    ))
    if result.get("ok"):
        engine = f"sander PM6 single point ran: ESCF {result['qm_escf_kcal']:.4f} kcal/mol"
    elif sample_mode:
        engine = PROPOSAL_LABEL + "; energies are null"
    else:
        engine = "engine did not produce an energy: " + "; ".join(result.get("errors") or ["unknown"])
    cards.append(DecisionCard(
        decision_id="DEC_CUSTOM_ENGINE", category=DecisionCategory.VALIDATION, target="engine status",
        choice=engine,
        rationale="uploaded structures are never replayed from cached sample output; only a live Docker run gives numbers",
        confidence=1.0, evidence={"sample_mode": sample_mode, "qm_escf_kcal": result.get("qm_escf_kcal"),
                                  "source": "Runner"},
    ))
    if val.get("available"):
        contacts = sorted(val.get("contacts") or [], key=lambda c: c["distance"])
        cards.append(DecisionCard(
            decision_id="DEC_CUSTOM_CONTACTS", category=DecisionCategory.VALIDATION, target="binding mode",
            choice=f"{len(contacts)} polar ligand-protein contacts in the minimised model",
            rationale="; ".join(f"{c['ligand_atom']}-{c['partner']} {c['distance']:.2f} Å" for c in contacts[:10]) or "none",
            confidence=0.5,
            evidence={"contacts": contacts[:20], "source": "minimised model polar contacts (no literature reference for an uploaded structure)"},
        ))
    return cards


def merge_cards(case: Dict[str, Any], cards: List[DecisionCard], extra: List[DecisionCard]) -> List[DecisionCard]:
    """Provenance cards first; drop the literature binding-mode card (0/0 published contacts says nothing)."""
    kept = [c for c in cards if c.decision_id != "DEC_BINDING_MODE"]
    return extra + kept


def engine_label(result: Dict[str, Any], sample_mode: bool, default: str) -> str:
    if not result.get("ok") and sample_mode:
        return PROPOSAL_LABEL
    return default


def custom_summary(case: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    p = case.get("custom")
    if not p:
        return None
    return {k: p.get(k) for k in ("structure_id", "name", "root_name", "parent_id", "mutations", "ligand_resname",
                                  "smiles", "smiles_source", "ligand_picked_automatically")}
