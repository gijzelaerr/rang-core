#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# G6 case A (research/g6-predict.md): A1's small MS, field 3, the probe's flags,
# MODEL_DATA and MODEL_WSCLEAN pre-filled with 7+7j; the probe's WSClean model.
#   bash case_a.sh OUTDIR GEMCLEAN
set -eu
O=$1; GEM=$2
source "$(dirname "$(readlink -f "$0")")/lib.sh"
PROBE=$D/g6-20261106-00-probe
A1=$D/fp-a1-20261106-simtruth/small/a1-small.ms
mkdir -p "$O"; snapshot
rm -rf "$O/a.ms"; cp -r "$A1" "$O/a.ms"
casa_py /g6/prep.py "$O/a.ms" --flags 3 --sentinel MODEL_DATA MODEL_WSCLEAN
casa_py /g6/compare.py "$O/a.ms" --hashes "$O/a-before.json"
THREADS=4
gem a -predict -name "$PROBE/w" -field 3 -j 4 "$O/a.ms" > "$O/a-gemclean.log" 2>&1
wsc a -predict -gridder wgridder -no-min-grid-resolution -wgridder-accuracy 1e-6 -pol I \
  -size 512 512 -scale 2asec -field 3 -j 4 -model-column MODEL_WSCLEAN -name "$PROBE/w" \
  "$O/a.ms" > "$O/a-wsclean.log" 2>&1
casa_py /g6/compare.py "$O/a.ms" --field 3 --sentinel 7+7j --before "$O/a-before.json" \
  --out "$O/a-compare.json" > /dev/null
rang_py "$HERE/dft.py" "$O/a.ms" "$PROBE/w-model.fits" --field 3 --out "$O/a-dft.json" > /dev/null
rang_py "$HERE/rang_hash.py" "$O/a.ms" MODEL_DATA > "$O/a-rang-hash.json"
python3 - "$O" <<'EOF'
import json, sys
o = sys.argv[1]
c = json.load(open(f"{o}/a-compare.json")); d = json.load(open(f"{o}/a-dft.json"))
r = json.load(open(f"{o}/a-rang-hash.json"))
print({k: c[k] for k in ("criterion_1", "criterion_2", "rel_l2", "max_abs_over_max_w", "rows_g", "rows_w", "selected_rows", "other_columns_changed")})
print("dft", d["criterion_3"], d["conjugate_used"], {k: v for k, v in d.items() if k.startswith("MODEL")})
print("readback", r["sha256_rang"] == c["sha256_g"])
EOF
