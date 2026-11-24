#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
# DD4 control C0 (amendment A1): WSClean's dirty image of the subset, no facets.
# Usage: step4_c0.sh SUBMS SCRATCH OUTDIR
source "$(dirname "$0")/common4.sh"
sub=$1; s=$2; out=$3
if [ -e "$s" ]; then echo "$s exists" >&2; exit 1; fi
mkdir -p "$s" "$out"; cp -r "$sub" "$s/sub.ms"
wsc "$s" "$out/c0.log" -name /w/c0 "${grid[@]}" -weight natural -niter 0 -data-column DATA \
  -no-update-model-required /w/sub.ms
cp "$s/c0-dirty.fits" "$out/c0-dirty.fits"; rm -rf "$s"
