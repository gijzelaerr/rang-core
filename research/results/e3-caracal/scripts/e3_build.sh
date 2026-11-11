#!/bin/sh
# Build and verify one E3 MS with E2's converter (fp-e2-acceptance, blob
# e33bbe4b of e2_convert.py = commit 14cc310), under the shared heavy lock.
#   sh e3_build.sh OUT.ms JSON [converter args: STORE:GROUP ... --rows N]
set -u
OUT=$1; JSON=$2; shift 2
E2=/c/Users/gijsm/Worktrees/rang/fp-e2-acceptance
PY=$E2/.venv/Scripts/python.exe
CONV=$E2/research/results/e2-acceptance-scripts/e2_convert.py
LOCK=/c/Users/gijsm/Github/rang/tools/heavy_lock.py
echo "START $(date -Is) build $OUT"
t0=$(date +%s)
"$PY" "$LOCK" run --slots 2 --mem 8 -- "$PY" "$CONV" build "$OUT" "$@"; rc=$?
t1=$(date +%s); echo "BUILD rc=$rc wall=$((t1-t0)) s"
[ $rc -eq 0 ] || exit $rc
"$PY" "$LOCK" run --slots 2 --mem 8 -- "$PY" "$CONV" verify "$OUT" "$@" --json "$JSON"; rc=$?
t2=$(date +%s); echo "VERIFY rc=$rc wall=$((t2-t1)) s END $(date -Is)"
exit $rc
