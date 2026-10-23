# samples/ — three judged inputs and their saved outputs

| case | input | outputs |
|---|---|---|
| ippoi_site_a | `ippoi_site_a/input.json` | `report.md`, `cards.json`, `trace.jsonl`, `stats.json` — pending `scripts/make_samples.sh` on a Docker host |
| ippoi_site_b | `ippoi_site_b/input.json` | same, pending |
| egfr_erlotinib | `egfr_erlotinib/input.json` | same, pending |

The outputs must come from a real run inside the build window (2026-10-22 00:00 UTC to 2026-10-27 23:45 UTC); the
generation date and commit are recorded in `data/sample/MANIFEST.md`. Hand-written outputs are not acceptable and
none are included.
