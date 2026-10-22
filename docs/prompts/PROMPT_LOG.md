# ActiveSite — Prompt Engineering & Agent Trajectory Log
**Open Agent Hackathon 2026 | Track 02: "The Agent That Can Explain Why"**

This log documents key prompt engineering cycles, Cursor Composer iterations, and autonomous agent trajectories used in the conception, development, and testing of **ActiveSite**.

---

## Log Entries

### [2026-10-21 19:25 CDT] — Kickoff & Scaffold Initialization
- **Tool / Environment:** Cursor IDE + Antigravity Agent
- **Target Component:** Repository Foundation, `.cursorrules`, and Track 02 Alignment
- **Developer Prompt:**
  > "Initialize repository ActiveSite-QM-MM for Open Agent Hackathon 2026 Track 02 ('The Agent That Can Explain Why'). Set up .cursorrules with clean host isolation, Meterless H-MEM memory rules, Zetaris MCP adapter configuration, and CPU-friendly judge sample modes."
- **Agent Action:**
  - Configured `.cursorrules` with Track 02 criteria (scientific explanation cards, zero-key CPU sample mode, Docker isolation).
  - Configured `.cursor/mcp.json` with fallback-resilient connectors for Zetaris and Meterless.
  - Initialized clean git structure and `.gitignore` to protect credentials and heavy MD trajectory outputs.
- **Verification:** Repository verified clean on `main` branch with working Desktop symlink.

---

### [2026-10-21 20:24 CDT] — Core Domain Models & Decision Cards (Track 02)
- **Tool / Environment:** Antigravity Builder Agent
- **Target Component:** `activesite/models.py`, `tests/test_models.py`
- **Developer Prompt:**
  > "Implement features step-by-step according to our .cursorrules: Feature 1 - Core Domain Models & Decision Cards."
- **Agent Action:**
  - Implemented `DecisionCard` and `AlternativeChoice` adhering to Track 02 mandatory fields (`decision_id`, `choice`, `alternatives`, `rationale`, `confidence`, `evidence`).
  - Added domain models for `LinkAtom`, `ResidueSelection`, `QMMMPartition`, and `SimulationResult`.
  - Added Markdown formatting method `to_markdown()` for readable explanation rendering in UI and report artifacts.
  - Implemented and passed unit tests covering card generation, partition assembly, and simulation result serialization.
- **Verification:**
  - `pytest tests/test_models.py` passed with 3/3 tests green in 0.18s.

---

### [2026-10-21 20:25 CDT] — Meterless H-MEM Episodic Memory & Trust Ledger
- **Tool / Environment:** Antigravity Builder Agent
- **Target Component:** `activesite/memory/meterless.py`, `activesite/memory/meterless_mcp.py`, `tests/test_memory.py`
- **Developer Prompt:**
  > "Implement features step-by-step according to our .cursorrules: Feature 2 - Meterless H-MEM Episodic Memory & Trust Ledger."
- **Agent Action:**
  - Implemented `MeterlessHMEM` managing episodic memory records and verifiable trust ledger with zero external key dependency.
  - Pre-seeded domain memories for benchmark cases (I-PpoI catalytic Mg2+ coordination rule, EGFR erlotinib hinge H-bond rule, ABL imatinib DFG-out rule).
  - Implemented `recall_corrective_action` to enable autonomous self-correction by the Critic Agent.
  - Implemented standard JSON-RPC MCP server (`activesite.memory.meterless_mcp`) for tool-based recall and ledger audits.
  - Created unit tests verifying initialization, seeding, error recall, and MCP dispatching.
- **Verification:**
  - `pytest tests/test_memory.py` passed with 4/4 tests green in 0.03s.

---

### [2026-10-21 20:26 CDT] — Data Scout & Zetaris MCP Adapter
- **Tool / Environment:** Antigravity Builder Agent
- **Target Component:** `activesite/adapters/scout.py`, `activesite/adapters/zetaris_mcp.py`, `tests/test_adapters.py`
- **Developer Prompt:**
  > "Implement features step-by-step according to our .cursorrules: Feature 3 - Data Scout & Zetaris MCP Adapter."
- **Agent Action:**
  - Implemented `DataScout` with support for loading benchmark cases, scanning local PDB references, and fallback querying of the RCSB PDB REST API.
  - Implemented `ZetarisCatalog` with an embedded DuckDB engine enabling federated SQL analytics across benchmark case definitions and macromolecular structures.
  - Implemented standard JSON-RPC MCP server (`activesite.adapters.zetaris_mcp`) with `search_catalog`, `sql_query`, and `resolve_structure` tools.
  - Implemented unit tests verifying case discovery, PDB parsing, DuckDB SQL execution, and MCP tool handling.
- **Verification:**
  - `pytest tests/test_adapters.py` passed with 4/4 tests green in 0.64s.

---

### [2026-10-21 20:27 CDT] — Structure Prep & Explainable Protonation Agent
- **Tool / Environment:** Antigravity Builder Agent
- **Target Component:** `activesite/chem/protonation.py`, `tests/test_protonation.py`
- **Developer Prompt:**
  > "Implement features step-by-step according to our .cursorrules: Feature 4 - Structure Prep, PROPKA & Protonation Agent with Explainability."
- **Agent Action:**
  - Implemented `ProtonationAgent` calculating chemical environmental pKa shifts (coordinating metals, dielectric burial, hydrogen bond networks) across titratable residues.
  - Added tautomer selection for Histidines (HIE vs HID vs HIP), showing why coordinating divalent Mg2+ suppresses double protonation and directs lone-pair orientation.
  - Added ligand protonation predictors for erlotinib (AQ4 quinazoline base) and imatinib (STI N-methylpiperazine tertiary ammonium cation).
  - Every protonation prediction generates a complete Track 02 `DecisionCard` with alternatives, scientific rationale, and numerical pKa evidence.
  - Implemented unit tests covering metal coordination, hydrophobic burial shifts, and ligand ionization.
- **Verification:**
  - `pytest tests/test_protonation.py` passed with 4/4 tests green in 0.03s.

---

### [2026-10-21 20:29 CDT] — QM/MM Active Site Partitioning & Link Atom Placement
- **Tool / Environment:** Antigravity Builder Agent
- **Target Component:** `activesite/chem/partitioning.py`, `tests/test_partitioning.py`
- **Developer Prompt:**
  > "Implement features step-by-step according to our .cursorrules: Feature 5 - QM/MM Active Site Partitioning & Link Atom Placement."
- **Agent Action:**
  - Implemented `QMMMPartitioner` with distance-based active site pocket selection around ligands and catalytic metal centers.
  - Added link atom cut generator placing capping hydrogens along single C_alpha - C_beta sigma bonds to minimize orbital distortion artifacts.
  - Supported metalloenzyme partitioning for I-PpoI endonuclease (Mg2+ coordinating sphere, catalytic waters, scissile phosphate).
  - Emitted Track 02 Decision Cards for radius selection, residue inclusion/exclusion (e.g. Met769 inclusion vs Thr766 exclusion), link atom boundary cuts, and formal charge balance.
  - Implemented unit tests verifying link atom geometry, EGFR erlotinib partitioning, and metal center active site construction.
- **Verification:**
  - `pytest tests/test_partitioning.py` passed with 3/3 tests green in 1.28s.

---

### [2026-10-21 20:30 CDT] — Critic Agent & Episodic Self-Correction Loop
- **Tool / Environment:** Antigravity Builder Agent
- **Target Component:** `activesite/agent/critic.py`, `tests/test_critic.py`
- **Developer Prompt:**
  > "Implement features step-by-step according to our .cursorrules: Feature 6 - Critic Agent & Self-Correction Feedback Loop."
- **Agent Action:**
  - Implemented `CriticAgent` with valence electron counting and closed-shell parity inspection.
  - Linked the Critic directly with `MeterlessHMEM` to automatically recall episodic lessons upon detecting anomalies such as `ODD_ELECTRON_SPIN_MISMATCH`.
  - Implemented automatic self-correction of the QM charge (e.g. converting `qmcharge` from 0 to +1 in I-PpoI endonuclease to prevent open-shell radical collapse).
  - Emitted Track 02 `CRITIC_CORRECTION` Decision Cards detailing diagnosed cause, recalled lesson, and verified singlet multiplicity.
  - Recorded audited decisions into the persistent Meterless Trust Ledger.
- **Verification:**
  - `pytest tests/test_critic.py` passed with 2/2 tests green in 0.16s.

---

### [2026-10-21 20:31 CDT] — Chemistry Runner & AmberTools QM/MM Execution
- **Tool / Environment:** Antigravity Builder Agent
- **Target Component:** `activesite/chem/runner.py`, `tests/test_runner.py`
- **Developer Prompt:**
  > "Implement features step-by-step according to our .cursorrules: Feature 7 - Chemistry Runner & AmberTools / GFN2-xTB Execution."
- **Agent Action:**
  - Implemented `ChemistryRunner` generating Amber `sander` `&qmmm` namelist configuration with automated `qmmask`, `qm_theory`, `qmcharge`, and `qmcut` parameters.
  - Implemented container execution logic targeting `activesite-engine:at26` with clean host machine isolation.
  - Implemented fast CPU-friendly `SAMPLE_MODE=true` offline fallback adhering to hackathon evaluation constraints (< 5 minutes, zero external API keys).
  - Emitted Track 02 `THEORY_SELECTION` Decision Card justifying PM6 semi-empirical Hamiltonian selection for rapid active-site exploration.
  - Implemented unit tests for namelist generation and offline execution.
- **Verification:**
  - `pytest tests/test_runner.py` passed with 2/2 tests green in 0.33s.

---

### [2026-10-21 20:32 CDT] — ChimeraX Visualization Script Generator (.cxc)
- **Tool / Environment:** Antigravity Builder Agent
- **Target Component:** `activesite/chem/chimerax.py`, `tests/test_chimerax.py`
- **Developer Prompt:**
  > "Implement features step-by-step according to our .cursorrules: Feature 8 - ChimeraX Visualization Script Generator."
- **Agent Action:**
  - Implemented `ChimeraXGenerator` providing automated `.cxc` command scripts for 3D molecular visualization in UCSF ChimeraX.
  - Automatically color-codes the partitioned QM system (magenta for ligand, cyan for catalytic residues, light green for metal centers, grey translucent ribbon for MM backbone).
  - Renders yellow spheres at calculated 3D coordinates for all covalent link atoms along severed C_alpha - C_beta sigma bonds.
  - Generates pseudobonds for active-site hydrogen bond networks and centers camera view on the QM pocket.
  - Implemented unit tests for command script creation and spec generation.
- **Verification:**
  - `pytest tests/test_chimerax.py` passed with 1/1 test green in 0.16s.

---

### [2026-10-21 20:33 CDT] — Planner, Explainer Agent & End-to-End Orchestrator
- **Tool / Environment:** Antigravity Builder Agent
- **Target Component:** `activesite/agent/planner.py`, `activesite/agent/explainer.py`, `activesite/agent/orchestrator.py`, `tests/test_orchestrator.py`
- **Developer Prompt:**
  > "Implement features step-by-step according to our .cursorrules: Feature 9 - Orchestrator, Planner & Explainer Agent."
- **Agent Action:**
  - Implemented `PlannerAgent` extracting targets, PDB codes, ligands, metal centers, pH, and theories from conversational prompts and JSON benchmark cases.
  - Implemented `ExplainerAgent` compiling comprehensive Track 02 scientific reports with detailed Decision Card breakdowns, rejected alternatives, and quantitative metrics.
  - Implemented `MasterOrchestrator` linking the complete 7-stage pipeline (Scout -> Plan -> Protonate -> Partition -> Critic -> Run -> Explain) with event callback hooks for live streaming.
  - Executed benchmark cases `egfr_erlotinib` and `ippoi_site_a` through the orchestrator.
  - Implemented unit and integration tests verifying end-to-end execution and report generation.
- **Verification:**
  - `pytest tests/test_orchestrator.py` passed with 3/3 tests green in 1.39s (26/26 full test suite green in 2.65s).

---

### [2026-10-21 20:35 CDT] — Interactive Web Dashboard, SSE Live Streaming & CLI Runner
- **Tool / Environment:** Antigravity Builder Agent
- **Target Component:** `activesite/server/main.py`, `activesite/server/index.html`, `run.py`, `tests/test_server.py`
- **Developer Prompt:**
  > "Implement features step-by-step according to our .cursorrules: Feature 10 - Interactive Web Interface & Live SSE Streaming."
- **Agent Action:**
  - Implemented FastAPI server (`activesite.server.main`) with SSE live streaming for internal agent thoughts (`/api/stream/{stream_id}`), simulation execution (`/api/run`), case queries (`/api/cases`), and trust ledger audits (`/api/ledger`).
  - Created a single-page interactive dashboard (`index.html`) featuring quick-select benchmark case buttons, conversational setup prompt box, real-time thought stream, simulation metrics, filterable Decision Cards deck, and ChimeraX script download.
  - Upgraded CLI runner `run.py` to support `--benchmark`, `--case`, `--query`, `--web`, `--port`, and `--sample-mode`.
  - Implemented unit tests for dashboard HTML, case listing, simulation execution, and ledger retrieval.
- **Verification:**
  - `pytest tests/test_server.py` passed with 4/4 tests green.
  - `python run.py --benchmark` successfully executed EGFR erlotinib, I-PpoI Site A, and ABL imatinib benchmarks in < 3s.
  - Full test suite passed with 30/30 tests green in 3.07s.

---

### [2026-10-21 22:12 CDT] — Amber qmmask Sanitizer, PM6 Spin=1, and --docker CLI
- **Tool / Environment:** Cursor Grok Agent
- **Target Component:** `activesite/chem/partitioning.py`, `activesite/chem/runner.py`, `activesite/agent/critic.py`, `run.py`
- **Developer Prompt:**
  > "1. Amber Mask Syntax Fix: ensure `amber_qmmask` does not repeat colons after commas (`:371,34,137` rather than `:371,:34,:137`) and sanitize `,:` in `generate_amber_mdin()`. 2. When `qm_theory == 'PM6'`, always enforce `spin=1` (Amber PM6 RHF). 3. Add `--docker` flag in `run.py` setting `sample_mode=False`. 4. Run pytest, log, and commit."
- **Agent Action:**
  - Added `format_amber_qmmask()` so partition masks use a single leading colon (`:371,34,137`).
  - Sanitized `qmmask` in `ChemistryRunner.generate_amber_mdin()` by replacing `,:` with `,`.
  - Forced `spin=1` in the Amber `&qmmm` namelist and in `CriticAgent.inspect_and_correct()` when theory is PM6.
  - Added CLI `--docker` to opt into containerized Amber execution (`sample_mode=False`).
- **Verification:**
  - `pytest` passed with 30/30 tests green in 2.96s.

---

### [2026-10-22 00:18 CDT] — P0: Clean Ground & Guardrails (branch `feat/p0-cleanup`)
- **Tool / Environment:** Claude Code (Fable 5.1); no Docker in the build environment (`docker info` fails)
- **Target Component:** `activesite/chem/runner.py`, `activesite/memory/meterless.py`, `activesite/agent/explainer.py`, `activesite/adapters/zetaris_mcp.py`, `AGENTS.md`, `.env.example`, `.gitignore`, tests
- **Developer Prompt:**
  > "P0 — clean ground and guardrails. Delete REFERENCE_ENERGIES, the '-0.05 Ha per residue' energy synthesis, the fake mdout writer and the -95000 default; run_simulation returns success=False with null energies and 'engine not implemented yet'. Delete _seed_foundational_memories and the error_type-only recall fallback; a fresh ledger starts empty. Remove 'cryptographically traceable'; add a Limitations section. Rename the DuckDB catalog to 'catalog-STANDIN (DuckDB)'. Add .env.example, AGENTS.md, .gitignore rules, logs/.gitkeep. Fix tests so the suite passes for the right reasons."
- **Agent Action:**
  - Runner: removed the reference-energy table, the per-residue energy synthesis and the mock mdout. `run_simulation` now only writes `qmmm.mdin`, emits the THEORY card and returns `success=False`, `energy_hartree=None`, `energy_kcal_mol=None`, `error_message="engine not implemented yet"`. The sander mdout parser returns `None` instead of `-95000.0` and is unit-tested against a text fixture.
  - Memory: no seeding; a missing ledger starts empty and nothing is written until a record is stored. `recall_corrective_action` only matches the same system (or `generic`); the cross-system `error_type` fallback is gone. The committed `data/memory/meterless_ledger.json` was reset to empty. Fixed `record_lesson` ids (previously always `MEM_USER_1000` because `sys.time` does not exist).
  - Explainer/UI/CLI/API: energy renders as `not computed (null) — engine not implemented yet` everywhere; "cryptographically traceable" removed; new "Limitations" section (PM6 single points only, implicit solvent for ligand cases, no local free-energy barriers, local catalog stand-in until Zetaris credentials exist). `/api/run` now returns `error_message`; the dashboard shows `null` and the reason.
  - Catalog: user-facing name is now `catalog-STANDIN (DuckDB)` in the adapter docstring, MCP tool descriptions, README and dashboard badge. Class names and MCP tool names unchanged.
  - Guardrails: `AGENTS.md` (series rules + the five `.cursorrules` principles), "See AGENTS.md" at the top of `.cursorrules`, `.env.example` with placeholders only, `.gitignore` now keeps `logs/.gitkeep` and ignores `logs/*.jsonl`.
  - Tests: every assertion of a fabricated energy or seeded memory replaced. The I-PpoI orchestrator test now asserts closed-shell parity instead of `qmcharge == 1`, because the old value came from the seeded memory via the deleted fallback.
- **Verification:**
  - `uv run pytest -q` → `37 passed, 33 warnings in 5.96s`
  - `grep -rn "REFERENCE_ENERGIES\|_seed_foundational\|cryptographically" activesite` → empty.
  - `uv run python run.py --case egfr_erlotinib` prints `Engine Status: did not run — engine not implemented yet` and `Total QM/MM Energy: not computed (null)`.
  - Working tree stays clean after CLI and test runs (the ledger is no longer mutated on init).
  - To run on a Docker host: nothing yet; engine execution is the next module.

---

### [2026-10-22 00:22 CDT] — P1: `activesite/chem/system.py` geometry & charge layer (branch `feat/p1-system`, stacked on `feat/p0-cleanup`)
- **Tool / Environment:** Claude Code (Fable 5.1); no Docker (pure parmed/numpy, nothing to run on a Docker host)
- **Target Component:** `activesite/chem/system.py`, `tests/test_system.py`
- **Developer Prompt:**
  > "Create activesite/chem/system.py: a small geometry and charge layer over parmed for Amber systems. ATOMIC_Z, ChargeReport dataclass, MolSystem(parm7, coords) with label/res_label/select/dist/angle/within/charge_report/ring_bonds_cut/atom_mask. Fast tests on a 3-atom water built in code; slow tests on the I-PpoI parm7+ncrst (skip if missing). Acceptance: tests green; no side effects on import."
- **Agent Action:**
  - `MolSystem` wraps `parmed.load_file(parm7, coords)`; `from_structure()` builds one from an in-memory Structure for tests and prep code. Coordinates are cached as a `(N,3)` numpy array; distances are plain Euclidean (no periodic imaging).
  - `charge_report` sums MM partial charges, rounds to the implied integer, reports the residual fraction, electrons as `sum(Z) - nearest_int`, and counts boundary bonds (exactly one end in QM) as link atoms. Atomic numbers come from the topology, with `ATOMIC_Z` as the fallback.
  - `ring_bonds_cut` flags intra-residue boundary bonds whose atoms stay connected through the residue's bond graph once that bond is removed (BFS over `bond_partners` restricted to the residue).
  - `atom_mask` compacts 0-based indices into a 1-based Amber range mask.
  - Tests: water (built with `parmed.Structure`) covers labels, dist/angle/within/select/charge/mask; the I-PpoI reference checks MG371, a neutral whole-system charge report with zero link atoms, and that selecting only C3' of a nucleotide flags its two furanose ring bonds while the whole nucleotide flags none. A subprocess import verifies no side effects.
- **Verification:**
  - `uv run pytest -q` → `46 passed, 49 warnings in 10.01s` (slow tests ran; the reference files are present).

---

### [2026-10-22 00:30 CDT] — P2: `activesite/chem/qmregion.py` QM region proposal with numeric evidence (branch `feat/p2-qmregion`, stacked on `feat/p1-system`)
- **Tool / Environment:** Claude Code (Fable 5.1); no Docker (geometry only, nothing to run on a Docker host)
- **Target Component:** `activesite/chem/qmregion.py`, `tests/test_qmregion.py`
- **Developer Prompt:**
  > "Create activesite/chem/qmregion.py: propose a QM region for a Mg-dependent phosphodiester-cleavage active site, with numeric evidence for every choice so the Explainer can cite it. Choice/Proposal dataclasses; propose(sys, metal_resid, cut_level) with rules metal / first shell (2.8 Å, whole waters, protein side chains) / scissile phosphate / nucleophile (largest O(w)-P-O3' angle within 4 Å) / general base (His ring N within 6 Å); cut levels minimal then sugar, accepted only if charge.fraction <= 0.10 and no ring bonds cut; compare(sys, ours, expert). Tests against the I-PpoI reference and the expert mask."
- **Agent Action:**
  - Five rules each append a `Choice(residue, role, rule, evidence)` with distances, angles, the search radius and every rejected candidate (waters with their in-line angle, other His N with their distance), so the Explainer can cite numbers rather than slogans.
  - Cut levels are tried smallest first; `minimal` is rejected on I-PpoI because it cuts the furanose ring bonds C3'-C2' and C3'-C4' of the leaving nucleotide, `sugar` is accepted (charge fraction 0.032, four link atoms). Both reasons land in `Proposal.notes`.
  - The expert mask for this exact parm7/ncrst is `QMMASK` in `gen_inputs.sh` (site Mg371, qmcharge +1). `gen_qmmask.py` is a fragment listing whole residues for the other site (Mg372) and `qmhub.ini` only carries engine settings, so the test parses `gen_inputs.sh` for the mask/charge and reads the other two to document what they contain.
  - `propose(sys, 371)` reproduces the 64-atom expert region with atom Jaccard 1.0 and `nearest_int == +1`; `propose(sys, 372)` yields a 67-atom region on the DG35/DA34 phosphodiester with every residue within 8 Å of the metal.
- **Verification:**
  - `uv run pytest -q` → `52 passed, 65 warnings in 13.64s`
  - Every `Choice` carries at least one numeric evidence value (asserted in the tests for both sites).

---

### [2026-10-22 00:36 CDT] — P3: `activesite/chem/sander.py` containerised sander single point (branch `feat/p3-sander`, stacked on `feat/p2-qmregion`)
- **Tool / Environment:** Claude Code (Fable 5.1); `docker info` fails here, so the engine test is skip-marked and listed for a Docker host
- **Target Component:** `activesite/chem/sander.py`, `activesite/chem/runner.py`, `activesite/models.py`, `tests/test_sander.py`, `tests/fixtures/sander_ok.out`, `tests/fixtures/sander_odd.out`
- **Developer Prompt:**
  > "Create activesite/chem/sander.py: run one sander QM/MM single point in the activesite-engine:at26 container and parse the output. PME and GB mdin templates; parse_sander_output(text, theory) pure function; run_single_point(...) with docker run --rm --name sander-<hex> -v refdir:/ref:ro -v workdir:/work, timeout -> docker rm -f. Fixtures in sander's real mdout layout; docker command test with subprocess.run monkeypatched; slow engine test on a Docker host. Replace the engine stub in runner.py; no placeholder energy path."
- **Agent Action:**
  - `sander.py`: PME and GB templates whose title line names theory and charge; an allow-list on theory, an Amber-mask character class on `qmmask`, int-only charge and a two-value solvent switch, because these strings reach the mdin and the docker command line. `parse_sander_output` reads ESCF and the NSTEP/ENERGY table only from the block after `FINAL RESULTS`, plus the RESP charge sum, `nlink`, the odd-electron count and every diagnostic `QMMM:` line; a NaN/Inf/overflow ESCF yields `ok=False` with "non-finite QM energy". `run_single_point` writes `sp.mdin`, runs the exact container command from the prompt, removes the container on timeout, and falls back to the stderr tail when sander exits non-zero without a diagnosable line.
  - `runner.py`: the stub is gone. `run_simulation` now returns one of three honest skips (SAMPLE_MODE on, no Docker/image, no Amber topology for the system) or maps the parsed engine output onto `SimulationResult` (total QM/MM energy in kcal/mol and Hartree, raw parse in the new `engine` field). PME vs GB is chosen from `%FLAG BOX_DIMENSIONS` in the parm7.
  - Fixtures were written by hand in the Amber 26 mdout layout (file assignments, echoed input, sections 1-5, link-atom table, RESP sum, pre-final and FINAL RESULTS energy blocks; the odd case carries the three-line `QMMM: System specified with odd number of electrons (  203)` diagnostic and a SANDER BOMB with no ESCF).
  - Tests: parser on both fixtures, FINAL-RESULTS-only reading, non-finite ESCF, theory name matching, template contents, allow-list rejections, exact docker command, timeout path with `docker rm -f`, stderr fallback, same-directory requirement, and the runner mapped through a mocked `run_single_point`. `slow` marker registered in `pyproject.toml`.
- **Verification:**
  - `uv run pytest -q` → `72 passed, 1 skipped, 65 warnings in 14.71s` (the skip is `test_engine_site_a_single_point`, needs Docker)
  - **To run on a Docker host:** `docker build -f docker/engine.Dockerfile -t activesite-engine:at26 .` then `uv run pytest -q tests/test_sander.py -m slow`: expects charge 0 on the P2 site-A mask → `ok False` with `odd_electrons` set, charge +1 → `ok True` with finite ESCF and `data/runs/sander_engine_test/charge1/sp.out` present. Also `SAMPLE_MODE=false uv run python run.py --case ippoi_site_a --docker`.

---

### [2026-10-22 00:45 CDT] — P4: `activesite/chem/prep.py` + `ligand_rdkit.py` complex preparation with evidence (branch `feat/p4-prep`, stacked on `feat/p3-sander`)
- **Tool / Environment:** Claude Code (Fable 5.1); no Docker here, so the two full-preparation tests are skip-marked and listed for a Docker host
- **Target Component:** `activesite/chem/prep.py`, `activesite/chem/ligand_rdkit.py`, `tests/test_prep.py`, `tests/fixtures/methanol.mol2`, `tests/fixtures/methanol.sdf`
- **Developer Prompt:**
  > "Create activesite/chem/prep.py and activesite/chem/ligand_rdkit.py: prepare a protein-ligand complex from a raw PDB for QM/MM, recording evidence for every decision. Every chemistry tool runs inside activesite-prep:at26. choose_chain / extract / protonate / ligand_protonation_site / review_uncertain / ligand_parameters (cached GAFF2+BCC, mol2 finalisation refusing order mismatch or residual >= 0.01 e) / build_complex / minimise / built_pose / polar_contacts. No-Docker tests on 1M17 and 2HYY; slow Docker tests for the full EGFR and ABL preparations."
- **Agent Action:**
  - `dock` runs an argv list (no shell) in the prep container with `work` at `/work`, optionally under `micromamba run -n prep`; merged output and seconds are returned and every tool's log is saved in `work`.
  - Pure parts testable without Docker: REMARK 465/470 parsing and chain scoring (gaps adjacent to the 12 Å CA pocket, missing-atom residues in the pocket, missing residues, chain id); altloc-filtered extraction; tertiary-amine detection (N with exactly three C within 1.6 Å) against backbone O within 3.3 Å; His review inside the 1.0 pKa window with the ring N facing the ligand cation left unprotonated; PROPKA summary and pdb4amber renum parsing; mol2 finalisation that keeps cached charges/types, takes this run's SDF coordinates, refuses count/element-order mismatches and residuals >= 0.01 e, and spreads smaller residuals evenly; polar-contact geometry shared by the crystal and built poses.
  - Container stages: pdb2pqr/PROPKA, the standalone `ligand_rdkit.py` (bond orders from the SMILES template, optional +1/explicit-H on the named N, H placement, one JSON line), antechamber+parmchk2 cached under `data/cache/ligands/<sha256[:16]>`, pdb4amber, tleap (fails on Errors > 0, parses the total charge), restrained GB minimisation, and `built_pose` via parmed with partners reported in crystal numbering. `prepare_complex` chains them and keeps every stage's dict.
  - On 2HYY chain A the amine rule picks N51 (N-methyl piperazine) with its closest backbone carbonyl under 3.3 Å; on 1M17 erlotinib has no tertiary amine and the function returns None. MET769 appears as a crystal polar contact under 3.3 Å.
- **Verification:**
  - `uv run pytest -q` → `83 passed, 3 skipped, 65 warnings in 14.12s` (skips: the sander engine test and the two prep Docker tests)
  - **To run on a Docker host:** `docker build -f docker/prep.Dockerfile -t activesite-prep:at26 .` (after the engine image) then `uv run pytest -q tests/test_prep.py -m slow`: expects complex.parm7 and min.rst7 for both cases, final GMAX < 10, ligand centroid shift < 1 Å, a MET769 contact under 3.3 Å for EGFR, net charge 0 (erlotinib) and +1 (imatinib), and nothing written outside the work and cache directories.

---

### [2026-10-22 00:50 CDT] — P5: `activesite/trace.py` + `activesite/memory/hmem.py`, Meterless facade (branch `feat/p5-trace-memory`, stacked on `feat/p4-prep`)
- **Tool / Environment:** Claude Code (Fable 5.1); pure Python (sqlite3 + JSONL), nothing to run on a Docker host
- **Target Component:** `activesite/trace.py`, `activesite/memory/hmem.py`, `activesite/memory/meterless.py`, `activesite/memory/meterless_mcp.py`, `activesite/agent/critic.py`, `activesite/server/main.py`, `tests/test_trace.py`, `tests/test_hmem.py`, `tests/test_memory.py`
- **Developer Prompt:**
  > "Create activesite/trace.py and activesite/memory/hmem.py, then make the existing memory module a facade over hmem. Trace(run_id, log_dir, on_event).log(...) appends JSONL + prints + calls on_event. MemoryStoreService (SQLite memories table, add with required source and clamped confidence, append-only JSONL ledger) and MemoryRetrievalService (keyword/tag/layer/recency score, threshold 0.35, top 5, touch + read ledger). Facade keeps record_episode/record_trust_entry/query_memories/recall_corrective_action/get_ledger; recall needs BOTH exact tag and error type, no fallback. Fix the MCP record id with uuid."
- **Agent Action:**
  - `Trace.log` writes the 12 spec keys per line to `logs/trace-<run_id>.jsonl`, truncates both summaries to 300 characters, prints one aligned line, and calls `on_event`; a listener that raises cannot break the run.
  - `MemoryStoreService` keeps the `memories` table in SQLite (`check_same_thread=False` plus a lock so the FastAPI worker threads can read it) and appends `create`/`read`/`trust` lines to `logs/hmem_ledger.jsonl`, never rewriting it. `MemoryRetrievalService` scores with the rescaled weights documented in the module docstring, requires a shared tag whenever the query carries tags (so a memory tagged `mg-phosphodiester` is never returned for `ligand-pocket`), touches each hit and writes a `read` line with the query, score and parts.
  - `MeterlessHMEM` is now a facade: episodes become long-term memories tagged with system, stage, outcome and error type (the full record in `extra`), trust entries become `trust` ledger lines, `get_ledger` reads them back, and `recall_corrective_action(system_class_tag, error_type)` needs an exact tag plus the error type with no fallback and audits itself with a `read` line. `/api/ledger` additionally returns the raw ledger lines. The committed `data/memory/meterless_ledger.json` is deleted; the SQLite db and the JSONL ledger are gitignored.
  - `record_lesson` ids now come from `uuid4`.
- **Verification:**
  - `uv run pytest -q` → `92 passed, 3 skipped, 65 warnings in 13.37s` (skips are the three Docker tests)
  - `echo '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}' | uv run python -m activesite.memory.meterless_mcp` answers with the three tools.

---

### [2026-10-22 00:56 CDT] — P6: agents and the orchestrator retry loop, metal case (branch `feat/p6-loop`, stacked on `feat/p5-trace-memory`)
- **Tool / Environment:** Claude Code (Fable 5.1); engine mocked at the subprocess boundary in tests, real `--demo-memory` needs a Docker host
- **Target Component:** `activesite/agent/core.py`, `activesite/agent/orchestrator.py`, `activesite/agent/legacy_pipeline.py`, `activesite/models.py`, `run.py`, `tests/test_loop.py`, `.gitignore`
- **Developer Prompt:**
  > "Create activesite/agent/core.py (Planner, DataScout, Setup, Runner, Critic, Explainer) and rewrite activesite/agent/orchestrator.py around a retry loop. Every action traced. Confidence from measured margins, never constants. Planner allow-lists steps; DataScout validates ids before SQL and uses a NullAdapter until P8; Setup proposes the region and recalls the charge rule from H-MEM; Runner runs P3; Critic prechecks, diagnoses odd electrons, remembers only after a successful retry, validates against the expert mask; Explainer builds cards and the report. run.py gains --demo-memory and --reset-memory."
- **Agent Action:**
  - `core.py`: the six agents. The Planner keeps only allow-listed steps and accepts mode "model" only when the full list survives. The DataScout rejects system ids outside `[a-z0-9_]+` and sites outside `[A-Z]` before any SQL is built and keeps the three query strings for the UI. Setup takes the charge from the MM partial-charge sum only when an H-MEM hit carries `extra.rule == mm_partial_sum`, otherwise from the textbook sum of whole-residue formal charges (which is 0 on I-PpoI and fails with an odd electron count). The Critic's diagnose returns the nearest-integer MM sum with a why-text; `remember` is called only after the retry converged. Every card confidence is a function of a measured quantity (coordination count, shell distance, P-P gap, angle gap, base distance, charge fraction, PM6 parameter coverage, check margin, Jaccard).
  - `orchestrator.py`: `run_case(case, adapter, hmem_db, on_event, ...)` runs the loop, writes `logs/report-<run_id>.md` and `logs/cards-<run_id>.json` and returns the stats dict. `MasterOrchestrator` is kept as the compatibility entry point: metal cases go through the loop (wrapped into the old `WorkflowOutput`), ligand cases through the legacy pipeline now living in `legacy_pipeline.py`, so `/api/run`, `--case` and the older tests keep working. Without Docker or in SAMPLE_MODE the Runner records an explicit skip; nothing is retried or learned from a skip.
  - `run.py --demo-memory` runs site A then site B and prints retries/memory_used side by side; `--reset-memory` deletes the sqlite db and the ledger after a typed confirmation.
  - Added `CUT_LEVEL`, `VALIDATION`, `ANALOGY` to `DecisionCategory`; report and card files under `logs/` are gitignored.
- **Verification:**
  - `uv run pytest -q` → `96 passed, 3 skipped, 113 warnings in 21.99s`
  - `tests/test_loop.py`: with `subprocess.run` faked to serve the odd fixture then the ok fixture, cold `ippoi_site_a` gives retries 1, one memory written, a trace with all six agents, and a qmcharge card naming the rejected first attempt; warm `ippoi_site_b` on the same db gives retries 0 and memory_used True with a `create`,`read` ledger.
  - `uv run python run.py --demo-memory` here prints both sites with `qm_ok False`, `ESCF null` and the line "Engine skipped (engine not run: SAMPLE_MODE=true)".
  - **To run on a Docker host:** `SAMPLE_MODE=false uv run python run.py --demo-memory --docker` should show cold retries=1 and warm retries=0 with finite ESCF values.

---

### [2026-10-22 01:06 CDT] — P7: the ligand case (`activesite/agent/ligand.py`, `run_ligand_case`) (branch `feat/p7-ligand`, stacked on `feat/p6-loop`)
- **Tool / Environment:** Claude Code (Fable 5.1); container stages mocked in tests, real EGFR/ABL runs need a Docker host
- **Target Component:** `activesite/agent/ligand.py`, `activesite/agent/orchestrator.py`, `activesite/agent/legacy_pipeline.py` (deleted), `tests/test_ligand.py`, `tests/test_orchestrator.py`, `tests/test_server.py`
- **Developer Prompt:**
  > "Create activesite/agent/ligand.py (LigandSetup, LigandCritic, ligand_cards, run_qmmm) and add run_ligand_case to the orchestrator. Cases with kind ligand route here; metal cases to P6. LigandSetup: chain (or requested), extract, protonate, amine site, recall His memories, review_uncertain, ligand_parameters, build_complex, minimise, built_pose for both models. LigandCritic: charge sum, pocket for both models (blocking), integer complex charge, GMAX < 10; validate literature contacts and expected_absent; remember only when QM/MM succeeded, overrides exist and nothing was recalled. run_qmmm: GB single point on :LIG. Cards per spec."
- **Agent Action:**
  - `LigandSetup.build` runs the pure stages (chain table, extraction, crystal polar contacts, tertiary-amine site, memory recall) always, then the container stages; in SAMPLE_MODE or without the prep image it records `prep_skipped` with the reason and stops, so the report still explains the decisions that were made. Every step is traced with its numbers.
  - `LigandCritic.precheck` marks the two pocket checks (and a missing preparation) as blocking; `run_ligand_case` refuses to run QM/MM on a blocking failure and writes a traced `blocked` error instead. `validate` recovers `literature_contacts` from the minimised model's polar contacts and confirms each `expected_absent`. `remember` writes one working-layer memory (confidence 0.7, rule `his_near_cation_neutral`) per His override only after a converged QM/MM with nothing recalled.
  - `run_case` now routes on the case file (`kind: ligand` vs `metal_resid`); the legacy radius pipeline is deleted and `MasterOrchestrator` wraps both loops for the server, the CLI and the older tests. `run_query` maps erlotinib/imatinib prompts to their cases.
  - Cards: chain choice with the per-chain gap table (source REMARK 465/470), PDB2PQR/PROPKA states, one low-confidence card per His override, ligand protonation site or "kept neutral", GAFF2+AM1-BCC, whole-ligand QM region, implicit-solvent trade-off, one per Critic check, binding mode "n/m published contacts present" with distances, one negative control per expected_absent, structure source from Q3 when rows exist.
- **Verification:**
  - `uv run pytest -q` → `100 passed, 3 skipped, 113 warnings in 20.92s`
  - `tests/test_ligand.py` (prep.* and run_single_point mocked): routing and the full card set on EGFR; a 1.8 Å centroid shift blocks QM/MM with a traced error; on ABL nothing is remembered after a failed QM/MM, one memory after a converged one, and the third run recalls it without rewriting.
  - `uv run python run.py --case egfr_erlotinib` here: chain A chosen, ligand kept neutral, `prep not run: SAMPLE_MODE=true`, ESCF `null`.
  - **To run on a Docker host:** `uv run python run.py --case egfr_erlotinib --docker` (expect ligand neutral, MET769 recovered, THR766 absent, finite ESCF, under 6 minutes) and `--case abl_imatinib_a --docker` (ligand +1, a HIS361 override card).

---

### [2026-10-22 01:11 CDT] — P8: model client and data adapters (branch `feat/p8-adapters`, stacked on `feat/p7-ligand`)
- **Tool / Environment:** Claude Code (Fable 5.1); no Postgres/MinIO/Zetaris/NVIDIA endpoints reachable here, all network paths tested with httpx mocked or in offline mode
- **Target Component:** `activesite/llm.py`, `activesite/adapters/catalog_standin.py`, `activesite/adapters/zetaris.py`, `activesite/adapters/zetaris_mcp.py`, `seed/seed.py`, `activesite/agent/orchestrator.py`, `tests/test_llm.py`, `tests/test_catalog.py`, `tests/conftest.py`
- **Developer Prompt:**
  > "Create activesite/llm.py, activesite/adapters/catalog_standin.py, activesite/adapters/zetaris.py, and wire DataScout and the Zetaris MCP server to them. ModelClient reads MODEL_* env, generate posts an OpenAI-compatible chat completion at temperature 0.1 or returns None without a key. The stand-in is one DuckDB connection attaching Postgres, reading MinIO Parquet and an RCSB entries table; seed/seed.py creates lab_runs and uploads a small EDA Parquet. zetaris.run_sql posts with bearer, org id and a fresh request id; get_adapter() picks zetaris when configured. MCP tools list_sources and read-only query."
- **Agent Action:**
  - `ModelClient`: unavailable without a key (no HTTP call), counts calls, returns None on any transport or schema error, and `plan_json` only extracts the first JSON object; the Planner still allow-lists every step.
  - `CatalogStandin` (label `catalog-STANDIN (DuckDB)`): lazily attaches Postgres read-only, sets httpfs S3 settings for MinIO and a view over `eda_synthetic.parquet`, and registers `rcsb_entries` from the RCSB search + entry REST (cached under `data/cache/rcsb/`). Every source records its status in `sources`; `CATALOG_OFFLINE=1` skips remote sources so tests and offline judging stay deterministic.
  - `ZetarisAdapter` (label `zetaris`): the three headers with a fresh `uuid4` per call, defensive row parsing (columns+rows, list of dicts, or nested), table names from `ZETARIS_TABLE_*`. `get_adapter()` chooses by env; the orchestrator calls it when no adapter is passed and calls `prepare(case)` so the RCSB table knows the case's `pdb_query`.
  - `seed/seed.py`: `lab_runs` rows per case (site A expert mask/charge from `gen_inputs.sh`, site B's bare residue list from `gen_qmmask.py` marked unverified, ligand cases `:LIG` with no expert); `eda_synthetic.parquet` is written with DuckDB and uploaded through httpfs, named and annotated as synthetic because `theories.csv` is a theory-level list, not an EDA table.
  - MCP server: `list_sources` and `query`; `validate_select` accepts one SELECT/WITH statement and rejects any write or control keyword. The old benchmark-case DuckDB table is gone.
- **Verification:**
  - `uv run pytest -q` → `106 passed, 3 skipped, 113 warnings in 23.71s`
  - `echo '...DROP TABLE x...' | uv run python -m activesite.adapters.zetaris_mcp` → `rejected: only SELECT queries are allowed`.
  - **To run on a Docker host with services:** `docker compose up -d && uv run python seed/seed.py && uv run python run.py --case ippoi_site_a` should show Q1 returning the expert record and cards citing `catalog-STANDIN (DuckDB)`; with `ZETARIS_*` set the same run cites `zetaris`.

---

### [Template for Future Entries]
```markdown
### [YYYY-MM-DD HH:MM CDT] — Component Name
- **Tool / Environment:** Cursor Composer / Agent
- **Target Component:** e.g., activesite/agent/planner.py
- **Developer Prompt:**
  > "[Exact prompt given to agent]"
- **Agent Action:**
  - [Summary of changes made]
- **Verification:**
  - [Test passed, output verified, or benchmark results]
```
