#!/usr/bin/env bash
# Judge smoke test: fresh clone, services, deps, the three sample cases in SAMPLE_MODE, assert cached-engine label + trace.
# Env: SKIP_COMPOSE=1 to skip docker compose; SOURCE=<repo path or URL> (default: this checkout).
set -euo pipefail
START=$(date +%s)
SOURCE="${SOURCE:-$(cd "$(dirname "$0")/.." && pwd)}"
TMP=$(mktemp -d)
echo "== clone $SOURCE -> $TMP/clone"
git clone -q "$SOURCE" "$TMP/clone"
cd "$TMP/clone"
if [[ "${SKIP_COMPOSE:-0}" != "1" ]]; then docker compose up -d; fi
uv sync -q
export SAMPLE_MODE=true CATALOG_OFFLINE=1
FAIL=0
for c in ippoi_site_a ippoi_site_b egfr_erlotinib; do
  echo "== $c"
  uv run python run.py --case "$c" --json > "stats_$c.json"
  report=$(python3 -c "import json;print(json.load(open('stats_$c.json'))['report'])")
  trace=$(python3 -c "import json;print(json.load(open('stats_$c.json'))['trace'])")
  label=$(python3 -c "import json;print(json.load(open('stats_$c.json'))['engine_label'])")
  if [[ -f "$report" && -f "$trace" && "$label" == "cached engine output (sample mode)" ]]; then
    echo "   ok: $label, report $report, trace $trace"
  else
    echo "   FAIL: engine_label='$label' report=$report trace=$trace"; FAIL=1
  fi
done
echo "== total seconds: $(( $(date +%s) - START ))"
exit $FAIL
