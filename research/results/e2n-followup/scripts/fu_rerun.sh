#!/bin/bash
# E2-N follow-up, rerun from the start (research/e2n-followup.md, amendment of 2026-11-22):
# E2-N's run root (R/: rang-run, rows-rang.npy, CASA's tables) and the follow-up's
# (e2n-followup-20261118) were both removed, so rang's side is regenerated first, with
# E2-N's own binary (rang-core 0.2.0 from PyPI, extension SHA-256 checked against E2-N's
# receipt) and E2-N's chain steps unchanged, then the follow-up chain from casa-prep-a.
# Self-driving: each step leaves R/done/<step>; a rerun of this script resumes.
#   nohup bash fu_rerun.sh >> RUN/fu-rerun.out 2>&1 &
set -u
W=$(cd "$(dirname "$0")/../../../.." && pwd)
F=$W/research/results/e2n-followup/scripts
N=$W/research/results/e2n-scripts
LOCK=$HOME/Github/rang/tools/heavy_lock.py
SRC=$HOME/rang-data/outputs/e2n-20261116
RUN=${RUN:-$HOME/rang-data/outputs/e2n-followup-20261122}
R=$RUN/R
MS=$RUN/e2n.ms
INPUT=$W/research/results/e2n/flaghash-input.json
WPY=$RUN/wheel-venv/bin/python        # rang-core 0.2.0: E2-N's rang arm
PY=$W/.venv/bin/python                # the worktree's rang: scripts and oracles
CONFIG=$F/e2n-rerun.yaml
EXT_SHA=9c42ea724253fd47da3e8ca3fd194ac862e2cd4e5702ec0c86f6d3370de683ed
ST=$W/outputs/status/e2n-followup.md
export MS R INPUT CONFIG
mkdir -p "$R/done"
note() { echo "$(date -Is) $*" | tee -a "$R/rerun.log"; sed -i "s|^- last:.*|- last: $(date +%H:%M) $*|" "$ST" 2>/dev/null; }
did() { [ -e "$R/done/$1" ]; }
mark() { touch "$R/done/$1"; note "done $1"; }
lock() { local s=$1 m=$2; shift 2; python3 "$LOCK" run --slots "$s" --mem "$m" -- nice -n 19 ionice -c3 "$@"; }
source "$HOME/.rang-env.sh" >/dev/null 2>&1

cmp -s "$N/mk_rfi_flagging_calibrator_fields_firstpass.yaml" "$F/mk_rfi_flagging_calibrator_fields_firstpass.yaml" \
  || { note "strategy copy differs from e2n-scripts'"; exit 2; }
did copy || { lock 1 4 cp -a "$SRC/e2n.ms" "$MS" && mark copy; } || { note "copy failed"; exit 2; }
did hash-copy || { lock 1 4 "$PY" "$F/fu_hash.py" "$MS" "$INPUT" "$R/fu-copy-hash.json" && mark hash-copy; } \
  || { note "copy hash differs from 9.1"; exit 2; }
did hash-original-before || { lock 1 4 "$PY" "$F/fu_hash.py" "$SRC/e2n.ms" "$INPUT" "$R/fu-original-hash-before.json" && mark hash-original-before; } \
  || { note "original hash differs from 9.1"; exit 2; }
if ! did wheel; then
  lock 2 4 bash -c "uv venv -q -p 3.14 '$RUN/wheel-venv' && uv pip install -q -p '$RUN/wheel-venv/bin/python' rang-core==0.2.0" \
    || { note "wheel venv failed"; exit 2; }
  got=$("$WPY" -c "import rang._core as c, hashlib; print(hashlib.sha256(open(c.__file__,'rb').read()).hexdigest())")
  echo "{\"extension\": \"$got\", \"e2n_receipt\": \"$EXT_SHA\", \"equal\": $([ "$got" = "$EXT_SHA" ] && echo true || echo false)}" > "$R/wheel-check.json"
  [ "$got" = "$EXT_SHA" ] || { note "rang-core 0.2.0 extension differs from E2-N's ($got)"; exit 2; }
  mark wheel
fi
# rang's side: E2-N's chain (e2n_nash_chain.sh) steps, unchanged, on this run root.
for seg in "columns-before run" "gate1 archive" "prep-inplace prep-inplace" "rows-snap-rang rows-snap-rang" "restore restore"; do
  set -- $seg
  did "rang-$1" && continue
  MS=$MS R=$R CONFIG=$CONFIG INPUT=$INPUT WPY=$WPY PY=$PY bash "$N/e2n_nash_chain.sh" "$1" "$2" \
    || { note "rang side stopped at $1-$2"; exit 3; }
  mark "rang-$1"
done
did flagversions || { lock 1 8 "$PY" "$F/fu_flagversions.py" "$MS" "$SRC/e2n.ms" "$R/fu-flagversions.json" && mark flagversions; } \
  || note "flag versions differ from E2-N's (recorded in fu-flagversions.json; the chain goes on, prep-b checks 3b's hash)"
KVERSION=$("$PY" -c "import json,sys; print(json.load(open(sys.argv[1]))['stages']['apply']['flag_version'])" "$R/rang-run/state.json")
export KVERSION WPY=$PY
did fu-to-leakage || { bash "$F/fu_chain.sh" casa-prep-a leakage-casa && mark fu-to-leakage; } || { note "chain stopped"; exit 3; }
did hash-original-mid || { lock 1 4 "$PY" "$F/fu_hash.py" "$SRC/e2n.ms" "$INPUT" "$R/fu-original-hash-mid.json"; mark hash-original-mid; }
if ! did fu-target; then
  # E3-A's 22:00-06:00 SAST window (1.2): target-wsclean (8 slots, about 3 h) starts only
  # if it can end before 22:00, otherwise at 06:00. HOLD=0 on the coordinator's word.
  now=$(TZ=Africa/Johannesburg date +%H%M)
  if [ "${HOLD:-1}" = 1 ] && { [ "$now" -ge 1900 ] || [ "$now" -lt 0600 ]; }; then
    target=$(TZ=Africa/Johannesburg date -d "$( [ "$now" -lt 0600 ] && echo today || echo tomorrow ) 06:00" +%s)
    note "holding target-wsclean until $(date -d @"$target" -Is) (E3-A window)"
    while [ "$(date +%s)" -lt "$target" ]; do sleep 300; done
  fi
  bash "$F/fu_chain.sh" target-wsclean final-restore || { note "chain stopped (target)"; exit 3; }
  mark fu-target
fi
did hash-original-after || { lock 1 4 "$PY" "$F/fu_hash.py" "$SRC/e2n.ms" "$INPUT" "$R/fu-original-hash-after.json"; mark hash-original-after; }
note "finished"
