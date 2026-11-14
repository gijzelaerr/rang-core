#!/usr/bin/env bash
# chain.sh NAME STEP... : run each STEP ("w SKY" or "u CONFIG SKY CAPC CAPS") as one job.sh job,
# one after another, logs in $O/logs/NAME-<n>.log. research/rml-gap.md.
set -u
here=$(dirname "$(readlink -f "$0")")
O=/mnt/d/rang/outputs/rml-gap-20261113
name=$1
shift
n=0
for step in "$@"; do
  n=$((n + 1))
  read -r mode rest <<<"$step"
  if [ "$mode" = u ]; then slots=8 mem=${UMEM:-16}; else slots=8 mem=${WMEM:-6}; fi
  bash "$here/job.sh" "$O/logs/$name-$n.log" $slots $mem python3 "$here/runs.py" $step
done
