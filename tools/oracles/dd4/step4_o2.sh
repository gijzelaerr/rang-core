#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
# DD4 arm O, step 3: WSClean's corrupted facet predict (model-pb), the
# residual column, and its flat-gain facet image (-feather-size 0), on the
# four-correlation copy sub4.ms (amendment A4).
# Usage: step4_o2.sh SCRATCH CYCLEDIR REGIONS
source "$(dirname "$0")/common4.sh"
s=$1; d=$2; reg=$3; log="$d/o2.log"; : > "$log"
cp "$reg" "$s/facets.reg"; cp "$d/solved.h5" "$s/solved.h5"
cp "$d/full-model.fits" "$s/po-model.fits"; cp "$d/full-model-pb.fits" "$s/po-model-pb.fits"
facets=(-facet-regions /w/facets.reg -apply-facet-solutions /w/solved.h5 amplitude000,phase000)
wsc "$s" "$log" -predict -name /w/po "${grid[@]}" "${facets[@]}" /w/sub4.ms
py - "$s/sub4.ms" <<'PY'
import sys, casacore.tables as pt
t = pt.table(sys.argv[1], readonly=False, ack=False)
t.putcol("CORRECTED_DATA", t.getcol("DATA") - t.getcol("MODEL_DATA")); t.close()
PY
wsc "$s" "$log" -name /w/resid "${grid[@]}" "${facets[@]}" -weight natural -niter 0 \
  -feather-size 0 -data-column CORRECTED_DATA -no-update-model-required /w/sub4.ms
cp "$s/resid-image-pb.fits" "$d/resid-image-pb.fits"
