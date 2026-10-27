#!/usr/bin/env bash
# Load the DataScout tables into a running local Zetaris platform (Zetaris Cloud "Run locally" bundle).
# Usage, from the repo root:  scripts/zetaris/load.sh <path-to-zetaris-platform-folder>
# The admin login is read inside the Zetaris containers from the bundle's own .env; it is never printed here.
# DDL cannot go through the REST query API (it accepts SELECT only), so the statements run in a one-off copy of the
# bundle's bootstrap container, the same way Zetaris seeds its own sample data. Running it inside the live driver
# container hangs at the metastore step.
set -euo pipefail
ZP="${1:?path to the zetaris-platform folder}"
DEST=/home/zetaris/customer-data/shared/activesite
tmp=$(mktemp -d)
uv run python scripts/zetaris/export_tables.py "$tmp"
cp scripts/zetaris/activesite.sql "$tmp/"
driver=$(docker compose --project-directory "$ZP" ps -q driver)
docker exec "$driver" mkdir -p "$DEST"
docker cp "$tmp/." "$driver:$DEST/"
docker compose --project-directory "$ZP" run --rm --no-deps --entrypoint /bin/bash bootstrap -c \
  "bash /home/zetaris/zetaris-ndp-driver/bin/lightning-sql.sh --email \"\$ZETARIS_ADMIN_EMAIL\" --password \"\$ZETARIS_ADMIN_PASSWORD\" -f $DEST/activesite.sql" \
  2>&1 | grep -E "LightningException|Time taken: " || true
rm -rf "$tmp"
echo "Done. Check with: uv run python smoke_test.py   (expects ACTIVESITE.expert_runs: 6 rows)"
