#!/usr/bin/env bash
# Bounded text-metadata probe of the LUNO calibrator and target stores: OBSERVATION,
# FIELD and HISTORY string arrays (json2-encoded, not pickle) plus HISTORY TIME, and
# the S3 Last-Modified of each store root. No MAIN visibilities, weights or flags.
# Decode offline afterwards with examples/decode_luno_text.py in the pinned image.
set -euo pipefail
cd "$(dirname "$0")/../.."
out="${1:?Usage: bash tools/flagging/fetch-luno-text.sh outputs/fresh-probe}"
case "$out" in outputs/*) ;; *) echo "Probe directory must be beneath outputs/" >&2; exit 2 ;; esac
bucket=https://ratt-public-data.s3.af-south-1.amazonaws.com
test ! -e "$out"
mkdir -p "$out"
get() {  # store key -> exclusive local file (64 KiB cap), record bytes + sha256
  local store="$1" key="$2" dest="$out/$1/$2"
  mkdir -p "$(dirname "$dest")"
  curl -fsS --proto =https --max-filesize 65536 -o "$dest" "$bucket/$store/$key"
  printf '%s %s %s/%s\n' "$(stat -c %s "$dest")" "$(sha256sum "$dest" | cut -d" " -f1)" "$store" "$key" >> "$out/receipt.txt"
}
for store in LBAND_LUNO_CALIBRATORS.zarr LBAND_LUNO_TARGET.zarr; do
  printf '%s %s\n' "$store" "$(curl -fsSI --proto =https "$bucket/$store/.zgroup" | tr -d "\r" | sed -n "s/^[Ll]ast-[Mm]odified: //p")" >> "$out/last-modified.txt"
  for a in OBSERVATION/OBSERVATION_0/PROJECT OBSERVATION/OBSERVATION_0/OBSERVER \
           OBSERVATION/OBSERVATION_0/SCHEDULE_TYPE OBSERVATION/OBSERVATION_0/TELESCOPE_NAME \
           FIELD/FIELD_0/NAME FIELD/FIELD_0/CODE HISTORY/HISTORY_0/TIME \
           HISTORY/HISTORY_0/APPLICATION HISTORY/HISTORY_0/MESSAGE \
           HISTORY/HISTORY_0/ORIGIN HISTORY/HISTORY_0/PRIORITY; do
    get "$store" "$a/.zarray"; get "$store" "$a/0"
  done
  for a in OBSERVATION/OBSERVATION_0/SCHEDULE OBSERVATION/OBSERVATION_0/LOG \
           HISTORY/HISTORY_0/APP_PARAMS HISTORY/HISTORY_0/CLI_COMMAND; do
    get "$store" "$a/.zarray"; get "$store" "$a/0.0"
  done
done
awk '{s+=$1} END {print NR " objects, " s " bytes"}' "$out/receipt.txt"
