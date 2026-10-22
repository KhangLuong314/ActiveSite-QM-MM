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
