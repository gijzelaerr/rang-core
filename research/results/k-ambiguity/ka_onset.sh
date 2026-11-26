#!/bin/bash
# SPDX-License-Identifier: MIT
# research/k-ambiguity.md section 6: ka_raw.py on every scan of block 1678312253 (each copied
# into the run root, read, deleted), to find when antenna 25's pi step starts.
set -euo pipefail
R=$HOME/rang-data/outputs/k-ambiguity-20261126
PY=$HOME/Worktrees/rang/k-ambiguity/.venv/bin/python
mkdir -p "$R/onset" "$R/tmp"
for ms in $("$PY" -c "import json; [print(s['ms']) for s in json.load(open('$R/scans.json'))['scans']]"); do
  n=$(basename "$ms" .ms)
  [ -s "$R/onset/$n.json" ] && continue
  if [ -d "$R/ms/$n.ms" ]; then src=$R/ms/$n.ms; else cp -r "$ms" "$R/tmp/"; src=$R/tmp/$n.ms; fi
  "$PY" "$R/ka_raw.py" "$src" 25 "$R/onset/$n.json" > "$R/onset/$n.out"
  chmod -R u+w "$R/tmp" && rm -rf "$R/tmp/$n.ms"
done
