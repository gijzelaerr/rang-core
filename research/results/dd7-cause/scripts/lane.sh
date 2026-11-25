#!/usr/bin/env bash
# lane.sh JOB... ; JOB = LABEL|SLOTS|MEM|tool args ; skips a label already ended rc=0, stops a lane on failure
R=D:/rang/outputs/dd7-20261125
for j in "$@"; do
  IFS="|" read label slots mem args <<< "$j"
  grep -q "^$label end .* rc=0" $R/times.log 2>/dev/null && continue
  bash $R/scripts/job.sh $label $slots $mem -- $args || exit 1
done
