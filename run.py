"""ActiveSite — Autonomous QM/MM Assistant (Track 02: The Agent That Can Explain Why)."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from activesite.agent.orchestrator import MasterOrchestrator


def main() -> None:
    parser = argparse.ArgumentParser(
        description="ActiveSite: Autonomous QM/MM Assistant with Explainable Scientific Reasoning"
    )
    parser.add_argument("--version", action="version", version="ActiveSite 0.1.0")
    parser.add_argument(
        "--case",
        type=str,
        help="Run a specific benchmark case (e.g. egfr_erlotinib, ippoi_site_a, abl_imatinib_a)",
    )
    parser.add_argument(
        "--query",
        "-q",
        type=str,
        help="Run a natural language setup query (e.g. 'Prepare EGFR kinase with erlotinib...')",
    )
    parser.add_argument(
        "--sample-mode",
        action="store_true",
        default=True,
        help="Run in offline CPU evaluation mode (default: True)",
    )
    parser.add_argument(
        "--docker",
        action="store_true",
        default=False,
        help="Run real containerized Amber execution when Docker is available (sets sample_mode=False)",
    )
    parser.add_argument(
        "--server",
        "--web",
        action="store_true",
        help="Launch the interactive FastAPI web dashboard at http://localhost:8088",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8088,
        help="Port for the web dashboard (default: 8088)",
    )
    parser.add_argument(
        "--benchmark",
        action="store_true",
        help="Execute all benchmark cases and print a validation summary table",
    )

    args = parser.parse_args()

    if args.server:
        import uvicorn
        print(f"🔬 Starting ActiveSite Interactive Web Dashboard on http://localhost:{args.port}...")
        uvicorn.run("activesite.server.main:app", host="0.0.0.0", port=args.port, reload=False)
        return

    sample_mode = False if args.docker else args.sample_mode
    orch = MasterOrchestrator(sample_mode=sample_mode)

    if args.benchmark:
        cases = ["egfr_erlotinib", "ippoi_site_a", "abl_imatinib_a"]
        print("================================================================================")
        print(" ActiveSite — Benchmark Validation Suite (Track 02: Explainable Agents)")
        print("================================================================================")
        for c in cases:
            print(f"\n--> Running benchmark case: {c}")
            res = orch.run_case(c)
            if res.result.energy_kcal_mol is None:
                print(f"    ✗ Energy: null ({res.result.error_message or 'engine did not run'})")
            else:
                print(f"    ✓ Energy: {res.result.energy_kcal_mol:,.2f} kcal/mol ({res.result.energy_hartree:.5f} Ha)")
            print(f"    ✓ QM Residues: {len(res.partition.qm_residues)} | qmcharge: {res.partition.qm_charge:+d}")
            print(f"    ✓ Decision Cards generated: {len(res.decision_cards)}")
            print(f"    ✓ ChimeraX script: {res.chimerax_script_path}")
        print("\nBenchmark setup finished. Energies are null until the Docker engine module exists.")
        return

    if args.case:
        print(f"Executing case: {args.case} (Sample Mode: {sample_mode})...")
        out = orch.run_case(args.case)
        print(out.report_markdown)
        return

    if args.query:
        print(f"Executing query: '{args.query}'...")
        out = orch.run_query(args.query)
        print(out.report_markdown)
        return

    # Default help when no args given
    parser.print_help()


if __name__ == "__main__":
    main()
