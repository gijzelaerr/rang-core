#!/usr/bin/env bash
# writes the status file from the run's records (every 30 min while lanes run)
R=D:/rang/outputs/dd14-20261127; S=C:/Users/gijsm/Github/rang/outputs/status/dd14-flux-scale.md
while ! grep -q LANES_DONE $R/times.log; do
  {
  echo "# dd14-flux-scale (#15) status"
  echo "Updated $(date '+%Y-%m-%d %H:%M %Z') (glacier)"
  echo "- Branch dd14-flux-scale pushed at e2b57a3a (frozen note 20308966, driver, A1); CI tests and docs green."
  echo "- Run root $R. Gates GB1-4 and R14 pass. Lanes: A Q12 -> QP12 -> AX; B AT12 -> ATP12 -> QPN12 (8 slots, 20 GB each)."
  for a in Q12 QP12 QPN12 AT12 ATP12 AX; do
    n=$(ls -d $R/loop/$a/cycle-*/ 2>/dev/null | wc -l); [ $n -gt 0 ] && echo "- $a: $n cycle dirs$( [ -f $R/loop/$a/stopped.json ] && echo ', stopped at 6')"
  done
  echo "- Last job lines: $(tail -1 $R/times.log)"
  echo "- Next: score, then the real flux check only if the frozen rule reads in."
  } > $S
  sleep 1500
done
