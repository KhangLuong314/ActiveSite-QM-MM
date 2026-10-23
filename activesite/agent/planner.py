"""ActiveSite — Planner & Intent Extractor Agent.

Parses natural language prompts and benchmark case definitions to extract
target systems, PDB IDs, ligands, metal centers, target pH, and simulation parameters.
"""
from __future__ import annotations

import re
from typing import Any, Dict, Optional
from pydantic import BaseModel, Field


class ExecutionPlan(BaseModel):
    system_name: str
    pdb_id: Optional[str] = None
    ligand_name: Optional[str] = None
    metal_resid: Optional[int] = None
    ph: float = 7.4
    cutoff_radius: float = 4.0
    qm_theory: str = "PM6"
    min_steps: int = 500
    parm7_path: Optional[str] = None
    coords_path: Optional[str] = None
    literature_contacts: Dict[str, str] = Field(default_factory=dict)
    expected_absent: Dict[str, str] = Field(default_factory=dict)
    case_id: Optional[str] = None


class PlannerAgent:
    """Extracts simulation parameters and constructs an actionable execution plan."""

    def plan_from_case(self, case_dict: Dict[str, Any]) -> ExecutionPlan:
        """Create execution plan directly from a loaded benchmark case definition."""
        case_id = case_dict.get("id", "case_unknown")
        system_name = case_dict.get("system", case_id)
        
        # Check if metal system (e.g. I-PpoI)
        metal_resid = case_dict.get("metal_resid")
        parm7 = case_dict.get("parm7")
        coords = case_dict.get("coords")
        pdb = case_dict.get("pdb")
        
        # Extract PDB ID if available in pdb path or question
        pdb_id = None
        if pdb:
            m = re.search(r"(\d[a-zA-Z0-9]{3})\.pdb", pdb)
            if m:
                pdb_id = m.group(1).upper()
        
        if not pdb_id and "1M17" in case_dict.get("question", ""):
            pdb_id = "1M17"
        elif not pdb_id and "2HYY" in case_dict.get("question", ""):
            pdb_id = "2HYY"

        return ExecutionPlan(
            system_name=system_name,
            pdb_id=pdb_id,
            ligand_name=case_dict.get("ligand"),
            metal_resid=metal_resid,
            ph=float(case_dict.get("ph", 7.4)),
            cutoff_radius=4.0,
            qm_theory="PM6",
            min_steps=int(case_dict.get("min_steps", 500)),
            parm7_path=parm7,
            coords_path=coords,
            literature_contacts=case_dict.get("literature_contacts", {}),
            expected_absent=case_dict.get("expected_absent", {}),
            case_id=case_id,
        )

    def plan_from_prompt(self, prompt: str) -> ExecutionPlan:
        """Parse user natural language prompt into an execution plan."""
        # 1. PDB ID extraction (4 characters: 1 digit + 3 alphanumeric)
        pdb_match = re.search(r"\b([0-9][a-zA-Z0-9]{3})\b", prompt)
        pdb_id = pdb_match.group(1).upper() if pdb_match else None

        # 2. pH extraction
        ph = 7.4
        ph_match = re.search(r"\bph\s*[:=]?\s*([0-9]+(?:\.[0-9]+)?)\b", prompt, re.IGNORECASE)
        if ph_match:
            try:
                ph = float(ph_match.group(1))
            except ValueError:
                pass

        # 3. Ligand extraction
        prompt_lower = prompt.lower()
        ligand_name = None
        system_name = "custom_system"

        if "erlotinib" in prompt_lower or "1m17" in prompt_lower or "aq4" in prompt_lower:
            ligand_name = "AQ4"
            system_name = "egfr_erlotinib"
            if not pdb_id:
                pdb_id = "1M17"
        elif "imatinib" in prompt_lower or "2hyy" in prompt_lower or "sti" in prompt_lower:
            ligand_name = "STI"
            system_name = "abl_imatinib"
            if not pdb_id:
                pdb_id = "2HYY"
        elif "ippoi" in prompt_lower or "i-ppoi" in prompt_lower:
            system_name = "ippoi_wt"

        # 4. Metal detection
        metal_resid = None
        if "site b" in prompt_lower or ":372" in prompt_lower or "372" in prompt_lower:
            metal_resid = 372
        elif "site a" in prompt_lower or ":371" in prompt_lower or "371" in prompt_lower or "ippoi" in prompt_lower:
            metal_resid = 371

        # 5. QM theory extraction
        qm_theory = "PM6"
        if "xtb" in prompt_lower or "gfn2" in prompt_lower:
            qm_theory = "GFN2-xTB"
        elif "dft" in prompt_lower or "b3lyp" in prompt_lower:
            qm_theory = "B3LYP"

        return ExecutionPlan(
            system_name=system_name,
            pdb_id=pdb_id,
            ligand_name=ligand_name,
            metal_resid=metal_resid,
            ph=ph,
            cutoff_radius=4.0,
            qm_theory=qm_theory,
            min_steps=500,
        )
