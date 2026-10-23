#!/usr/bin/env bash
# OPTIONAL. The large reference files ship in the repo; a clean clone never needs this script.
# Refresh the large reference files (parm7, ncrst, fmatch npy, eda pkl) from REFERENCE_URL (http base) or
# REFERENCE_PATH (local directory mirroring data/reference/) and verify SHA-256 against data/reference/LARGE_FILES.sha256.
set -euo pipefail
cd "$(dirname "$0")/.."
MANIFEST=data/reference/LARGE_FILES.sha256
[[ -f "$MANIFEST" ]] || { echo "missing $MANIFEST"; exit 1; }
while read -r sha path; do
  if [[ -f "$path" ]] && echo "$sha  $path" | sha256sum -c --quiet - 2>/dev/null; then
    echo "ok       $path"; continue
  fi
  mkdir -p "$(dirname "$path")"
  rel="${path#data/reference/}"
  if [[ -n "${REFERENCE_PATH:-}" && -f "$REFERENCE_PATH/$rel" ]]; then
    cp "$REFERENCE_PATH/$rel" "$path"; echo "copied   $path"
  elif [[ -n "${REFERENCE_URL:-}" ]]; then
    curl -fsSL "${REFERENCE_URL%/}/$rel" -o "$path"; echo "fetched  $path"
  else
    echo "missing  $path (set REFERENCE_URL or REFERENCE_PATH)"; continue
  fi
  echo "$sha  $path" | sha256sum -c --quiet - || { echo "CHECKSUM MISMATCH $path"; exit 2; }
done < "$MANIFEST"
