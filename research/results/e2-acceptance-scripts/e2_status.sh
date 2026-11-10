#!/bin/sh
# Rewrites outputs/status/fp-e2.md every 20 minutes from the run logs (research/e2-acceptance.md).
# The first lines come from e2_status.head (edited by hand when the plan changes).
S=/c/Users/gijsm/Github/rang/outputs/status/fp-e2.md
H=/c/Users/gijsm/Github/rang/outputs/status/fp-e2.head
while true; do
  {
    cat "$H"
    for f in /d/rang/data/e2-a.log /d/rang/data/e2-d.log; do
      echo "- $(basename $f): $(grep -E '^(START|END)' $f | tail -1 | cut -c1-60) | $(tail -1 ${f%.log}/progress.log 2>/dev/null | cut -c1-60)"
    done
    for f in $(ls -t /d/rang/outputs/e2-2026*.log /d/rang/outputs/e2-2026*/*.log 2>/dev/null | head -3); do
      echo "- $(echo $f | sed 's|/d/rang/outputs/||'): $(grep -E '^(START|END)' $f | tail -1 | cut -c1-50)"
    done
    echo "- auto-updated $(date '+%F %T')"
  } > "$S.tmp" && mv "$S.tmp" "$S"
  sleep 1200
done
