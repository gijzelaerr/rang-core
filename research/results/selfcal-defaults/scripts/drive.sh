#!/bin/bash
# selfcal-defaults grid driver: at most three grid runs at a time, every job through run_nash.sh (the lock).
cd ~/Build/tmp/20261117-floor4
source ~/.rang-env.sh
G=~/rang-data/outputs/selfcal-defaults-20261117
F4=~/rang-data/outputs/floor-4-20261117/floor-4
PY=~/Github/rang/.venv/bin/python
LOCK="$PY $HOME/Github/rang/tools/heavy_lock.py"
say() { echo "$(date -u +%FT%TZ) $*"; }
running() { pgrep -f "run_nash.sh grid $1\$" >/dev/null || pgrep -f "run_nash.sh grid $1 " >/dev/null; }
nrun() { local n=0; for r in L300 L60 L120 L600 D M60 M120 M300 M600 N60 N120 N300 N600; do running $r && n=$((n+1)); done; echo $n; }
# deferred scores of the three runs started with NOSCORE=1
pending="L300 L60 L120"
queue="L600 D M60 M120 M300 M600 N60 N120 N300 N600"
while :; do
  for r in $pending; do
    if ! running $r; then
      if grep -q "$r end" logs/grid-$r.log; then
        say "score $r"; nohup nice -n 19 ionice -c3 ./run_nash.sh score $r > logs/score-$r.log 2>&1 < /dev/null &
      else say "FAILED $r (no end line)"; fi
      pending=$(echo $pending | sed "s/\b$r\b//")
    fi
  done
  set -- $queue
  if [ $# -gt 0 ] && [ "$(nrun)" -lt 3 ]; then
    r=$1; shift; queue="$*"
    say "launch $r"; nohup nice -n 19 ionice -c3 ./run_nash.sh grid $r > logs/grid-$r.log 2>&1 < /dev/null &
    sleep 20; continue
  fi
  [ -z "$queue" ] && [ -z "$(echo $pending)" ] && [ "$(nrun)" -eq 0 ] && ! pgrep -f "run_nash.sh score" >/dev/null && break
  sleep 120
done
for r in L300 L60 L120 L600 D M60 M120 M300 M600 N60 N120 N300 N600; do [ -f $G/$r/score.json ] || say "MISSING score $r"; done
cd ~/Worktrees/rang/floor-4
say "summary 1"
nice -n 19 ionice -c3 $LOCK run --slots 1 --mem 4 -- $PY examples/selfcal_grid.py summary --out $G --f4out $F4 > ~/Build/tmp/20261117-floor4/logs/summary1.log 2>&1
cp $G/summary.json $G/summary-before-X.json
if python3 -c "import json,sys; sys.exit(0 if 'chosen' in json.load(open('$G/summary.json')) else 1)"; then
  cd ~/Build/tmp/20261117-floor4
  say "launch X"; nice -n 19 ionice -c3 ./run_nash.sh grid X > logs/grid-X.log 2>&1 < /dev/null
  cd ~/Worktrees/rang/floor-4
  say "summary 2"
  nice -n 19 ionice -c3 $LOCK run --slots 1 --mem 4 -- $PY examples/selfcal_grid.py summary --out $G --f4out $F4 > ~/Build/tmp/20261117-floor4/logs/summary2.log 2>&1
else say "no chosen cell: X not run"; fi
say DONE
