#!/bin/bash
# E2-N follow-up launcher on nash (research/e2n-followup.md 1.2-1.4): stage inputs,
# check the copy's FLAG hash, run the chain up to leakage-casa, then hold
# target-wsclean (8 slots, about 3 h) until 06:00 SAST so it never runs in
# E3-A's 22:00-06:00 window, then finish the chain and check the original MS.
set -u
W=$(cd "$(dirname "$0")/../../../.." && pwd)
F=$W/research/results/e2n-followup/scripts
WPY=${WPY:-$W/.venv/bin/python}; export WPY
LOCK=$HOME/Github/rang/tools/heavy_lock.py
SRC=$HOME/rang-data/outputs/e2n-20261116
RUN=$HOME/rang-data/outputs/e2n-followup-20261118
R=$RUN/R
INPUT=$W/research/results/e2n/flaghash-input.json
ST=$W/outputs/status/e2n-followup.md
note() { echo "$(date -Is) $*" >> "$R/launch.log"; }
hashck() { python3 "$LOCK" run --slots 1 --mem 4 -- nice -n 19 ionice -c3 "$WPY" "$F/fu_hash.py" "$1" "$INPUT" "$2"; }
mkdir -p "$R/leakage"
[ -d "$R/rang-run" ] || python3 "$LOCK" run --slots 1 --mem 2 -- nice -n 19 ionice -c3 cp -a "$SRC/R/rang-run" "$R/"
cp -a "$SRC"/R/leakage/rang*.json "$R/leakage/" 2>/dev/null
hashck "$RUN/e2n.ms" "$R/fu-copy-hash.json" || { note "copy hash differs"; exit 2; }
hashck "$SRC/e2n.ms" "$R/fu-original-hash-before.json" || { note "original hash differs"; exit 2; }
note "inputs staged, hashes equal"
bash "$F/fu_chain.sh" tricolour leakage-casa || { note "chain stopped"; exit 3; }
note "chain to leakage-casa done"
hashck "$SRC/e2n.ms" "$R/fu-original-hash-mid.json" || note "original hash differs (mid)"
now=$(TZ=Africa/Johannesburg date +%H%M)
if [ "$now" -ge 2200 ] || [ "$now" -lt 0600 ] || [ "$now" -ge 1900 ]; then
  # target-wsclean would not end before 22:00: wait for 06:00 SAST
  target=$(TZ=Africa/Johannesburg date -d "$( [ "$now" -lt 0600 ] && echo today || echo tomorrow ) 06:00" +%s)
  note "holding target-wsclean until $(date -d @"$target" -Is)"
  sed -i "s/^- next:.*/- next: target-wsclean held until 06:00 SAST (E3-A window)/" "$ST" 2>/dev/null
  while [ "$(date +%s)" -lt "$target" ]; do sleep 300; done
fi
bash "$F/fu_chain.sh" target-wsclean final-restore || { note "chain stopped (target)"; exit 3; }
hashck "$SRC/e2n.ms" "$R/fu-original-hash-after.json" || note "original hash differs (after)"
note "done"
