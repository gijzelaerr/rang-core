#!/usr/bin/env bash
# writes the status file from the run's records (every 25 min until ALL_DONE)
R=D:/rang/outputs/dd15-20261128; S=C:/Users/gijsm/Github/rang/outputs/status/dd15-beam-gate.md
while true; do
  {
  echo "# dd15-beam-gate (#15) status"
  echo "Updated $(date '+%Y-%m-%d %H:%M %Z') (glacier)"
  echo "- Branch dd15-beam-gate: frozen note 925fd92a, driver 2237db19. Run root $R."
  echo "- Prep: build/GB15 then gate R15; lanes A ATG12 -> QPG12, B QPG12-O (6 slots, 20 GB each)."
  for a in ATG12 QPG12 QPG12-O R-QPG12; do
    n=$(ls -d $R/loop/$a/cycle-*/ 2>/dev/null | wc -l); [ $n -gt 0 ] && echo "- $a: $n cycle dirs$( [ -f $R/loop/$a/stopped.json ] && echo ', stopped at 6')"
  done
  echo "- Last job line: $(tail -1 $R/times.log 2>/dev/null)"
  grep -q "rc=[1-9]" $R/times.log 2>/dev/null && echo "- A step failed: see times.log"
  echo "- Next: score by the frozen rule; section 7's real loop only on an 'in' reading."
  } > $S
  grep -q ALL_DONE $R/times.log 2>/dev/null && exit 0
  sleep 1500
done
