# AGENTS.md — rules for every agent working in this repo

ActiveSite-QM-MM — Open Agent Hackathon 2026, Track 02 "The Agent That Can Explain Why".
Build window: 2026-10-22 00:00 UTC → 2026-10-27 23:45 UTC. Mid-build checkpoint 2026-10-24.
Feature freeze 2026-10-26 18:00 CDT. The engine is being rebuilt one module per prompt
(P0 cleanup, P1 system, …). These rules apply to every prompt in that series.

## Rules for every prompt

1. **One branch per prompt** (`feat/p0-cleanup`, `feat/p1-system`, …). Never commit to `main`.
   Never `--no-verify`. Small commits with the *why* in the message. The maintainer opens and merges PRs.
2. **Never fabricate a number.** If an engine did not run, the value is `null` and every output
   (report, API, UI, CLI) says so. No reference tables, no "realistic variance", no default energies.
3. **Chemistry binaries run only inside Docker** (`.cursorrules` rule 3). If `docker info` fails in
   the build environment, implement and unit-test with text fixtures and list the engine checks
   under "to run on a Docker host" in the hand-off.
4. **Ask before adding a dependency.** Treat model output and user input as untrusted:
   allow-lists, parameterised SQL, no `eval`.
5. **Append one entry to `docs/prompts/PROMPT_LOG.md` per prompt**, using its template.
6. **End every prompt with:** files changed (one line each), `uv run pytest -q` output,
   acceptance checklist with ✅/❌, open questions. Then stop.

## The five mandatory agent principles (from `.cursorrules`)

1. **Explain Why (Track 02 core):** every autonomous choice (active-site radius, link-atom cuts,
   protonation states, formal charges) generates a structured Decision Card with `decision_id`,
   `choice`, `alternatives`, `rationale`, `confidence`.
2. **Judge execution constraint:** always keep a `SAMPLE_MODE=true` offline path. Benchmarks must run
   on an ordinary CPU in under 5 minutes with no mandatory API keys.
3. **Clean host machine:** never install Amber or other chemistry binaries on the host. All
   computational chemistry runs inside Docker containers.
4. **Episodic learning:** when a simulation error occurs (odd-electron spin mismatch, bad contact,
   charge discrepancy) the Critic diagnoses, self-corrects, and records the lesson in Meterless H-MEM
   so later runs succeed first time. The ledger starts empty; nothing is pre-seeded.
5. **Prompt audit trail:** log significant prompt workflows and agent iterations in
   `docs/prompts/PROMPT_LOG.md`.

## Current honesty markers

- `ChemistryRunner.run_simulation` runs one `sander` single point via `activesite/chem/sander.py`
  inside `activesite-engine:at26`. If SAMPLE_MODE is on, Docker/image is missing, or the system has no
  Amber topology, it returns `success=False`, `energy_* = None` and an `error_message` naming the reason.
- The MCP data catalog is **catalog-STANDIN (DuckDB)**, a local stand-in until Zetaris credentials
  (`ZETARIS_REST_URL`, `ZETARIS_API_KEY`) are configured. See `.env.example`.
