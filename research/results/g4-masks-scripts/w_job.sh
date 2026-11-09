#!/usr/bin/env bash
# w_job.sh LOG RUN... : w_batch.sh detached-friendly, with START, END and exit codes in LOG
# (a restart leaves a readable record). research/g4-masks.md.
set -u
log=$1
shift
here=$(dirname "$(readlink -f "$0")")
echo "START $(date -Is) pid $$ :: $*" >"$log"
for r in "$@"; do
  t=$(date +%s)
  bash "$here/w_batch.sh" "$r" >>"$log" 2>&1
  echo "RUN $r rc=$? wall=$(($(date +%s) - t))s $(date -Is)" >>"$log"
done
echo "END $(date -Is)" >>"$log"
