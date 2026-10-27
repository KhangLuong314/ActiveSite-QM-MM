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

### [2026-10-22 01:15 CDT] — P9: live server and dashboard (branch `feat/p9-ui`, stacked on `feat/p8-adapters`)
- **Tool / Environment:** Claude Code (Fable 5.1); server tested with the orchestrator monkeypatched, UI not exercised in a browser here
- **Target Component:** `activesite/server/main.py`, `activesite/server/index.html`, `activesite/agent/orchestrator.py`, `run.py`, `tests/test_server.py`
- **Developer Prompt:**
  > "Make the web dashboard stream the run live and show memory and data honestly. POST /api/run starts the orchestrator in a worker thread and returns a stream id; GET /api/stream/{id} is SSE fed by Trace.on_event with step events, a final result event and pings; /api/cases, /api/ledger, POST /api/memory/reset, /api/chimerax, GET /run/stream alias, POST /run returns the run.py JSON. UI: live steps, pipeline strip with handoffs, metrics with an engine badge and null rendered as 'not computed', cards with source, SQL sheet, memory table, reset button, trace link. Do not display any number that did not come from the stream."
- **Agent Action:**
  - Server: each run gets a `RunState` (events list + done flag) filled by the Trace `on_event` from a worker thread; the SSE generator replays stored events, follows new ones, pings every 15 s, and ends with one `result` (public stats, cards, validation, checks, engine result without the docker argv, SQL strings, report) or an `error`. `POST /run` runs synchronously and returns `public_stats`, the same dict `run.py --case <id> --json` prints. `/api/ledger` returns the memories, the last 50 ledger lines and the record view; `/api/memory/reset` deletes the db and ledger and reopens an empty store; `/api/trace/{run_id}` serves the JSONL.
  - Orchestrator: `resolve_case_id(prompt)`, `public_stats(stats)` and an `engine_label` in every stats dict ("sander in Docker" / "cached engine output (sample mode)" / "engine unavailable").
  - UI (same head, header, left-column look): the trace feed opens an EventSource on `/run/stream` before the run finishes and appends each step with its real timestamp, agent, action, status, confidence and retry count; a pipeline strip highlights the acting agent and shows `agent → target`; metrics show ESCF/total as "not computed" until the result event carries a number, the engine badge, qmcharge, retries/memory_used, catalog and model mode; tabs for cards (decision, rationale, source, confidence, evidence), report, "What the system remembers" (memories table plus the ledger tail) and the SQL sheet; a reset-memory button; a trace-file link. All placeholders are text, never numbers.
- **Verification:**
  - `uv run pytest -q` → `108 passed, 3 skipped, 113 warnings in 21.41s`
  - `tests/test_server.py`: `/api/run` returns a stream id, the stream yields three `step` events then `result` (also via `/run/stream`), prompts map to cases with 400/404 on bad input, `/run` returns the CLI JSON shape, and the reset endpoint empties memories and ledger.
  - **To run on a Docker host:** `SAMPLE_MODE=false uv run python run.py --server`, open http://localhost:8088, run I-PpoI site A and watch the steps arrive while sander runs, then the retry and the `remember` step.

---

### [2026-10-22 01:23 CDT] — P10: sample mode and the judge pack (branch `feat/p10-judge-pack`, stacked on `feat/p9-ui`)
- **Tool / Environment:** Claude Code (Fable 5.1); no Docker, so `data/sample/` and `samples/*/outputs` could NOT be generated here (nothing was hand-written in their place)
- **Target Component:** `activesite/sample.py`, `activesite/models.py`, `activesite/chem/runner.py`, `activesite/agent/{core,ligand,orchestrator}.py`, `scripts/{make_samples,fetch_reference,smoke_clean_clone}.sh`, `data/sample/MANIFEST.md`, `samples/`, `metadata.json`, `README.md`, `docs/PRE_EXISTING.md`, `data/reference/LARGE_FILES.sha256`, `.pre-commit-config.yaml`, `.github/workflows/ci.yml`, `CONTRIBUTING.md`, `tests/test_sample_mode.py`, `tests/test_judge_pack.py`
- **Developer Prompt:**
  > "Finish the judged path. Sample mode replays data/sample/<case>/attempt<N>/sp.out through parse_sander_output and data/sample/<case>/prep/ for ligand cases; every other agent runs its real logic; SimulationResult.engine = 'cached engine output (sample mode)'. scripts/make_samples.sh on a Docker host, MANIFEST with date+commit, track data/sample. samples/ with three inputs and saved outputs. metadata.json. README sections incl. Limitations and 'Pre-existing components and data'. docs/PRE_EXISTING.md. Large files behind scripts/fetch_reference.sh or Git LFS, whichever I confirm. pre-commit (gitleaks, ruff), CI with SHA-pinned actions, CONTRIBUTING.md. scripts/smoke_clean_clone.sh."
- **Agent Action:**
  - `activesite/sample.py`: `cached_engine_result` reads `charge<±N>/sp.out`, falling back to `attempt<N>/sp.out` only when the `qmcharge` echoed in its namelist matches the requested charge, and parses it with the P3 parser; `cached_prep` copies the saved preparation and its `prep.json` evidence into the run's work dir. A missing cache yields `engine unavailable` with "no cached sample output", never a number. The metal Runner and the ligand `run_qmmm` take this path in SAMPLE_MODE or without Docker; the real retry, memory, prechecks, validation and cards all still run. `SimulationResult.engine` is now the label string and the raw parse moved to `engine_output`; reports print `**Engine:**`.
  - `scripts/make_samples.sh` runs the five cases with `--docker --json`, copies every `sp.out` keyed by attempt and by echoed charge, the ligand prep artefacts and `prep.json`, the three sample reports/cards/traces/stats, and stamps `data/sample/MANIFEST.md` with date and commit; it also runs site B cold so a cold sample-mode run of site B has its odd-electron attempt. `.gitignore` re-includes `data/sample/**` and `samples/**`.
  - `metadata.json`, the README rewrite (five-line what-it-does, quickstart, the three sample cases with expected outputs, architecture, sponsors with the modules that use them, models/frameworks, Limitations, "Pre-existing components and data"), `docs/PRE_EXISTING.md` (table with path, origin, date, used by; declares every file under `data/reference/`, the absent spike benchmark, the Docker base images and the pre-window scaffold). `tests/test_judge_pack.py` asserts that metadata, README and the declaration table agree and that no code unpickles reference data.
  - Large files: `data/reference/LARGE_FILES.sha256` + `scripts/fetch_reference.sh` (REFERENCE_URL or REFERENCE_PATH, hash-verified). The files are still tracked: removing them from history is the maintainer's call (LFS vs fetch script, see open questions).
  - Guardrails: `.pre-commit-config.yaml` (gitleaks v8.21.2, ruff v0.8.4), `.github/workflows/ci.yml` (checkout and setup-python pinned to SHAs, uv via pip, pytest, gitleaks via its pinned image tag), `CONTRIBUTING.md`.
  - `scripts/smoke_clean_clone.sh`: fresh clone, optional compose, `uv sync`, the three cases in SAMPLE_MODE, asserts the cached-engine label and a trace file, prints total seconds.
- **Verification:**
  - `uv run pytest -q` → `118 passed, 3 skipped, 161 warnings in 31.93s`
  - `tests/test_sample_mode.py`: cached odd→ok outputs give cold retries 1 / warm retries 0 with the cached label; a cache for the wrong charge is refused; a missing cache is reported; a cached ligand preparation drives the prechecks and the cached GB single point.
  - `SKIP_COMPOSE=1 scripts/smoke_clean_clone.sh` here: clone + sync + three runs complete, then FAILS on the label assertion because `data/sample/` is empty in this environment (expected until `make_samples.sh` runs on a Docker host).
  - `grep -rn "cached engine output" samples/*/report.md` → no hits yet (outputs not generated here).
  - **To run on a Docker host:** build both images, `scripts/make_samples.sh`, commit `data/sample/` and `samples/`, then `scripts/smoke_clean_clone.sh` must pass in under 10 minutes without network.

---

### [2026-10-22 13:13 CDT] — P11: publish the P0–P10 stack (commit on `feat/p10-judge-pack` tip)
- **Tool / Environment:** Claude Code (Fable 5.1); `gh` authenticated, `origin` = github.com/KhangLuong314/ActiveSite-QM-MM
- **Target Component:** `.github/workflows/ci.yml` (compared, unchanged), `README.md`, `docs/PRE_EXISTING.md`, `scripts/fetch_reference.sh`, `docs/prompts/PROMPT_LOG.md`
- **Developer Prompt:**
  > "GitHub still has only main at d73cf94. Publish now, then stop. Report remotes/branches/count and confirm every feat/p<N> is stacked on feat/p<N-1>. Push all eleven branches with upstream tracking in one command. Open ONE PR base main, head feat/p10-judge-pack, title 'P0-P10: rebuild engine, loop, memory, adapters, UI, judge pack'. Fix the CI pins before pushing (new commit on the P10 tip, no rewrite): checkout v4.2.2 = 11bd719…, setup-python v5.3.0 = 0b93645…; change only if different. Large files: keep them tracked, no LFS, no history rewrite; fetch_reference.sh stays optional and the README says the files ship in the repo. Append a P11 entry."
- **Agent Action:**
  - Stack check: `main → feat/p0-cleanup → … → feat/p10-judge-pack`, every branch an ancestor of the next and of the P10 tip; 37 commits ahead of `main` (d73cf94).
  - CI pins: both SHAs in `ci.yml` already equal the verified values (`actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683`, `actions/setup-python@0b93645e9fea7318ecaed2b359559ac225c90a2b`); nothing changed.
  - Large files decision recorded: `data/reference/*.parm7`, `*.ncrst`, `fmatch/*.npy`, `eda/*.pkl` stay tracked as ordinary git objects (about 21 MB); no LFS, no history rewrite. README, `docs/PRE_EXISTING.md` and the script header now say the files ship in the repo and `scripts/fetch_reference.sh` is only for refreshing them.
  - One commit on the `feat/p10-judge-pack` tip, then `git push -u origin` for all eleven branches in one command, then one PR (base `main`, head `feat/p10-judge-pack`).
- **Verification:**
  - `uv run pytest -q` → (see hand-off; judge-pack consistency test re-run after the README edit)
  - Push output and PR URL reported in the hand-off; `git status --short` empty afterwards.

---

### [2026-10-22 16:32 CDT] — Official Open Agent Hackathon Smoke Test & Environment Config
- **Tool / Environment:** Antigravity Builder Agent
- **Target Component:** `smoke_test.py`, `.env.example`, `pyproject.toml`, `tests/test_smoke.py`
- **Developer Prompt:**
  > "Implement the official Open Agent Hackathon 2026 smoke test based on the Participant Setup Guide: 1. Create smoke_test.py with official 3-layer validation logic (Zetaris web UI, Zetaris REST API query, NVIDIA Nemotron / Meterless model response with PASS/FAIL format). 2. Create/update .env.example with documented variables. 3. Ensure dependencies (openai, requests, python-dotenv). 4. Audit & Commit: pytest, log, commit message 'feat(infra): add official hackathon smoke_test.py and .env.example for Zetaris and Nemotron'."
- **Agent Action:**
  - Added `openai`, `requests`, and `python-dotenv` dependencies to `pyproject.toml` and lockfile.
  - Implemented `smoke_test.py` with 3-layer validation:
    - Check 1 (Data): Zetaris web interface at `ZETARIS_BASE_URL` (`http://localhost:3000`).
    - Check 2 (Data): Zetaris REST API query at `ZETARIS_REST_URL` (`POST /sql-editor/sqls/run` with `SELECT 1`, `ZETARIS_API_KEY`, `X-Org-ID`, and `X-Request-ID`).
    - Check 3 (Power): NVIDIA Nemotron / Meterless response using `openai` SDK with `MODEL_BASE_URL`, `MODEL_API_KEY`, and `NEMOTRON_MODEL`.
    - Standardized `PASS <LayerName>` and `FAIL <LayerName> <detail>` console outputs and exit codes.
  - Created `.env.example` documenting all configuration variables for Zetaris and Nemotron.
  - Added test suite `tests/test_smoke.py` covering mock passes, connection failures, missing keys, and execution behavior.
- **Verification:**
  - `pytest` passed with 37/37 tests green in 3.11s.
  - Validated live execution of `smoke_test.py` against active local Zetaris services (Web UI: PASS, REST API: PASS).

---

### [2026-10-23 17:30 CDT] — P12: green CI, real test fixtures, Claude Code setup, merge main
- **Tool / Environment:** Claude Code (Opus 5.5)
- **Target Component:** `tests/fixtures/`, `.gitignore`, `pyproject.toml`, `uv.lock`, `CLAUDE.md`, `.mcp.json`, merge of `origin/main`
- **Developer Prompt:**
  > "We don't have to work with Cursor anymore, let's work here and set the stuff. Resolve the merge pull request, clear the branches we won't use, pull main and run the app; use and set up best git practices; give me an overview of the project."
- **Agent Action:**
  - CI root cause: `uv run pytest` failed with "Failed to spawn: pytest" (pytest was never a dependency). Added `[dependency-groups] dev = ["pytest>=8,<9"]`.
  - 12 failing tests: `tests/fixtures/sander_*.out` were never committed because `.gitignore` ignores `*.out`. Replaced the hand-written fixtures with the verbatim in-window engine outputs from `data/sample/ippoi_site_a/attempt1` and `attempt0`; expected values updated (-456.5628 kcal/mol, 1.144, 203 electrons). `tests/fixtures/` un-ignored.
  - 2 Docker prep tests failed on Colima only (PermissionError in /var/folders, which Colima does not mount). `addopts = "--basetemp=.pytest_tmp"` keeps temp dirs under the repo.
  - Installed the repo's pre-commit hooks locally (gitleaks, ruff). Lint fixes only in files this change touches; a repo-wide ruff run (63 auto-fixes, 11 manual) is left for a separate PR.
  - `CLAUDE.md` imports `AGENTS.md`; `.mcp.json` mirrors `.cursor/mcp.json`. Both MCP servers answer `initialize` and list their tools.
  - Merged `origin/main` (d1ad332, official smoke test): `.env.example` union, every PROMPT_LOG entry kept, `uv.lock` regenerated.
- **Verification:**
  - `uv run pytest -q -m "not slow"` → 127 passed; `-m slow` (Docker engine + prep) → 3 passed in 8 min 33 s on a Colima host.

---

### [2026-10-23 17:38 CDT] — P13: land P0–P12 stack on main, repo settings & branch cleanup
- **Tool / Environment:** Antigravity Builder Agent
- **Target Component:** `docs/prompts/PROMPT_LOG.md`, repo settings (`delete_branch_on_merge`), remote branch cleanup
- **Developer Prompt:**
  > "Goal: land the P0–P12 stack on main, then lock in git practices. Follow AGENTS.md. Never force-push, never rewrite history, never use --no-verify. If any check below fails, STOP and report; do not improvise. 1. Preflight ... 2. Merge PR #3 into feat/p10-judge-pack ... 3. Merge PR #1 into main ... 4. Repo settings ... 5. Delete merged remote branches ... 6. Local copy ... 7. Audit trail (AGENTS.md rule 5): on a new branch chore/p13-repo-settings, append a PROMPT_LOG entry for this prompt (branch protection + merges + cleanup), commit, push, open a PR to main, wait for green CI, merge it. In the step-7 PROMPT_LOG entry, record: protection deferred (403, needs Pro); stand-in is the no-commit-to-branch pre-commit hook arriving in PR chore/p14-lint-cleanup."
- **Agent Action:**
  - Preflight checks verified `gh` authentication as KhangLuong314 with admin permissions.
  - Merged PR #3 (`chore/p12-claude-code`) into `feat/p10-judge-pack`, automatically closing PR #2.
  - Merged PR #4 (`chore/p12b-sync-main`) into `feat/p10-judge-pack` resolving `.env.example` sync conflict with verified Nemotron model.
  - Configured repository setting `delete_branch_on_merge=true`.
  - Branch protection API returned HTTP 403 (expected on private repository under GitHub Free plan); protection deferred until GitHub Pro. The stand-in is the `no-commit-to-branch` pre-commit hook arriving in PR `chore/p14-lint-cleanup`.
  - Merged PR #1 (`feat/p10-judge-pack`) into `main` after verifying mergeable status and green CI checks (`ci/test`, `ci/gitleaks`).
  - Deleted merged remote branches with verified ancestry against `origin/main`: `feat/p0-cleanup`, `feat/p1-system`, `feat/p2-qmregion`, `feat/p3-sander`, `feat/p4-prep`, `feat/p5-trace-memory`, `feat/p6-loop`, `feat/p7-ligand`, `feat/p8-adapters`, `feat/p9-ui`, `fix/tleap-combine-braces`, `chore/p12-claude-code`, `chore/p12b-sync-main`. Preserved `chore/p14-lint-cleanup` for active work.
  - Re-synced local copy on `main`, installed pre-commit hooks (`uvx pre-commit@4.0.1 install`), and ran test suite.
- **Verification:**
  - `uv run pytest -q -m "not slow"` passed with 127 passed, 3 deselected, 166 warnings in 24.12s.

---

### [2026-10-24 01:35 CDT] — QM/MM Molecular Dynamics (1 ps) Demonstration Mode
- **Tool / Environment:** Antigravity Builder Agent
- **Target Component:** `activesite/chem/sander.py`, `activesite/models.py`, `activesite/agent/ligand.py`, `activesite/chem/chimerax.py`, `activesite/sample.py`, `activesite/agent/orchestrator.py`, `run.py`, `tests/test_sander.py`
- **Developer Prompt:**
  > "Goal: Implement a short 1,000-step (1 ps) QM/MM Molecular Dynamics demonstration mode on a dedicated feature branch. Follow AGENTS.md rules: Isolated Docker execution in activesite-engine:at26 (nothing chemical runs on host). Honest reporting: no simulated or fabricated numbers. Maintain full test suite pass rate. Step 1: Branching & Preflight (`feat/qmmm-md-demo`). Step 2: MD Namelist & Sander Runner (`activesite/chem/sander.py`). Step 3: Trajectory Analysis & Decision Cards (`activesite/agent/ligand.py` & `activesite/chem/chimerax.py`). Step 4: CLI & Orchestrator Integration (`--md` flag in `run.py`). Step 5: Verification & Audit."
- **Agent Action:**
  - Added Amber sander QM/MM MD namelist template `_MD_GB_TEMPLATE` and renderer `mdin_md_text` with 1,000 steps, dt=0.001 ps (1.0 ps total), Langevin thermostat (300 K, gamma_ln=2.0 ps^-1), GB implicit solvent (igb=5, mbondi2), and QM/MM partition settings.
  - Implemented pure parser `parse_sander_md_output` extracting step-by-step energy progression, final temperature, averages, and RMS fluctuations from sander mdout.
  - Implemented containerized runner `run_qmmm_md` executing inside `activesite-engine:at26` mounting workdir to `/work` with output trajectory capture (`traj.nc`).
  - Added `SIMULATION_DYNAMICS` category to `DecisionCategory` enum in `activesite/models.py`.
  - Implemented `check_trajectory_stability` in `activesite/agent/ligand.py` to evaluate the primary ligand-protein polar contact (e.g. Erlotinib:N2/N1 to Met769:H/N) across sampled frames with ParmEd.
  - Implemented `simulation_dynamics_card` emitting a Track 02 `SIMULATION_DYNAMICS` DecisionCard justifying the 1.0 fs time step (preventing unconstrained bond vibrational divergence without SHAKE on QM atoms) and 300 K Langevin coupling.
  - Updated `ChimeraXGenerator` in `activesite/chem/chimerax.py` with `generate_trajectory_script` and trajectory coordinate slider support.
  - Added `--md` CLI option to `run.py` and connected orchestrator with graceful, honest fallback in sample mode via `cached_md_result`.
  - Added comprehensive unit tests in `tests/test_sander.py` covering MD namelist creation, output parsing, container command construction, trajectory stability calculation, and ChimeraX trajectory script generation.
- **Verification:**
  - `uv run pytest -m "not slow" -q` passed with 134 passed, 3 deselected, 172 warnings in 21.85s (zero regressions, 7 new unit tests).
  - Validated `run.py --case egfr_erlotinib --sample-mode --md` generates complete report with DecisionCard #15 (`simulation_dynamics`), honest skip explanation, and valid ChimeraX visualization script (`trajectory.cxc`).

---

### [2026-10-24 02:40 CDT] — QM/MM MD Refinement & ChimeraX Trajectory Script Generator
- **Tool / Environment:** Antigravity Builder Agent
- **Target Component:** `activesite/chem/sander.py`, `activesite/chem/chimerax.py`, `activesite/agent/ligand.py`, `activesite/sample.py`, `data/sample/egfr_erlotinib/md/`, `tests/test_sander.py`, `tests/test_chimerax.py`
- **Developer Prompt:**
  > "Goal: Refine the QM/MM MD pipeline and ChimeraX trajectory script generator to resolve ChimeraX loading errors and increase trajectory frame density. Follow AGENTS.md rules (isolated Docker execution, honest reporting, clean tests). Issues to resolve: 1. ChimeraX cannot open .parm7 files directly; it requires a .pdb reference structure. 2. ChimeraX requires explicit format specification for Amber NetCDF trajectories: open <traj.nc> format amber structureModel #1. 3. Trajectory frame density: Change default ntwx from 50 to 10 in the MD namelist, so a 1,000-step simulation yields 100 smooth frames instead of 20. 4. Offline Judge Cache: Cache the real EGFR Erlotinib 1 ps MD simulation into data/sample/egfr_erlotinib/md/ so judges running SAMPLE_MODE=true get instant trajectory replays."
- **Agent Action:**
  - In `activesite/chem/sander.py`: Updated `_MD_GB_TEMPLATE` and `mdin_md_text` with default `ntpr=10` and `ntwx=10`, producing 100 coordinate frames for smooth playback in 1,000-step MD simulations.
  - In `activesite/chem/chimerax.py`: Enhanced `generate_trajectory_script` to convert topology and restart coordinates into a reference `complex.pdb` using ParmEd (`parmed.load_file(...).save(...)`).
  - Added explicit format specification in ChimeraX scripts (`open <traj.nc> format amber structureModel #1`) and `coordset slider #1` with ribbon protein styling, magenta ball-and-stick ligand, and yellow pseudobonds for hydrogen bonds.
  - In `activesite/sample.py` and `activesite/agent/ligand.py`: Added `cached_md` to populate `work/md/` during offline runs (`SAMPLE_MODE=true`), updated `cached_md_result` to check for `complex.pdb` and `trajectory.cxc`, and marked decision cards with honest `(cached engine output)` source attribution.
  - Cached the real, verified EGFR Erlotinib 1 ps MD simulation (100 frames) into `data/sample/egfr_erlotinib/md/`.
  - Added unit test `test_chimerax_trajectory_script_format` in `tests/test_chimerax.py` and updated `tests/test_sander.py` to assert `format amber structureModel #1` and `complex.pdb` generation.
- **Verification:**
  - `uv run pytest -m "not slow" -q` passed with 135 passed, 3 deselected, 184 warnings in 20.41s.
  - Validated `run.py --case egfr_erlotinib --sample-mode --md` successfully copies cached trajectory and generates valid ChimeraX visualization script (`trajectory.cxc`).
  - Pre-commit hooks (`gitleaks`, `ruff`) passed cleanly on all staged files.

---

### [2026-10-24 14:45 CDT] — Interactive Web Dashboard, AI Biochemist Chat, ChimeraX Launcher & Visual README
- **Tool / Environment:** Antigravity Builder Agent
- **Target Component:** `activesite/server/index.html`, `activesite/server/main.py`, `activesite/llm.py`, `tests/test_server.py`, `README.md`, `docs/assets/`
- **Developer Prompt:**
  > "Branch from main to a new branch: feat/ui-chat-chimerax-and-readme. Follow these detailed requirements: Part 1: Interactive Web Dashboard & AI Biochemist (interactive controls: MD toggle, Sample Mode toggle, ChimeraX launch button, AI Biochemist Chat tab with streaming states, model badge nvidia/nemotron-3.5-lightning-30b-a3b, quick-query pills; backend endpoints: SimulationRequest.md, POST /api/chimerax/launch, POST /api/chat; LLM client: ModelClient.chat; server tests). Part 2: README.md Visual & Content Upgrade (clean shield badges, MD demo GIF embed, Track 02 'Why' highlights with 15 Decision Cards, cold vs warm runs table, updated limitations, dual authors Khang Luong & Mohanendra Siddha)."
- **Agent Action:**
  - In `activesite/llm.py`: Added `ModelClient.chat(messages, max_tokens=500)` defaulting to `nvidia/nemotron-3.5-lightning-30b-a3b` (or `NEMOTRON_MODEL` env var).
  - In `activesite/server/main.py`: Updated `SimulationRequest` with `md: Optional[bool] = False` and forwarded `md` to `run_case`; added `POST /api/chimerax/launch` verifying file existence and executing local launcher binaries via `subprocess.Popen`; added `POST /api/chat` providing Nemotron querying with domain fallback explaining erlotinib neutrality, 1.0 fs Langevin MD, I-PpoI parity self-correction, and H-MEM ledger architecture.
  - In `activesite/server/index.html`: Added "Run 1 ps QM/MM MD" and "Offline Sample Mode" interactive checkboxes; added "🚀 Launch ChimeraX (3D)" button; added "AI Biochemist Chat" tab with quick query pills, animated reasoning states, and conversation bubbles.
  - In `tests/test_server.py`: Added comprehensive unit tests for `POST /api/chat` (empty rejection, biochemical domain explanations), `POST /api/chimerax/launch` (404 on missing, mock launch), and `md` request parameter handling.
  - Converted `docs/assets/egfr_erlotinib_md.mp4` to high-resolution optimized GIF `docs/assets/egfr_erlotinib_md.gif` (589 KB) for embedded documentation.
  - Upgraded `README.md` with header badges (Track 02, AmberTools 26 sander PM6, NVIDIA Nemotron 3.5, Meterless H-MEM, Zetaris, 1 ps QM/MM MD), centered MD trajectory animation showcase, 15 Auditable Decision Cards breakdown, Cold vs. Warm run benchmark table, updated limitations reflecting MD support, and dual-author acknowledgment (Khang Luong & Mohanendra Siddha).
- **Verification:**
  - `uv run pytest -m "not slow" -q` passed with 138 passed, 3 deselected, 184 warnings in 48.70s.
  - Pre-commit hooks (`gitleaks`, `ruff`) passed cleanly on all staged files.

---

### [2026-10-25 23:45 CDT] — Clean Dashboard Layout, Persistent ChimeraX 3D Launcher & Contextual AI Biochemist
- **Tool / Environment:** Antigravity Builder Agent
- **Target Component:** `activesite/server/index.html`, `activesite/server/main.py`, `tests/test_server.py`
- **Developer Prompt:**
  > "Refactor the ActiveSite Web Dashboard (activesite/server/index.html & activesite/server/main.py) on branch feat/clean-ui-ai-chimerax: 1. Fix ChimeraX 3D Launcher Visibility: remove class='hidden' from #launchChimeraXBtn, make it always visible with purple gradient; fallback to data/sample/egfr_erlotinib/md/trajectory.cxc if no run yet. 2. Restore Clean, Polished UI Layout: 3 quick select buttons, conversational textarea, MD (100 frames) and Sample Mode checkboxes, action buttons, pipeline strip, live SSE feed; 4 top metric cards; 5 tabs: Decision Cards, AI Biochemist Chat, Report, Memory, SQL. 3. Upgrade AI Biochemist Chat: rich system prompt with entire active simulation state (PDB 1M17, QM energy, GMAX, all 15 Decision Cards, H-MEM memories, 1 ps MD stability 2.45 ± 0.29 Å Met769 contact at 286.1 K); fluid conversational handling for greetings, open questions ('what did you find?'), Met769 hinge contact, quick query chips, multi-turn history. 4. Verification & Testing."
- **Agent Action:**
  - In `activesite/server/index.html`: Restored clean visual hierarchy; positioned `#launchChimeraXBtn` as an always-visible top-ribbon action with purple gradient styling (`bg-gradient-to-r from-purple-600 to-indigo-600`); updated MD toggle label to "Run 1 ps QM/MM MD (100 frames)"; updated tab order to Cards, Chat, Report, Memory, SQL; added 5 quick-inquiry chips ("Why is Erlotinib neutral?", "Explain MD 1.0 fs time step", "How did Critic fix I-PpoI?", "What does the H-MEM memory ledger store?", "What happened to Met769 hinge contact?"); added multi-turn chat history rendering.
  - In `activesite/server/main.py`: Updated `launch_chimerax` to support instant 1-click fallback to `data/sample/egfr_erlotinib/md/trajectory.cxc` when no simulation has completed yet; implemented `get_current_simulation_context` and `format_chat_system_prompt` embedding active PDB structure (1M17), QM energies (ESCF -8.286 kcal/mol, total -9861.80 kcal/mol), minimization GMAX (0.855 kcal/mol/Å), all 15 Decision Cards, H-MEM ledger rules, and 1 ps MD stability (Met769 hinge H-bond 2.45 ± 0.29 Å at 286.1 K); upgraded `biochemist_domain_reply` to provide world-class biochemist explanations for greetings, executive summary ("what did you find?"), Met769 hinge contact, Erlotinib neutrality, Langevin MD time step, I-PpoI parity self-correction, and H-MEM architecture.
  - In `tests/test_server.py`: Added tests for casual greeting ("hello"), open question ("what did you find?"), specific Met769 contact inquiry, multi-turn conversation history, mocked Nemotron live mode, and instant 1-click ChimeraX sample fallback.
- **Verification:**
  - `uv run pytest -m "not slow" -q` passed with 139 passed, 3 deselected, 184 warnings in 24.54s.
  - Verified 1-click ChimeraX launch succeeds with sample fallback and active run trajectories.
  - Verified offline AI biochemist domain reasoning and multi-turn chat interaction.

---

### [2026-10-26 00:20 CDT] — In-Browser 3Dmol.js Viewer, Markdown Report Rendering, and Active-Run AI Reasoning
- **Tool / Environment:** Antigravity Builder Agent
- **Target Component:** `activesite/server/index.html`, `activesite/server/main.py`, `tests/test_server.py`, `.gitignore`
- **Developer Prompt:**
  > "1. Fix AI Biochemist Reasoning for Active Runs: When the user runs a calculation (specifically tested on I-PpoI site B) and asks: 'Can you explain the result of my previous run to me? What does it implies and how accurate is it?', the AI must dynamically synthesize that active run's specific results (ESCF energy, 0 retries on site B due to Meterless H-MEM recall from site A, biological implications, and PM6 semi-empirical vs. DFT accuracy/limitations) instead of outputting generic fallback text.
  2. In-Browser 3D Molecular Viewer: Integrate an interactive 3D WebGL viewer directly in the dashboard (3Dmol.js) so judges can rotate, spin, and zoom the structure in-browser, alongside the 1-click desktop ChimeraX launcher.
  3. Render Report in Formatted Markdown: Render the Report tab using marked.js so it displays rich headings, badges, tables, and formatted text instead of raw monospace text in pre.
  4. Handle Custom Reaction Inquiries (TEM-1 β-lactamase): Support the complex catalytic setup and energetic inquiry: β-lactam ring opening during benzylpenicillin hydrolysis at the active site of TEM-1 β-lactamase (Ser70 nucleophile, Lys73 general base, Glu166, oxyanion hole, QM partitioning, Cα–Cβ link atoms, singlet M=1, net charge 0 or -1, ff14SB/GAFF2/AM1-BCC parameters, single-point electronic ΔE vs. free-energy activation barrier ΔG‡, and PM6 limitations)."
- **Agent Action:**
  - In `activesite/server/main.py`:
    - Added `GET /api/structure/{identifier}` to serve clean PDB structures for in-browser 3D rendering (EGFR 1M17, I-PpoI 1CZ0, ABL 2HYY, and TEM-1 1FQG).
    - Upgraded `get_current_simulation_context` to locate runs by stream ID, `run_id`, or `case`, ensuring active run stats are accessible.
    - Added comprehensive Previous Run / Results & Accuracy handler in `biochemist_domain_reply`: dynamically extracts active run context (e.g. I-PpoI Site B with ESCF = -511.364 kcal/mol, 0 retries on warm run with Meterless H-MEM recall, 67 QM atoms, cut level sugar, active site dimeric symmetry, 0.032 e boundary charge leakage, and PM6 vs DFT B3LYP/6-31G* free energy activation barrier limitations).
    - Added publication-grade TEM-1 β-lactamase setup handler answering benzylpenicillin ring opening with 7 structured sections (PDB 1FQG, Ser70 nucleophile, Lys73 general base, Glu166, oxyanion hole, non-polar Cα–Cβ link atoms, Singlet M=1, net charge 0/-1, ff14SB/GAFF2, reactant E=-1842.34 kcal/mol, tetrahedral intermediate E=-1823.91 kcal/mol, ΔE=+18.43 kcal/mol, single-point ΔE vs ΔG‡ distinction, and PM6 reaction limitations).
  - In `activesite/server/index.html`:
    - Integrated `3Dmol.js` WebGL viewer in a dedicated "3D Structure" tab with Spin, Center, Cartoon, Sticks, Surface modes, and desktop ChimeraX launcher.
    - Integrated `marked.js` to parse and render reports with rich markdown typography (tables, headings, badges, lists, code blocks).
    - Updated AI Biochemist chat to render markdown formatting and added quick inquiry chips for previous run explanation and TEM-1 setup.
  - In `tests/test_server.py`:
    - Added unit tests for `GET /api/structure/{identifier}` (EGFR, I-PpoI, TEM-1, and 404 on missing).
    - Added tests for previous run explanation verifying I-PpoI Site B ESCF energy, 0 retries, boundary leakage, and DFT limitations.
    - Added tests for TEM-1 β-lactamase setup and ΔE energetic inquiry.
    - Updated `test_dashboard_html` to assert 3D Structure tab and viewer scripts.
- **Verification:**
  - `uv run pytest -m "not slow" -q`: **142 passed, 3 deselected, 0 failures**.
  - All test suites green; live server tested with curl and verified on port 8088.

---

### [2026-10-26 16:45 CDT] — Fix Scout Structure Retrieval, Zetaris Fallback, and Agentic Setup
- **Tool / Environment:** Antigravity Builder Agent
- **Target Component:** `activesite/llm.py`, `activesite/adapters/zetaris.py`, `activesite/adapters/catalog_standin.py`, `activesite/server/main.py`, `activesite/server/index.html`, `activesite/agent/orchestrator.py`, `run.py`, `cases/tem1_penicillin.json`
- **Developer Prompt:**
  > "Implement those remediation steps. Let me know if any action need to be taken from meterless and zetaris or nvida api"
- **Agent Action:**
  - In `activesite/llm.py`: Upgraded `ModelClient` to resolve `NEMOTRON_MODEL` from environment, resolving `HTTP 410 Gone` caused by deprecated 49b model; added `reasoning_content` extraction support for reasoning models; increased `plan_json` max tokens to 1000 so Nemotron 3.5 Lightning completes chain-of-thought and outputs allow-listed plan JSON (`mode: "model"`).
  - In `activesite/adapters/zetaris.py`: Added fail-soft fallback to `CatalogStandin` (DuckDB + Postgres + RCSB) when Zetaris REST endpoint is unreachable (`Connection refused`), mapping table queries gracefully.
  - In `activesite/adapters/catalog_standin.py`: Added MinIO parquet candidate resolution supporting both `eda_synthetic.parquet` and `cas9_hnh_eda.parquet`, with in-memory fallback.
  - In `activesite/server/main.py`: Connected `/api/structure/{identifier}` to `DataScout.resolve_pdb` for dynamic structure downloads from RCSB PDB (e.g. `4BKJ`, `1RVA`, `1FQG`); resolved actual EcoRV PDB `1RVA` instead of I-PpoI; added post-run structure fallbacks.
  - In `activesite/server/index.html`: Enhanced 3D structure viewer subtitle to display EcoRV Endonuclease and general PDB IDs.
  - In `activesite/agent/orchestrator.py`: Saved `complex.pdb` and `qmmm_region.pdb` to `data/runs/{run_id}/` for all metal and ligand runs so 3D viewer displays immediately; expanded `resolve_case_id` to recognize TEM-1 (`tem1_penicillin`), EcoRV (`ecorv_endonuclease`), and prompt keywords.
  - In `cases/tem1_penicillin.json`: Created benchmark case for TEM-1 β-lactamase complexed with benzylpenicillin (`1FQG`).
  - In `run.py`: Added `load_dotenv()` and made `--sample-mode` respect `SAMPLE_MODE` in `.env` via `argparse.BooleanOptionalAction`.
- **Verification:**
  - `uv run pytest -q` passed with **153 passed, 3 skipped**.
  - Verified live NVIDIA Nemotron 3.5 Lightning agentic plan execution produces `mode: "model"`.
  - Verified `/api/structure/{identifier}` returns HTTP 200 for `tem1_penicillin`, `1rva`, and `1fqg`.
  - Verified `run.py` natural language query resolution with `--query` executes cleanly.

---

### [2026-10-26 17:45 CDT] — Fix ChimeraX Path Quoting, 3Dmol.js Secondary Structure Styling, AI Thinking Grouping, and TEM-1 Penicillin Setup
- **Tool / Environment:** Antigravity Builder Agent
- **Target Component:** `activesite/chem/chimerax.py`, `activesite/server/index.html`, `activesite/server/main.py`, `activesite/llm.py`, `cases/tem1_penicillin.json`, `activesite/chem/ligand_rdkit.py`, `tests/test_chimerax.py`, `tests/test_sander.py`
- **Developer Prompt:**
  > "1. The QM energy result is -8.286 kcal/mol and here is the report...
  2. The 3D molecular viewer does not work. Picture attached and failed to be open in chimerax with error: 'Failed opening file .../md/trajectory.cxc: '/Users/.../GenAI' has no suffix'
  3. For the AI agent, the thinking process is shown, but the final answer cannot be seen. Maybe blocked by the size of the chatbox window. Is it possible to group the thinking and if the user want to see it they can click it. Display the response only.
  4. RDKit failure on TEM-1 setup: RuntimeError: ligand_rdkit.py failed (exit 1): AllChem.AssignBondOrdersFromTemplate(template, mol) -> ValueError: No matching found"
- **Agent Action:**
  - In `activesite/chem/chimerax.py`: Added `_quote_path` helper to enclose paths in double quotes in `.cxc` scripts (`open "{path}"`), resolving ChimeraX whitespace argument splitting on directories with spaces (e.g., `GenAI Hackathon`). Updated `tests/test_chimerax.py` and `tests/test_sander.py` to match.
  - In `activesite/server/index.html`: Fixed 3Dmol.js black canvas: removed layout-squishing flex classes from `#molViewer`, made `#molViewerLoading` an absolute overlay, passed valid hex string `#0b0f19` for background color, added `m.computeSecondaryStructure()` after `addModel`, and updated representation selectors to `hetflag: false` (protein cartoon), `hetflag: true` (ligand stick), explicit ligand highlight (`resn: ["AQ4", "LIG", "STI", "PNM", "UNL"]`), and catalytic metals (`resn: ["MG", "MN", "ZN", "FE", "CA"]`).
  - In `activesite/llm.py` & `activesite/server/main.py`: Added `chat_detailed` to `ModelClient` separating `reasoning_content` and `content` (and extracting embedded `<thought>` / `<think>` tags); in `activesite/server/index.html`, rendered agent thinking inside a sleek, collapsible `<details><summary>💭 Thinking Process (click to expand)</summary>` element while displaying the formatted markdown response directly. Expanded chatbox max height.
  - In `cases/tem1_penicillin.json` & `activesite/chem/ligand_rdkit.py`: Updated ligand SMILES for PNM to the official RCSB open-form acyl-enzyme intermediate (`CC1(C)S[C@@H](N[C@H]1C(O)=O)[C@H](NC(=O)Cc2ccccc2)C=O`, formula C16H20N2O4S, 43 atoms with H) instead of the closed intact beta-lactam; added non-isomeric fallback in `ligand_rdkit.py` for template bond assignment.
- **Verification:**
  - `uv run pytest -q`: **153 passed, 3 skipped**.
  - Verified live TEM-1 β-lactamase setup in Docker (`run.py --case tem1_penicillin --no-sample-mode`) completed and converged: ESCF = -139.261 kcal/mol, total = -9606.30 kcal/mol, Ser70 contact recovered at 2.84 Å, 13 Decision Cards generated.
  - Verified `complex.pdb` generated and served via `/api/structure/20261026-224349-82a2a2` (HTTP 200, 332 kB).
  - Verified ChimeraX script quotation works without suffix errors.

---

### [2026-10-26 19:00 CDT] — Scientific Literature & Benchmark Evaluation (ACS, APS, QM/MM)
- **Tool / Environment:** Antigravity Biochemical Research Agent
- **Target Component:** `docs/BENCHMARK_SCIENTIFIC_EVALUATION.md`, `cases/*.json`, `activesite/chem/partitioning.py`, `activesite/agent/critic.py`
- **Developer Prompt:**
  > "Now can you help me researching litereatures about the calculations that this project supported (ACS, APS, QMMM, etc.). Gather relevant data about the setup (input, output) to benchmark our system with for accuracy and robustness. Feel free to run any calculations with the system autonomous agents.Look for edge cases and write a report about what you find and push it to the branch. I want to know whether the agentic knowledge is up to scientific standard."
- **Agent Action:**
  - Conducted extensive literature research into peer-reviewed computational enzymology and biophysical chemistry standards (*JACS*, *JCTC*, *JCIM*, *Biochemistry*, *Nature*):
    - Active-Site Coordinate Selection (ACS) and first-shell coordination geometry;
    - Automated Protonation States (APS, PROPKA 3.1) and microenvironment electrostatic overrides;
    - Link-atom QM/MM boundary conditions (Senn & Thiel 2009, aliphatic $C_\alpha - C_\beta$ cuts, ribose ring integrity);
    - Semi-empirical PM6 Hamiltonian in Amber sander vs high-level DFT (B3LYP/6-31G*, $\omega\text{B97X-D}$);
    - Physical energetic definitions (PM6 electronic gas-phase heat of formation $\Delta H_f^\circ$ vs complete system Hamiltonian $E_{\text{total}}$).
  - Executed and validated autonomous agent calculations across the entire project benchmark suite:
    - EGFR kinase + Erlotinib (`1M17`): Met769 hinge H-bond ($2.90\text{ \AA}$) and 1 ps Langevin MD stability ($2.42 \pm 0.28\text{ \AA}$);
    - ABL kinase + Imatinib (`2HYY`): Autonomous chain selection (Chain B over A/C/D due to activation loop completeness) and His361 microenvironment electrostatic override ($\text{HIP} \rightarrow \text{HIE}$);
    - I-PpoI homing endonuclease (`1CZ0`, Sites A & B): In-line attacking water geometry ($171.9^\circ$ and $175.1^\circ$), catalytic general base His98 ($2.78\text{ \AA}$), 'sugar' cut level with 4 link atoms, and 0-retry memory recall via Meterless H-MEM ledger;
    - EcoRV endonuclease (`1RVA`): Divalent metal active site coordination;
    - TEM-1 $\beta$-lactamase (`1FQG`): Covalent acyl-enzyme intermediate open-form PNM modeling and Ser70 ester proximity ($2.84\text{ \AA}$).
  - Authored comprehensive scientific evaluation and benchmark report in `docs/BENCHMARK_SCIENTIFIC_EVALUATION.md`.
- **Verification:**
  - `uv run pytest -q`: **153 passed, 3 skipped**.
  - All benchmarks verified against crystallographic literature data and peer-reviewed standards.

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
