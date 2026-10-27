# Security

## Reporting

Found a vulnerability or a committed secret? Message the maintainers privately
([@KhangLuong314](https://github.com/KhangLuong314), [@mohanendrasidda](https://github.com/mohanendrasidda))
or use GitHub's private vulnerability reporting. Don't open a public issue with the details.

## Leaked secret runbook

A key that reached GitHub, a chat or a screenshot counts as compromised, even if the commit or message is deleted
a minute later. Bots scrape new commits within seconds, and rewriting history does not un-leak it.

1. **Revoke or rotate first** at the provider (NVIDIA, Zetaris, any other API console). Do this before touching git.
2. Tell the other maintainer what leaked, when, and that it is rotated.
3. Remove it from the code; the new key goes only in your local `.env`.
4. Only if needed, scrub history (`git filter-repo`). That is cleanup, not the fix: step 1 is the fix.

## Controls in this repo

- `gitleaks` runs as a pre-commit hook and in CI on every push and pull request.
- `.env` and `.env.*` are gitignored and excluded from the Docker image; only `.env.example` (no values) is committed.
- CI actions are pinned to commit SHAs.
- A local pre-commit hook blocks commits to `main`; changes go through pull requests with green CI.
- Model output and user input are untrusted: the Planner allow-lists model output, SQL is validated and read-only,
  uploaded structure files are limited to allow-listed types (.pdb, .cif, .mmcif) and 20 MB, and chat replies cannot show numbers that no run produced.
