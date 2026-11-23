#!/bin/bash
# Gate 3c rerun chain (research/gate3c-rerun.md section 3), after the forced
# apply. One heavy-lock booking per step; on nash every step under
# nice -n 19 ionice -c3. Environment:
#   LEG    e2n | e2a
#   MS     the leg's MS copy in the run root; R the run root
#   PY     a Python with rang for reading and scoring (the host's main venv)
#   LEGPY  the leg's own wheel venv (gemclean)
#   LOCK   the main checkout's tools/heavy_lock.py
#   SELFCAL_VERSION  the saved flag version "flags before selfcal" (R1)
#   ARCHIVED_NOSI    (e2a) the archived -no-small-inversion WSClean dirty directory (R3)
#   CLEAN  1: run arm N's cleaned images (the compact row)
#   DARM   1: arm D may run (if arm N is not "setup")
#   LOCKPY the Python that runs the lock (default python3)
#   FIRST  the first step to run (default r1)
set -u
H=$(cd "$(dirname "$0")" && (pwd -W 2>/dev/null || pwd))
S=$H/../e2-acceptance-scripts
G="$PY $H/g3r.py"
LOG=$R/chain-steps.log
NICE=()
case $(uname -s) in Linux) NICE=(nice -n 19 ionice -c3) ;; esac
step() {  # name slots mem command...
  local name=$1 slots=$2 mem=$3; shift 3
  echo "$(date -Iseconds) START $name slots=$slots mem=$mem" >> "$LOG"
  local t0=$(date +%s)
  ${LOCKPY:-python3} "$LOCK" run --slots "$slots" --mem "$mem" -- "${NICE[@]}" "$@" > "$R/$name.step.out" 2>&1
  local rc=$?
  echo "$(date -Iseconds) END $name rc=$rc $(( $(date +%s) - t0 ))s" >> "$LOG"
  return $rc
}
on=0
go() { [ "$1" = "${FIRST:-r1}" ] && on=1; [ $on = 1 ]; }

if go r1; then step r1 1 4 $G flaghash "$MS" "$MS.flagversions/$SELFCAL_VERSION" "$R/r1-flaghash.json" || exit 1; fi
if go unit; then step unit 1 4 $G unit "$MS" "$R" || exit 1; fi
if go c3; then
  step ws-c3-dirty 4 16 $G wsclean "$MS" "$R" c3 dirty 4 || exit 1
  $G logcheck "$R" ws-c3-dirty
  step score-c3 1 16 $PY "$S/e2_score3c_a.py" "$R/c3" "$R/ws-c3" "$R/g3c-c3.json" --dirty-only || exit 1
  if [ "$LEG" = e2a ]; then $G diff "$R/ws-c3" "$ARCHIVED_NOSI" ESO137m001 "$R/r3-diff.json"; fi
fi
if go grid; then
  $PY - "$R/ws-c3-dirty-logcheck.json" <<'EOF' || exit 1
import json, sys
d = json.load(open(sys.argv[1]))
ok = not d["minimal_inversion_lines"] and d["nyquist_lower_bound_arcsec"] >= 2.0
print("grid", d["nyquist_lower_bound_arcsec"], "ok" if ok else "STOP")
sys.exit(0 if ok else 1)
EOF
fi
if go n-dirty; then
  step ws-n-dirty 4 24 $G wsclean "$MS" "$R" n dirty 4 & a=$!
  step n-dirty 8 32 $G gemclean "$MS" "$R" n-dirty "$LEGPY" & b=$!
  wait $a || exit 1
  wait $b || exit 1
  $G logcheck "$R" ws-n-dirty
  step score-n-dirty 1 24 $PY "$S/e2_score3c_a.py" "$R/n-dirty" "$R/ws-n" "$R/g3c-n-dirty.json" --dirty-only || exit 1
fi
if go d-dirty && [ "${DARM:-0}" = 1 ]; then
  if $PY -c "import json,sys; sys.exit(0 if json.load(open('$R/g3c-n-dirty.json'))['dirty']['max_over_peak'] > 1e-4 else 1)"; then
    step d-dirty 8 48 $G gemclean "$MS" "$R" d-dirty "$LEGPY" || exit 1
    step score-d-dirty 1 24 $PY "$S/e2_score3c_a.py" "$R/d-dirty" "$R/ws-n" "$R/g3c-d-dirty.json" --dirty-only || exit 1
  else
    echo "$(date -Iseconds) SKIP d-dirty (class setup)" >> "$LOG"
  fi
fi
if go n-clean && [ "${CLEAN:-0}" = 1 ]; then
  step ws-n-clean 8 48 $G wsclean "$MS" "$R" n clean 8 & a=$!
  step n-clean 8 80 $G gemclean "$MS" "$R" n-clean "$LEGPY" & b=$!
  wait $a || exit 1
  wait $b || exit 1
  $G logcheck "$R" ws-n-clean
  step score-n 1 24 $PY "$S/e2_score3c_a.py" "$R/n-clean" "$R/ws-n" "$R/g3c-n.json" || exit 1
fi
echo "$(date -Iseconds) chain finished" >> "$LOG"
