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
