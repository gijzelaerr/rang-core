#!/bin/bash
# SPDX-License-Identifier: MIT
# research/k-ambiguity.md section 4 on nash: scan 60 of block 1678312253 (own copy), flag with
# stage 3's strategy, then K alone with stage 3's calibrate section, key off and on, every K
# solve's arrays captured (ka_capture.py); then the probe on antenna 25. Heavy lock, nice 19,
# ionice -c3; timings in logs/timings.tsv.
set -euo pipefail
R=$HOME/rang-data/outputs/k-ambiguity-20261126
W=$HOME/Worktrees/rang/k-ambiguity
PY=$W/.venv/bin/python
RC=$W/.venv/bin/rang-core
LOCK="python3 $HOME/Github/rang/tools/heavy_lock.py run"
MS=${MS:-$R/ms/scan060.ms}
TAG=${TAG:-s60}
cd "$R"
step() { # name slots mem -- command...
  local name=$1 slots=$2 mem=$3; shift 4
  if [ -e "$R/done/$TAG-$name" ]; then return 0; fi
  mkdir -p "$R/done"
  /usr/bin/time -f "%e s %M KB" -o "$R/logs/$TAG-$name.time" \
    $LOCK --slots "$slots" --mem "$mem" -- nice -n 19 ionice -c3 "$@" >>"$R/logs/$TAG.log" 2>&1
  printf "%s\t%s\t%s\t%s\n" "$TAG" "$name" "$(cat "$R/logs/$TAG-$name.time")" "$(date -u +%FT%TZ)" >>"$R/logs/timings.tsv"
  touch "$R/done/$TAG-$name"
}
"$PY" - <<PYEOF
import yaml
for arm, key in (("off", False), ("on", True)):
    c = yaml.safe_load(open("$R/on.yaml"))
    c["fields"].pop("gcal", None)
    c["calibrate"]["primary"]["terms"] = c["calibrate"]["primary"]["terms"][:1]
    c["calibrate"].pop("secondary", None)
    c["calibrate"]["k_zero_start"] = key
    yaml.safe_dump(c, open("$R/k-%s.yaml" % arm, "w"), sort_keys=False)
PYEOF
export RAYON_NUM_THREADS=4
step flag 4 24 -- "$RC" flag "$R/k-off.yaml" "$MS" --run-dir "$R/$TAG-run-flag"
export RAYON_NUM_THREADS=2
mkdir -p "$R/cap"
step cal-off 2 16 -- "$PY" "$R/ka_capture.py" "$R/cap/$TAG-off" -- calibrate "$R/k-off.yaml" "$MS" --run-dir "$R/$TAG-run-off"
step restore 1 8 -- "$PY" -c "
import json
from rang import core_writeback
v = json.load(open('$R/$TAG-run-off/state.json'))['stages']['calibrate'].get('flag_version')
print('restore', v)
if v: core_writeback.restore_flags('$MS', v)
"
step cal-on 2 16 -- "$PY" "$R/ka_capture.py" "$R/cap/$TAG-on" -- calibrate "$R/k-on.yaml" "$MS" --run-dir "$R/$TAG-run-on"
step probe-off 1 8 -- "$PY" "$R/ka_probe.py" "$R/cap/$TAG-off-0.npz" 25 "$R/$TAG-probe-off.json"
step probe-on 1 8 -- "$PY" "$R/ka_probe.py" "$R/cap/$TAG-on-0.npz" 25 "$R/$TAG-probe-on.json"
echo "== end $(date -u +%FT%TZ)" >>"$R/logs/$TAG.log"
