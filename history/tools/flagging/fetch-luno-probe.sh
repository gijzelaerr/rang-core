#!/usr/bin/env bash
# Bounded numeric-only probe of LBAND_LUNO_CALIBRATORS.zarr: group attrs, small numeric
# subtables, and one row-chunk x channel-tile of weights/sigma/flags for MAIN_0.
# Decode offline afterwards with examples/decode_luno_probe.py in the pinned image.
set -euo pipefail
cd "$(dirname "$0")/../.."
out="${1:?Usage: bash tools/flagging/fetch-luno-probe.sh outputs/fresh-probe}"
case "$out" in outputs/*) ;; *) echo "Probe directory must be beneath outputs/" >&2; exit 2 ;; esac
base=https://ratt-public-data.s3.af-south-1.amazonaws.com/LBAND_LUNO_CALIBRATORS.zarr
test ! -e "$out"
mkdir -p "$out"
get() {  # key -> exclusive local file, record bytes + sha256
  local key="$1" dest="$out/$1"
  mkdir -p "$(dirname "$dest")"
  curl -fsS --proto =https -o "$dest" "$base/$key"
  printf '%s %s %s\n' "$(stat -c %s "$dest")" "$(sha256sum "$dest" | cut -d' ' -f1)" "$key" >> "$out/receipt.txt"
}
for g in $(seq 0 19); do get "MAIN/MAIN_$g/.zattrs"; done
for k in POLARIZATION/POLARIZATION_0/CORR_TYPE/0.0 POLARIZATION/POLARIZATION_0/CORR_TYPE/.zarray \
         FIELD/FIELD_0/PHASE_DIR/0.0.0 FIELD/FIELD_0/PHASE_DIR/.zarray \
         SPECTRAL_WINDOW/SPECTRAL_WINDOW_0/CHAN_FREQ/0.0 SPECTRAL_WINDOW/SPECTRAL_WINDOW_0/CHAN_FREQ/.zarray \
         ANTENNA/ANTENNA_0/FLAG_ROW/0 ANTENNA/ANTENNA_0/FLAG_ROW/.zarray \
         ANTENNA/ANTENNA_0/POSITION/0.0 ANTENNA/ANTENNA_0/POSITION/.zarray \
         OBSERVATION/OBSERVATION_0/TIME_RANGE/0.0 OBSERVATION/OBSERVATION_0/TIME_RANGE/.zarray; do
  get "$k"
done
for c in ANTENNA1 ANTENNA2 TIME FLAG_ROW; do get "MAIN/MAIN_0/$c/.zarray"; get "MAIN/MAIN_0/$c/0"; done
for c in WEIGHT SIGMA; do get "MAIN/MAIN_0/$c/.zarray"; get "MAIN/MAIN_0/$c/0.0"; done
for c in WEIGHT_SPECTRUM SIGMA_SPECTRUM FLAG; do get "MAIN/MAIN_0/$c/.zarray"; get "MAIN/MAIN_0/$c/0.8.0"; done
awk '{s+=$1} END {print NR " objects, " s " bytes"}' "$out/receipt.txt"
