#!/bin/bash
# Gate 3c compact-scatter diagnostic without channel averaging (research/gate3c-rerun.md
# section 7, post hoc). Self-driving on nash; each step leaves $R/done/<step>, so a second
# start resumes. One heavy-lock booking per step, every step nice 19 / ionice idle.
#   nohup bash gca.sh >> $R/gca.out 2>&1 &
set -u
W=$(cd "$(dirname "$0")/../../.." && pwd)          # this branch's worktree on nash
H=$W/research/results/gate3c-rerun                  # g3r.py, unchanged
F=$W/research/results/e2n-followup/scripts
LOCK=$HOME/Github/rang/tools/heavy_lock.py
SRC=$HOME/rang-data/outputs/e2n-20261116           # read only
R=${R:-$HOME/rang-data/outputs/gate3c-compact-avg-20261124}
MS=$R/e2n.ms
PY=$HOME/Github/rang/.venv/bin/python               # scripts and scorer (as 6.2)
S=$HOME/Github/rang/research/results/e2-acceptance-scripts
B=$HOME/Build/tmp/20261124-gate3c-compact-avg
WPY=$B/wheel-venv/bin/python                         # E2-N's rang (gemclean, run)
SRCW=$HOME/Worktrees/rang/e2n                        # E2-N's source path (embedded)
EXT_SHA=9c42ea724253fd47da3e8ca3fd194ac862e2cd4e5702ec0c86f6d3370de683ed
CONFIG_SHA_PREFIX=3b3f3047
ST=$W/outputs/status/gate3c-compact-avg.md
GS=${GS:-12}            # GeMClean slots and RAYON_NUM_THREADS, every arm
mkdir -p "$R/done" "$B"
LOG=$R/steps.log
note() { echo "$(date -Is) $*" | tee -a "$R/gca.log"; }
did() { [ -e "$R/done/$1" ]; }
mark() { touch "$R/done/$1"; note "done $1"; }
source "$HOME/.rang-env.sh" >/dev/null 2>&1
step() {  # name slots mem command...  (timed, peak RSS by /usr/bin/time -v)
  local name=$1 slots=$2 mem=$3; shift 3
  echo "$(date -Is) START $name slots=$slots mem=$mem" >> "$LOG"
  local t0=$(date +%s)
  RAYON_NUM_THREADS=$slots OMP_NUM_THREADS=$slots python3 "$LOCK" run --slots "$slots" --mem "$mem" -- \
    nice -n 19 ionice -c3 /usr/bin/time -v -o "$R/$name.time" "$@" > "$R/$name.step.out" 2>&1 < /dev/null
  local rc=$?
  echo "$(date -Is) END $name rc=$rc $(( $(date +%s) - t0 ))s" >> "$LOG"
  return $rc
}
G="$PY $H/g3r.py"

# 1. copy and its 9.1 check
did copy || { step copy 1 4 cp -a "$SRC/e2n.ms" "$SRC/e2n.ms.flagversions" "$R/" && mark copy; } || { note "copy failed"; exit 2; }
did hash-copy || { step hash-copy 1 4 "$PY" "$F/fu_hash.py" "$MS" "$W/research/results/e2n/flaghash-input.json" "$R/copy-hash.json" && mark hash-copy; } \
  || { note "copy hash differs from 9.1"; exit 2; }
# 2. E2-N's wheel, rebuilt at 99a5261 from E2-N's path
if ! did wheel; then
  [ -d "$SRCW" ] || git -C "$HOME/Github/rang" worktree add --detach "$SRCW" 99a5261 || { note "e2n worktree failed"; exit 2; }
  rm -rf "$B/wheel"
  step wheel-build 8 12 bash -c "cd '$SRCW' && '$PY' tools/wheel/build.py '$B/wheel'" || { note "wheel build failed"; exit 2; }
  step wheel-venv 2 4 bash -c "uv venv -q -p 3.14 '$B/wheel-venv' && uv pip install -q -p '$WPY' \$(ls '$B'/wheel/dist/rang_core-0.2.0-*.whl)'[imaging]' psutil" \
    || { note "wheel venv failed"; exit 2; }
  got=$("$WPY" -c "import rang._core as c, hashlib; print(hashlib.sha256(open(c.__file__,'rb').read()).hexdigest())")
  echo "{\"extension\": \"$got\", \"e2n_receipt\": \"$EXT_SHA\", \"equal\": $([ "$got" = "$EXT_SHA" ] && echo true || echo false)}" > "$R/wheel-check.json"
  [ "$got" = "$EXT_SHA" ] || { note "rebuilt extension differs from E2-N's ($got)"; exit 2; }
  mark wheel
fi
# 3. rang-core run, the follow-up's configuration unchanged (flag, calibrate, apply, image)
if ! did run; then
  ( cd "$F" && step run 16 96 "$WPY" -m rang.core_cli run "$F/e2n-rerun.yaml" "$MS" --run-dir "$R/c3/rang-run" ) \
    || { note "run failed"; exit 2; }
  mark run
fi
# 4. checks R1, R2, flag versions
did r1 || { step r1 1 4 $G flaghash "$MS" "$MS.flagversions/flags.rang_selfcal_20261117T072854Z" "$R/r1-flaghash.json" && mark r1; } \
  || { note "R1 not met"; exit 2; }
did flagversions || { step flagversions 1 4 "$PY" "$F/fu_flagversions.py" "$MS" "$SRC/e2n.ms" "$R/flagversions.json" && mark flagversions; } \
  || { note "flag versions differ"; exit 2; }
if ! did r2; then
  "$PY" - "$R/c3/rang-run" "$CONFIG_SHA_PREFIX" "$R/r2.json" <<'EOF' || { note "R2 not met"; exit 2; }
import json, sys
from pathlib import Path
rd, want, out = Path(sys.argv[1]), sys.argv[2], sys.argv[3]
st = json.loads((rd / "state.json").read_text())
hits = []
def walk(o, path=""):
    if isinstance(o, dict):
        for k, v in o.items():
            if k == "config_sha256":
                hits.append((path, v))
            walk(v, f"{path}/{k}")
    elif isinstance(o, list):
        for i, v in enumerate(o):
            walk(v, f"{path}[{i}]")
walk(st)
apply = [v for p, v in hits if "apply" in p]
ok = bool(apply) and all(v.startswith(want) for v in apply)
json.dump({"config_sha256": hits, "want_prefix": want, "met": ok}, open(out, "w"), indent=1)
print("R2", ok, apply)
sys.exit(0 if ok else 1)
EOF
  mark r2
fi
# 5. matched state, dirty pair (control and timed piece)
did unit || { step unit 1 4 $G unit "$MS" "$R" && mark unit; } || { note "unit failed"; exit 2; }
if ! did dirty; then
  step ws-n-dirty 4 24 $G wsclean "$MS" "$R" n dirty 4 & a=$!
  step n-dirty "$GS" 48 $G gemclean "$MS" "$R" n-dirty "$WPY" & b=$!
  wait $a || { note "ws-n-dirty failed"; exit 2; }
  wait $b || { note "n-dirty failed"; exit 2; }
  step d-dirty "$GS" 48 $G gemclean "$MS" "$R" d-dirty "$WPY" || { note "d-dirty failed"; exit 2; }
  $G logcheck "$R" ws-n-dirty
  step score-n-dirty 1 24 "$PY" "$S/e2_score3c_a.py" "$R/n-dirty" "$R/ws-n" "$R/g3c-n-dirty.json" --dirty-only || exit 2
  step score-d-dirty 1 24 "$PY" "$S/e2_score3c_a.py" "$R/d-dirty" "$R/ws-n" "$R/g3c-d-dirty.json" --dirty-only || exit 2
  mark dirty
fi
[ "${STOP_AFTER_DIRTY:-0}" = 1 ] && { note "stopped after the dirty pair (projection)"; exit 0; }
# 6. the three clean jobs, concurrently: WSClean, A (n-clean), U (d-clean)
if ! did clean; then
  did ws-n-clean || { step ws-n-clean 8 48 $G wsclean "$MS" "$R" n clean 8 && mark ws-n-clean; } & a=$!
  did n-clean || { step n-clean "$GS" 80 $G gemclean "$MS" "$R" n-clean "$WPY" && mark n-clean; } & b=$!
  did d-clean || { step d-clean "$GS" 104 $G gemclean "$MS" "$R" d-clean "$WPY" && mark d-clean; } & c=$!
  wait $a; ra=$?; wait $b; rb=$?; wait $c; rc=$?
  [ $ra = 0 ] && [ $rb = 0 ] && [ $rc = 0 ] || { note "clean jobs rc $ra $rb $rc"; exit 2; }
  $G logcheck "$R" ws-n-clean
  mark clean
fi
did score-n || { step score-n 1 24 "$PY" "$S/e2_score3c_a.py" "$R/n-clean" "$R/ws-n" "$R/g3c-n.json" && mark score-n; } || exit 2
did score-d || { step score-d 1 24 "$PY" "$S/e2_score3c_a.py" "$R/d-clean" "$R/ws-n" "$R/g3c-d.json" && mark score-d; } || exit 2
note "finished"
