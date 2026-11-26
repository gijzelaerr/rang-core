#!/usr/bin/env bash
# lane.sh JOB... ; JOB = LABEL|SLOTS|MEM|args ; skips a label already ended rc=0, stops a lane on failure
# a JOB "wait:LABEL" blocks until LABEL ended rc=0 (exits if any job failed)
R=D:/rang/outputs/dd8-20261125
for j in "$@"; do
  if [[ $j == wait:* ]]; then
    l=${j#wait:}
    until grep -q "^$l end .* rc=0" $R/times.log 2>/dev/null; do grep -q "^$l end .* rc=[1-9]" $R/times.log 2>/dev/null && exit 1; sleep 30; done
    continue
  fi
  IFS="|" read label slots mem args <<< "$j"
  grep -q "^$label end .* rc=0" $R/times.log 2>/dev/null && continue
  bash $R/scripts/job.sh $label $slots $mem -- $args || exit 1
done
