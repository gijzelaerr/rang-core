#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
# DD4 arm O set-up: a fresh copy of the subset MS on ext4 with CORRECTED_DATA
# and MODEL_D0..MODEL_D{N-1}. Usage: step4_o0.sh SUBMS SCRATCH NDIR
source "$(dirname "$0")/common4.sh"
sub=$1; s=$2; n=$3
if [ -e "$s" ]; then echo "$s exists" >&2; exit 1; fi
mkdir -p "$s"; cp -r "$sub" "$s/sub.ms"
py - "$s/sub.ms" "$n" <<'PY'
import sys, casacore.tables as pt
t = pt.table(sys.argv[1], readonly=False, ack=False)
names = ["CORRECTED_DATA"] + [f"MODEL_D{d}" for d in range(int(sys.argv[2]))]
for name in names:
    desc = t.getcoldesc("DATA"); desc["name"] = name
    dm = t.getdminfo("DATA"); dm["NAME"] = "Tiled" + name; dm["COLUMNS"] = [name]
    t.addcols(pt.maketabdesc([pt.makecoldesc(name, desc)]), dm)
t.close()
PY
docker run --rm --entrypoint "" "$image" cat /wsclean-commit.txt > "$s/wsclean-commit.txt"
