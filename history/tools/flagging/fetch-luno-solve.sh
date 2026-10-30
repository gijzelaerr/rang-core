#!/usr/bin/env bash
# Inputs for the LUNO solved-gain survey (research/flagging-luno-solved.md): the small
# subtables, the remaining MAIN_1 row columns (chunk 0) and, with --data, DATA tiles
# 8-23 of MAIN_1 row chunk 0. Build the MS afterwards with examples/build_luno_ms.py.
set -euo pipefail
cd "$(dirname "$0")/../.."
out="${1:?Usage: bash tools/flagging/fetch-luno-solve.sh outputs/fresh-dir [--data]}"
case "$out" in outputs/*) ;; *) echo "Directory must be beneath outputs/" >&2; exit 2 ;; esac
bucket=https://ratt-public-data.s3.af-south-1.amazonaws.com
store=LBAND_LUNO_CALIBRATORS.zarr
get() {  # key -> exclusive local file, record bytes + sha256
  local key="$1" dest="$out/$1"
  test ! -e "$dest"
  mkdir -p "$(dirname "$dest")"
  curl -fsS --proto =https --retry 3 -o "$dest" "$bucket/$store/$key"
  printf '%s %s %s\n' "$(stat -c %s "$dest")" "$(sha256sum "$dest" | cut -d' ' -f1)" "$key" >> "$out/receipt.txt"
}
keys() {  # prefix -> every key below it, following S3 ListObjectsV2 pagination
  local token="" page
  while :; do
    page=$(curl -fsS --proto =https -G "$bucket/" --data-urlencode list-type=2 \
      --data-urlencode "prefix=$store/$1" ${token:+--data-urlencode "continuation-token=$token"})
    grep -o '<Key>[^<]*</Key>' <<<"$page" | sed -e 's/<Key>//' -e 's#</Key>##' -e "s#^$store/##"
    token=$(grep -o '<NextContinuationToken>[^<]*' <<<"$page" | sed 's/<NextContinuationToken>//' || true)
    [ -n "$token" ] || break
  done
}
if [ "${2:-}" = --data ]; then
  test -d "$out"
  get MAIN/MAIN_1/DATA/.zarray
  for t in $(seq 8 23); do get "MAIN/MAIN_1/DATA/0.$t.0"; done
else
  test ! -e "$out"
  mkdir -p "$out"
  get .zgroup
  for table in ANTENNA FEED SPECTRAL_WINDOW POLARIZATION DATA_DESCRIPTION FIELD OBSERVATION STATE PROCESSOR; do
    keys "$table/" | while read -r key; do get "$key"; done
  done
  get MAIN/.zgroup
  get MAIN/MAIN_1/.zattrs
  get MAIN/MAIN_1/.zgroup
  for c in UVW INTERVAL EXPOSURE TIME_CENTROID FEED1 FEED2 ARRAY_ID OBSERVATION_ID \
           PROCESSOR_ID STATE_ID SIGMA WEIGHT; do
    get "MAIN/MAIN_1/$c/.zarray"
    for key in $(keys "MAIN/MAIN_1/$c/0" | grep -E "/$c/0(\.0)*$"); do
      get "$key"
    done
  done
fi
awk '{s+=$1} END {print NR " objects, " s " bytes"}' "$out/receipt.txt"
