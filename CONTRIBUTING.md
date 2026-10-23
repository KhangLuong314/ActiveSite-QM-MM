# Contributing

The rules come from `AGENTS.md`; this is the short version for humans.

- **One branch per prompt or change** (`feat/p<N>-<topic>`). Never commit to `main`; never use `--no-verify`.
  Small commits whose message says *why*. The maintainer opens and merges pull requests; branches stack in order.
- **Never fabricate a number.** If an engine did not run, the value is `null` and the report, API, UI and CLI say so.
- **Chemistry binaries run only inside Docker** (`activesite-engine:at26`, `activesite-prep:at26`). Without Docker,
  implement against text fixtures and list the engine checks under "to run on a Docker host".
- **Ask before adding a dependency.** Treat model output and user input as untrusted: allow-lists, parameterised or
  validated SQL, no `eval`.
- **Append one entry to `docs/prompts/PROMPT_LOG.md` per prompt**, using its template.
- **Every hand-off ends with:** files changed, `uv run pytest -q` output, an acceptance checklist, open questions.
- **Pre-existing data must be declared** in `docs/PRE_EXISTING.md` and the README section of the same name.

Setup: `uv sync`, `pre-commit install` (gitleaks + ruff), `uv run pytest -q`.
