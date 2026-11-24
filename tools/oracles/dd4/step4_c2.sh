#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
# DD4 amendment A5's controls: WSClean's flat-gain facet image of DATA with
# the given gains on two four-correlation copies of the subset: sub4m.ms
# (--matched: both hands weight min(w_XX, w_YY), flag XX|YY) and sub4e.ms
# (--equal-unflagged). Usage: step4_c2.sh SUBMS SCRATCH OUTDIR SOLVED_H5 REGIONS
source "$(dirname "$0")/common4.sh"
sub=$1; s=$2; out=$3; h5=$4; reg=$5; log="$out/c2.log"
if [ -e "$s" ]; then echo "$s exists" >&2; exit 1; fi
mkdir -p "$s" "$out"; : > "$log"
cp "$h5" "$s/solved.h5"; cp "$reg" "$s/facets.reg"
facets=(-facet-regions /w/facets.reg -apply-facet-solutions /w/solved.h5 amplitude000,phase000 -feather-size 0)
common=(-weight natural -niter 0 -data-column DATA -no-update-model-required)
for v in m e; do
  cp -r "$sub" "$s/sub4$v.ms"
  mode=$([ "$v" = m ] && echo --matched || echo --equal-unflagged)
  py "$(dirname "$0")/to_four_corr.py" "$s/sub4$v.ms" "$mode" >> "$log" 2>&1
  wsc "$s" "$log" -name "/w/c2$v" "${grid[@]}" "${facets[@]}" "${common[@]}" "/w/sub4$v.ms"
  cp "$s/c2$v-image-pb.fits" "$out/"
  rm -rf "$s/sub4$v.ms"
done
rm -rf "$s"
