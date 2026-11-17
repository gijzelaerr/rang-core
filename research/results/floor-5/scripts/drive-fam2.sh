#!/bin/bash
# Coordinator driver, 2026-11-17: floor-5 family II after G1 (floor-5.md section 7). Two at a time at 8 slots (16 in all, inside the night cap).
source ~/Build/tmp/20261117-floor5/env.sh
log(){ echo "$(date -Is) $*"; }
while pgrep -u gijs -f "20261117-floor5/g1.sh" >/dev/null; do sleep 120; done
log "G1 ended"; tail -3 $OUT/logs/g1.log
[ -f $OUT/g1/P/pilot.ms/table.dat ] || { log "no G1 pilot.ms: stop"; exit 1; }
one() { $LOCK run --slots 8 --mem 20 -- nice -n 19 ionice -c3 ~/Build/tmp/20261117-floor5/fam2.sh $1 > $OUT/logs/fam2-$1.log 2>&1; echo "$(date -Is) fam2 $1 rc $?"; }
export -f one
printf "%s\n" R3 Dm1 Dm03 Dms03 Du1 S C0 | xargs -P 2 -I{} bash -c "one {}"
while pgrep -u gijs -f "20261117-floor5/arms.sh" >/dev/null; do sleep 120; done
log "family II and arms done"
