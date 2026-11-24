#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
# DD4 arm O set-up: a fresh copy of the subset MS on ext4 with
# MODEL_D0..MODEL_D{N-1} for QuartiCal, and its four-correlation copy sub4.ms
# (A4), matched (A5: both hands min(w_XX, w_YY), flag XX|YY), with
# CORRECTED_DATA for WSClean's facet steps.
# Usage: step4_o0.sh SUBMS SCRATCH NDIR
source "$(dirname "$0")/common4.sh"
sub=$1; s=$2; n=$3
if [ -e "$s" ]; then echo "$s exists" >&2; exit 1; fi
mkdir -p "$s"; cp -r "$sub" "$s/sub.ms"; cp -r "$sub" "$s/sub4.ms"
py "$(dirname "$0")/to_four_corr.py" "$s/sub4.ms" --matched  # DD4 amendment A5
py - "$s/sub4.ms" CORRECTED_DATA <<'PY'
import sys, casacore.tables as pt
t = pt.table(sys.argv[1], readonly=False, ack=False)
desc = t.getcoldesc("DATA"); desc["name"] = sys.argv[2]
dm = t.getdminfo("DATA"); dm["NAME"] = "Tiled" + sys.argv[2]; dm["COLUMNS"] = [sys.argv[2]]
dm["SPEC"].pop("HYPERCUBES", None)
t.addcols(pt.maketabdesc([pt.makecoldesc(sys.argv[2], desc)]), dm)
t.close()
PY
py - "$s/sub.ms" "$n" <<'PY'
import sys, casacore.tables as pt
t = pt.table(sys.argv[1], readonly=False, ack=False)
names = [f"MODEL_D{d}" for d in range(int(sys.argv[2]))]
for name in names:
    desc = t.getcoldesc("DATA"); desc["name"] = name
    dm = t.getdminfo("DATA"); dm["NAME"] = "Tiled" + name; dm["COLUMNS"] = [name]
    t.addcols(pt.maketabdesc([pt.makecoldesc(name, desc)]), dm)
t.close()
PY
docker run --rm --entrypoint "" "$image" cat /wsclean-commit.txt > "$s/wsclean-commit.txt"
