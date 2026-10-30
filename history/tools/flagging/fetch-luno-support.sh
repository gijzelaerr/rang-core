#!/usr/bin/env bash
# Bounded slice for the LUNO processed-support survey (research/flagging-luno-support.md):
# row chunk 0 of groups 1 (PKS 1934-638) and 2 (PKS 1830-211), channel tiles 8-23,
# without DATA. Run the survey afterwards with examples/survey_luno_support.py.
set -euo pipefail
cd "$(dirname "$0")/../.."
out="${1:?Usage: bash tools/flagging/fetch-luno-support.sh outputs/fresh-slice}"
case "$out" in outputs/*) ;; *) echo "Slice directory must be beneath outputs/" >&2; exit 2 ;; esac
base=https://ratt-public-data.s3.af-south-1.amazonaws.com/LBAND_LUNO_CALIBRATORS.zarr
test ! -e "$out"
mkdir -p "$out"
get() {  # key -> exclusive local file, record bytes + sha256
  local key="$1" dest="$out/$1"
  mkdir -p "$(dirname "$dest")"
  curl -fsS --proto =https --retry 3 -o "$dest" "$base/$key"
  printf '%s %s %s\n' "$(stat -c %s "$dest")" "$(sha256sum "$dest" | cut -d' ' -f1)" "$key" >> "$out/receipt.txt"
}
get ANTENNA/ANTENNA_0/NAME/.zarray
get ANTENNA/ANTENNA_0/NAME/0
for g in 1 2; do
  get "MAIN/MAIN_$g/.zattrs"
  for c in ANTENNA1 ANTENNA2 TIME FLAG_ROW; do get "MAIN/MAIN_$g/$c/.zarray"; get "MAIN/MAIN_$g/$c/0"; done
  for c in FLAG WEIGHT_SPECTRUM MODEL_DATA; do
    get "MAIN/MAIN_$g/$c/.zarray"
    for t in $(seq 8 23); do get "MAIN/MAIN_$g/$c/0.$t.0"; done
  done
done
awk '{s+=$1} END {print NR " objects, " s " bytes"}' "$out/receipt.txt"
