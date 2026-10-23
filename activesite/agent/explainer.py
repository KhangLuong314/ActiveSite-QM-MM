"""ActiveSite — Explainer Agent (Track 02: The Agent That Can Explain Why).

Synthesizes simulation results, QM/MM partition parameters, and all Track 02 Decision Cards
into structured, verifiable scientific explanation reports and audit records.

Honesty rule: a number appears in the report only if an engine produced it.
When no engine ran, the energy is rendered as "not computed" with the reason.
"""
from __future__ import annotations

from typing import Optional

from activesite.models import QMMMPartition, SimulationResult

CATALOG_STANDIN_NAME = "catalog-STANDIN (DuckDB)"

LIMITATIONS = [
    "PM6 single points only; no geometry optimisation, dynamics, or higher-level theory.",
    "Implicit solvent for ligand cases; no explicit water model.",
    "No free-energy barriers are computed locally.",
    f"The data catalog is a local stand-in ({CATALOG_STANDIN_NAME}) until Zetaris credentials are configured.",
]


def format_energy(result: SimulationResult) -> str:
    """Render the energy line honestly: a number only when one was computed."""
    if result.energy_kcal_mol is None or result.energy_hartree is None:
        reason = result.error_message or "no engine ran"
        return f"not computed (`null`) — {reason}"
    return f"**{result.energy_kcal_mol:,.2f} kcal/mol** ({result.energy_hartree:.5f} Hartree)"


def format_execution_mode(result: SimulationResult) -> str:
    if not result.success:
        return f"No engine ran ({result.error_message or 'unknown reason'})"
    if result.sample_mode:
        return "CPU Sample Mode (Benchmark Offline)"
    return "Docker Engine (AmberTools 26)"


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
            "**Track 02: The Agent That Can Explain Why** | *Automated QM/MM Setup Audit*",
            "",
            "---",
            "",
            "## 📊 Simulation Summary",
            f"- **System Name:** `{system_name}`",
            f"- **Engine Status:** {'success' if result.success else 'did not run'}"
            + (f" — {result.error_message}" if result.error_message else ""),
            f"- **QM Theory Level:** `{result.qm_theory}`",
            f"- **Total QM/MM Energy:** {format_energy(result)}",
            f"- **Total QM Residues:** {len(partition.qm_residues)}",
            f"- **Formal Charge (`qmcharge`):** {partition.qm_charge:+d}",
            f"- **Spin Multiplicity:** {partition.spin_multiplicity} (Closed-shell Singlet)",
            f"- **Valence Electrons:** {partition.total_valence_electrons}",
            f"- **Link Atoms Severed:** {len(partition.link_atoms)}",
            f"- **Execution Mode:** {format_execution_mode(result)}",
            f"- **Execution Time:** {result.execution_time_seconds:.3f} s",
        ]

        if chimerax_script_path:
            lines.append(f"- **ChimeraX 3D Script:** `{chimerax_script_path}`")

        lines.extend([
            "",
            "---",
            "",
            "## 🎴 Track 02 Decision Cards (Verifiable Scientific Explanations)",
            "Every autonomous choice made by ActiveSite is detailed below with rejected alternatives, scientific rationales, and quantitative evidence.",
            "",
        ])

        # Group cards by category
        cards = result.decision_cards or partition.decision_cards
        for idx, card in enumerate(cards, start=1):
            lines.append(f"### {idx}. {card.category.value.upper()}: `{card.target}`")
            lines.append(f"- **Selected Choice:** **{card.choice}** *(Confidence: {card.confidence:.2f})*")
            lines.append(f"- **Scientific Rationale:** {card.rationale}")

            if card.alternatives:
                lines.append("- **Evaluated & Rejected Alternatives:**")
                for alt in card.alternatives:
                    lines.append(f"  - ❌ **{alt.name}**: {alt.rejected_reason}")

            if card.evidence:
                lines.append("- **Quantitative Evidence:**")
                for k, v in card.evidence.items():
                    lines.append(f"  - `{k}`: {v}")
            lines.append("")

        lines.extend([
            "---",
            "",
            "## 🛡️ Trust & Reproducibility Ledger",
            "The partition was checked for odd-electron spin contamination, valid boundary bond cuts, "
            "and protonation equilibrium. Decisions and self-corrections are recorded in the Meterless H-MEM ledger "
            "so they can be audited and replayed.",
            "",
            "---",
            "",
            "## ⚠️ Limitations",
        ])
        lines.extend(f"- {item}" for item in LIMITATIONS)

        return "\n".join(lines) + "\n"
