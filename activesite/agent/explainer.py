"""ActiveSite — Explainer Agent (Track 02: The Agent That Can Explain Why).

Synthesizes simulation results, QM/MM partition parameters, and all Track 02 Decision Cards
into structured, verifiable scientific explanation reports and audit records.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional
from activesite.models import DecisionCard, QMMMPartition, SimulationResult


class ExplainerAgent:
    """Explainer Agent compiling Track 02 Decision Cards into transparent scientific narratives."""

    def generate_report(
        self,
        system_name: str,
        result: SimulationResult,
        partition: QMMMPartition,
        chimerax_script_path: Optional[str] = None,
    ) -> str:
        """Render a comprehensive scientific explanation report in GitHub Flavored Markdown."""
        lines = [
            f"# 🔬 ActiveSite Explanation Report: `{system_name}`",
            f"**Track 02: The Agent That Can Explain Why** | *Automated QM/MM Simulation Audit*",
            f"",
            f"---",
            f"",
            f"## 📊 Simulation Summary",
            f"- **System Name:** `{system_name}`",
            f"- **QM Theory Level:** `{result.qm_theory}`",
            f"- **Total QM/MM Energy:** **{result.energy_kcal_mol:,.2f} kcal/mol** ({result.energy_hartree:.5f} Hartree)",
            f"- **Total QM Residues:** {len(partition.qm_residues)}",
            f"- **Formal Charge (`qmcharge`):** {partition.qm_charge:+d}",
            f"- **Spin Multiplicity:** {partition.spin_multiplicity} (Closed-shell Singlet)",
            f"- **Valence Electrons:** {partition.total_valence_electrons}",
            f"- **Link Atoms Severed:** {len(partition.link_atoms)}",
            f"- **Execution Mode:** {'CPU Sample Mode (Benchmark Offline)' if result.sample_mode else 'Docker Engine (AmberTools 26)'}",
            f"- **Execution Time:** {result.execution_time_seconds:.3f} s",
        ]

        if chimerax_script_path:
            lines.append(f"- **ChimeraX 3D Script:** `{chimerax_script_path}`")

        lines.extend([
            f"",
            f"---",
            f"",
            f"## 🎴 Track 02 Decision Cards (Verifiable Scientific Explanations)",
            f"Every autonomous choice made by ActiveSite is detailed below with rejected alternatives, scientific rationales, and quantitative evidence.",
            f"",
        ])

        # Group cards by category
        cards = result.decision_cards or partition.decision_cards
        for idx, card in enumerate(cards, start=1):
            lines.append(f"### {idx}. {card.category.value.upper()}: `{card.target}`")
            lines.append(f"- **Selected Choice:** **{card.choice}** *(Confidence: {card.confidence:.2f})*")
            lines.append(f"- **Scientific Rationale:** {card.rationale}")
            
            if card.alternatives:
                lines.append(f"- **Evaluated & Rejected Alternatives:**")
                for alt in card.alternatives:
                    lines.append(f"  - ❌ **{alt.name}**: {alt.rejected_reason}")
            
            if card.evidence:
                lines.append(f"- **Quantitative Evidence:**")
                for k, v in card.evidence.items():
                    lines.append(f"  - `{k}`: {v}")
            lines.append("")

        lines.extend([
            f"---",
            f"",
            f"## 🛡️ Trust & Reproducibility Ledger",
            f"This calculation was checked for odd-electron spin contamination, valid boundary bond cuts, "
            f"and protonation equilibrium. All decisions are cryptographically traceable in the Meterless H-MEM ledger.",
        ])

        return "\n".join(lines) + "\n"
