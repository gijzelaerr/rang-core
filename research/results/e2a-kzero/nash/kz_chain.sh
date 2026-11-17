#!/bin/bash
# SPDX-License-Identifier: MIT
# research/e2a-kzero.md on nash: one rang arm (zs or zsd) end to end. The copy's
# hash, `rang-core run` of the arm's configuration (one invocation, one receipt),
# then E2-A's in-place post steps (gates 1, 2a-c and the self-calibration gains)
# and rows (self-calibration rms, target noise and dynamic range, flux) as
# research/results/e2-acceptance-scripts runs them, through kz_nash.py.
# Not run: gate 3a (Tricolour), gate 3c and the oracle's WSClean (the note).
# Every step is one shared heavy-lock job of at most 4 slots (two arms: 8, the
# night budget), each inside e2_diskguard.py, under nice -n 19 ionice -c3,
# with every thread pool capped at the slots booked.
#   bash kz_chain.sh ARM [FIRST [LAST]]
# Log: O/ARM/R/chain-steps.log (START/END lines; "ARM DONE" at the end).
set -u
ARM=$1
W=$(cd "$(dirname "$0")/../../../.." && pwd)
K=$W/research/results/e2a-kzero
S=$W/research/results/e2-acceptance-scripts
O=$HOME/rang-data/outputs/e2a-kzero-20261117
MS=$O/$ARM/e2a.ms
R=$O/$ARM/R
CONFIG=$K/e2a-kzero-$ARM.yaml
INPUT=$W/research/results/e2-acceptance/e2a-rerun/flaghash-input.json
PY=$W/.venv/bin/python
LOCK=$HOME/Github/rang/tools/heavy_lock.py
FLOOR=${FLOOR:-1000}
mkdir -p "$R"
LOG=$R/chain-steps.log
# step slots GB kind
STEPS="
hash-copy 1 4 HASH
columns-before 1 2 POST
config-check 1 4 CHECK
run 4 48 RUN
keys 1 2 KEYS
stage-hash 1 4 STAGEHASH
gate1 1 2 POST
archive 1 2 POST
wcs 1 4 POST
casacore 1 4 POST
casa-ro 1 4 POST
wsclean0 4 16 POST
daskms 4 32 POST
prep-inplace 1 8 POST
applycal-inplace 4 16 POST
compare-inplace 1 8 POST
snapshot-inplace 1 12 POST
drop-corrected-inplace 1 2 POST
qc-avg 4 32 POST
qc-selfcal 4 64 POST
restore 1 4 RESTORE
selfcal-score 1 16 ROWS
oracle-copy 1 2 ORACLE
target-score 1 16 ROWS
flux-prep 1 4 FLUXPREP
flux-run 4 48 ROWS
flux-score 4 12 ROWS
final-restore 1 4 FINAL
"
first=${2:-hash-copy}
last=${3:-final-restore}
on=0
while read -r step slots mem kind; do
  [ -n "$step" ] || continue
  [ "$step" = "$first" ] && on=1
  [ $on = 1 ] || continue
  case $kind in
    HASH) cmd=("$PY" -c "import json, sys; sys.path.insert(0, '$S'); import e2_post as P
h = P.flag_hash('$MS'); w = json.load(open('$INPUT'))
ok = all(h[k] == w[k] for k in ('rows', 'flag_sha256', 'flag_row_sha256'))
json.dump({**h, 'input': w, 'met': ok}, open('$R/hash-copy.json', 'w'), indent=1)
print(h, ok); sys.exit(0 if ok else 3)") ;;
    CHECK) cmd=("$PY" -c "import json, sys; from rang import core_pipeline as cp
cfg, stages, warn = cp.check_config('$CONFIG', '$MS')
want = {'zs': (True, False), 'zsd': (True, True)}['$ARM']
got = (cfg['calibrate']['k_zero_start'], cfg['calibrate']['bandpass_model_divided'])
rec = {'stages': stages, 'warnings': warn, 'keys': got, 'want': want, 'met': got == want}
json.dump(rec, open('$R/config-check.json', 'w'), indent=1); print(rec); sys.exit(0 if got == want else 3)") ;;
    RUN) cmd=("$PY" "$S/e2_timed.py" "$R/run-timed.json" -- "$PY" -m rang.core_cli run "$CONFIG" "$MS") ;;
    KEYS) cmd=("$PY" "$K/kz_score.py" configs) ;;
    STAGEHASH) cmd=("$PY" -c "import json, sys; sys.path.insert(0, '$S'); import e2_post as P
v = P.state('$MS')['stages']['calibrate']['flag_version']
h = P.flag_hash('$MS.flagversions/flags.' + v)
json.dump({'version': v, **h}, open('$R/flag-stage-hash.json', 'w'), indent=1); print(v, h)") ;;
    POST) cmd=("$PY" "$K/kz_nash.py" e2_post "$step" "$MS" "$R") ;;
    RESTORE) cmd=("$PY" "$K/kz_nash.py" e2_post restore "$MS" "$R" "$INPUT") ;;
    ROWS) cmd=("$PY" "$K/kz_nash.py" e2_rows_a "$step" "$MS" "$R") ;;
    FLUXPREP) cmd=("$PY" "$K/kz_nash.py" e2_rows_a flux-prep "$MS" "$R" "$CONFIG") ;;
    FINAL) cmd=("$PY" "$K/kz_nash.py" e2_rows_a final-restore "$MS" "$R" "$INPUT") ;;
    ORACLE) cmd=(bash -c "rm -rf '$R/oracle-a' && cp -a '$O/archived/oracle-a' '$R/oracle-a'") ;;
  esac
  t0=$(date +%s)
  echo "$(date -Is) START $step slots=$slots mem=$mem" >> "$LOG"
  RAYON_NUM_THREADS=$slots OMP_NUM_THREADS=$slots OPENBLAS_NUM_THREADS=$slots \
  MKL_NUM_THREADS=$slots NUMBA_NUM_THREADS=$slots KZ_THREADS=$slots \
    python3 "$LOCK" run --slots "$slots" --mem "$mem" -- \
    nice -n 19 ionice -c3 "$PY" "$S/e2_diskguard.py" --path "$HOME" --min-free-gib "$FLOOR" \
    --log "$R/chain-guard.jsonl" -- "${cmd[@]}" < /dev/null >> "$R/chain.out" 2>&1
  rc=$?
  dt=$(( $(date +%s) - t0 ))
  echo "$(date -Is) END $step rc=$rc ${dt}s" >> "$LOG"
  printf '%s\t%s\t%s\t%s\t%s\t%s\n' "$(date -Is)" "$ARM" "$step" "$rc" "$dt" "$slots" >> "$O/timings.tsv"
  [ "$rc" = 0 ] || { echo "$(date -Is) $ARM FAILED at $step rc=$rc" >> "$LOG"; exit "$rc"; }
  [ "$step" = "$last" ] && break
done <<< "$STEPS"
echo "$(date -Is) $ARM DONE" >> "$LOG"
