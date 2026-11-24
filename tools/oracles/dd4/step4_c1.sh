#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
# DD4 controls C0' and C1 (amendment A4): on the four-correlation copy of the
# subset, WSClean's dirty image (no facets) and its flat-gain facet image of
# DATA with the given gains; for contrast, the same facet image on the
# two-correlation MS with -diagonal-visibilities (A3).
# Usage: step4_c1.sh SUBMS SCRATCH OUTDIR SOLVED_H5 REGIONS
source "$(dirname "$0")/common4.sh"
sub=$1; s=$2; out=$3; h5=$4; reg=$5; log="$out/c1.log"
if [ -e "$s" ]; then echo "$s exists" >&2; exit 1; fi
mkdir -p "$s" "$out"; : > "$log"
cp -r "$sub" "$s/sub.ms"; cp -r "$sub" "$s/sub4.ms"
py "$(dirname "$0")/to_four_corr.py" "$s/sub4.ms" ${DD4_UNFLAG_CROSS:+--unflag-cross} >> "$log" 2>&1
cp "$h5" "$s/solved.h5"; cp "$reg" "$s/facets.reg"
facets=(-facet-regions /w/facets.reg -apply-facet-solutions /w/solved.h5 amplitude000,phase000)
common=(-weight natural -niter 0 -data-column DATA -no-update-model-required)
wsc "$s" "$log" -name /w/c0p "${grid[@]}" "${common[@]}" /w/sub4.ms
wsc "$s" "$log" -name /w/c1 "${grid[@]}" "${facets[@]}" -feather-size 0 "${common[@]}" /w/sub4.ms
wsc "$s" "$log" -name /w/c1d "${grid[@]}" "${facets[@]}" -diagonal-visibilities -feather-size 0 "${common[@]}" /w/sub.ms
cp "$s/c0p-dirty.fits" "$s/c1-image-pb.fits" "$s/c1-dirty.fits" "$s/c1d-image-pb.fits" "$out/"
rm -rf "$s"
