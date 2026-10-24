"""ActiveSite — Autonomous QM/MM Assistant (Track 02: The Agent That Can Explain Why)."""
from __future__ import annotations

import argparse
import json

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
        "--md",
        action="store_true",
        default=False,
        help="Run short 1,000-step (1 ps) QM/MM Molecular Dynamics demonstration",
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
    parser.add_argument(
        "--json",
        action="store_true",
        help="With --case/--query: print the run stats as JSON (same shape as POST /run) instead of the report",
    )
    parser.add_argument(
        "--demo-memory",
        action="store_true",
        help="Run I-PpoI site A then site B through the retry loop and show retries/memory_used side by side",
    )
    parser.add_argument(
        "--reset-memory",
        action="store_true",
        help="Delete the H-MEM sqlite db and the JSONL ledger (asks for confirmation)",
    )

    args = parser.parse_args()

    if args.server:
        import uvicorn
        print(f"🔬 Starting ActiveSite Interactive Web Dashboard on http://localhost:{args.port}...")
        uvicorn.run("activesite.server.main:app", host="0.0.0.0", port=args.port, reload=False)
        return

    sample_mode = False if args.docker else args.sample_mode

    if args.reset_memory:
        from activesite.memory.meterless import DEFAULT_DB_PATH, DEFAULT_LEDGER_PATH
        targets = [p for p in (DEFAULT_DB_PATH, DEFAULT_LEDGER_PATH) if p.exists()]
        if not targets:
            print("Nothing to reset: no memory db or ledger present.")
            return
        print("This deletes: " + ", ".join(str(p) for p in targets))
        if input("Type 'yes' to confirm: ").strip().lower() == "yes":
            for p in targets:
                p.unlink()
            print("Memory reset.")
        else:
            print("Aborted.")
        return

    if args.demo_memory:
        from activesite.agent.orchestrator import run_case
        rows = []
        for case_id in ("ippoi_site_a", "ippoi_site_b"):
            print(f"\n=== {case_id} ===")
            st = run_case(case_id, sample_mode=sample_mode)
            rows.append(st)
        print("\ncase            retries  memory_used  qm_ok  qmcharge  ESCF(kcal/mol)      engine_s  run_id")
        for st in rows:
            esc = "null" if st["qm_escf_kcal"] is None else f"{st['qm_escf_kcal']:.3f}"
            print(f"{st['case']:<15} {st['retries']:>7}  {str(st['memory_used']):<11}  {str(st['qm_ok']):<5}  "
                  f"{st['qmcharge']:>+8d}  {esc:>14}  {st['engine_time_s']:>8}  {st['run_id']}")
        if any(st["engine_skipped"] for st in rows):
            print("\nEngine skipped (" + "; ".join(sorted({e for st in rows for e in st['errors']})) + "): "
                  "retries and memory reflect only what could run.")
        return

    orch = MasterOrchestrator(sample_mode=sample_mode, md=args.md)

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

    if args.case or args.query:
        if args.json:
            from activesite.agent.orchestrator import public_stats, resolve_case_id, run_case
            case_id = args.case or resolve_case_id(args.query)
            print(json.dumps(public_stats(run_case(case_id, sample_mode=sample_mode, echo=False, md=args.md)), indent=2, default=str))
            return
        if args.case:
            print(f"Executing case: {args.case} (Sample Mode: {sample_mode}, MD: {args.md})...")
            out = orch.run_case(args.case)
        else:
            print(f"Executing query: '{args.query}'...")
            out = orch.run_query(args.query)
        print(out.report_markdown)
        return

    # Default help when no args given
    parser.print_help()


if __name__ == "__main__":
    main()
