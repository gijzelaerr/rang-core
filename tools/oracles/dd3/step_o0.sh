#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
# DD3 arm O set-up: a fresh MS copy on ext4 with a CORRECTED_DATA column.
# Usage: step_o0.sh SIMDIR SCRATCH
source "$(dirname "$0")/common.sh"
sim=$1; s=$2
if [ -e "$s" ]; then echo "$s exists" >&2; exit 1; fi
mkdir -p "$s"; cp -r "$sim/dd1.ms" "$s/dd1.ms"
py - "$s/dd1.ms" <<'PY'
import sys, casacore.tables as pt
t = pt.table(sys.argv[1], readonly=False, ack=False)
desc = t.getcoldesc("DATA"); desc["name"] = "CORRECTED_DATA"
dm = t.getdminfo("DATA"); dm["NAME"] = "TiledCORRECTED"; dm["COLUMNS"] = ["CORRECTED_DATA"]
t.addcols(pt.maketabdesc([pt.makecoldesc("CORRECTED_DATA", desc)]), dm)
t.close()
PY
docker run --rm --entrypoint "" "$image" cat /wsclean-commit.txt > "$s/wsclean-commit.txt"
