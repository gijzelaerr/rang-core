#!/usr/bin/env bash
# lane.sh JOB... ; JOB = LABEL|SLOTS|MEM|dd6 args (space separated); skips a label already ended rc=0
R=D:/rang/outputs/dd6-20261125
for j in "$@"; do
  IFS="|" read label slots mem args <<< "$j"
  grep -q "^$label end .* rc=0" $R/times.log 2>/dev/null && continue
  bash $R/scripts/job.sh $label $slots $mem -- $args
done
