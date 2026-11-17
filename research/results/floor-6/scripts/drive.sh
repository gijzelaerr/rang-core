#!/bin/bash
# floor-6 unattended driver (research/floor-6.md sections 8 and 9). Not under the lock itself;
# every heavy step books the heavy lock with its real thread count. Rerunnable: stages skip done work.
source ~/Build/tmp/20261117-floor6/env.sh
RUN=$B/run; mkdir -p $RUN $LOGS $FAM; rm -f $RUN/*.job
DLOG=$LOGS/drive.log
log(){ echo "$(date -Is) $*" | tee -a $DLOG; status; }
status(){ { echo "# floor-6 status (nash driver, $(date -Is))"; echo; echo "Driver: $B/drive.sh, PID $(cat $B/drive.pid 2>/dev/null), log $DLOG"; echo "Running: $(cd $RUN && ls *.job 2>/dev/null | tr '\n' ' ')"; echo; tail -8 $DLOG | sed 's/^/    /'; } > $HOME/Github/rang/outputs/status/floor-6.md.tmp && mv $HOME/Github/rang/outputs/status/floor-6.md.tmp $HOME/Github/rang/outputs/status/floor-6.md; }
# night cap: at most 8 slots from 21:30 to 06:00; a launch above 8 in total needs every job (with
# its estimate, x1.5) to end by 21:00 (clarification 1)
admit(){ # N EST_MIN -> 0 if it may start now
  local n=$1 est=$2 now end h21 h06 booked maxend
  now=$(date +%s); end=$(( now + est * 90 )); h21=$(date -d "today 21:00" +%s); h06=$(date -d "today 06:00" +%s)
  booked=$(cat $RUN/*.job 2>/dev/null | awk '{s+=$1} END{print s+0}')
  maxend=$(cat $RUN/*.job 2>/dev/null | awk -v e=$end 'BEGIN{m=e} {if($2>m)m=$2} END{print m}')
  [ $(( booked + n )) -le 8 ] && return 0
  [ $(( booked + n )) -le 16 ] && [ $now -ge $h06 ] && [ $maxend -le $h21 ] && return 0
  return 1
}
launch(){ # NAME SLOTS MEM EST cmd...
  local name=$1 n=$2 mem=$3 est=$4; shift 4
  while true; do
    exec 9>$RUN/.lk; flock 9
    if admit $n $est; then echo "$n $(( $(date +%s) + est * 90 ))" > $RUN/$name.job; flock -u 9; break; fi
    flock -u 9; sleep 60
  done
  log "start $name ($n slots, $mem GB)"
  $LOCK run --slots $n --mem $mem -- nice -n 19 ionice -c3 env RAYON_NUM_THREADS=$n OMP_NUM_THREADS=$n OPENBLAS_NUM_THREADS=$n MKL_NUM_THREADS=$n /usr/bin/time -f "TIME $name %e s %M KB" "$@" >> $LOGS/$name.log 2>&1
  local rc=$?
  rm -f $RUN/$name.job
  log "end $name rc $rc ($(grep '^TIME' $LOGS/$name.log | tail -1))"
  return $rc
}
s6(){ $PY $S6 "$@" --held $HELD; }
export -f s6
arm(){ launch arm-$1 8 ${2:-20} ${3:-20} $B/arm.sh $1; }
score_ho(){ local a=(); for x in "$@"; do [ -f $HO/family2/$x.json ] || a+=("$x=$FAM/$x/image"); done; [ ${#a[@]} -eq 0 ] || launch score-ho-$1 2 8 10 $PY $S6 score "${a[@]}" --out $HO --held $HELD; }
score_pi(){ local a=(); for x in "$@"; do [ -f $PI/family2/$x.json ] || a+=("$x=$( [ ${x:0:1} = f ] && echo $F5/family2/${x#f} || echo $FAM/$x )/image"); done; [ ${#a[@]} -eq 0 ] || launch score-pi-$1 2 8 10 $PY $S6 score "${a[@]}" --out $PI --held $HELD; }

pilot_track(){
  launch pilot-state 4 16 25 $PY $S6 state --out $PI --held $HELD --cal2 $HELD/cal2.ms --g1 $F5/g1 --ms4 $F5/g1/P/pilot.ms --pilot-T || return 1
  score_pi fR3 fDm03 fS || return 1
  log "GP numbers: $(grep -h score $LOGS/score-pi-fR3.log | tail -3 | tr '\n' ' ')"
  arm pRm3 || return 1; arm pSm3 24 30 || return 1; arm pSDm03 24 35 || return 1
  score_pi pRm3 pSm3 pSDm03 || return 1
  log "pilot track done"
}
ho_track(){
  launch meta 1 4 5 $PY $S6 meta --out $HO --held $HELD || { log "STOP: candidate 2 fails section 2's conditions (meta.json)"; return 3; }
  launch fetch 1 4 20 $PY $S6 fetch --out $HO --held $HELD --gains $GAINS || { log "STOP: fetch failed or no gain group"; return 3; }
  launch build 1 12 45 $PY $S6 build --out $HO --held $HELD --gains $GAINS || { log "STOP: build or gate GH failed"; return 3; }
  launch copy 1 6 15 $PY $S6 copy --out $HO --held $HELD || return 1
  if [ ! -f $HO/P/run/selfcal/summary.json ]; then
    launch selfcal 8 32 70 $PY -m rang.core_cli selfcal $WT/research/results/floor-3/p1.yaml $HO/P/pilot.ms --run-dir $HO/P/run || return 1
  fi
  launch ho-state 4 16 25 $PY $S6 state --out $HO --held $HELD --cal2 $HO/build/cal2.ms --g1 $HO --ms4 $HO/P/pilot.ms || return 1
  arm R3 || return 1; arm Dm03 || return 1; arm C0 || return 1; arm S 24 30 || return 1
  score_ho R3 Dm03 C0 S || return 1
  log "primaries scored"
  arm Dm1 || return 1; arm Rm3 || return 1; arm Sm3 24 30 || return 1; arm SDm03 24 35 || return 1
  score_ho Dm1 Rm3 Sm3 SDm03 || return 1
  log "held-out track done"
}
echo $$ > $B/drive.pid
log "driver start, pin: $(sha256sum $WT/python/rang/_core.abi3.so | cut -c1-16) commit $(git -C $WT rev-parse --short HEAD)"
( while sleep 600; do status; done ) & SPID=$!
pilot_track & PT=$!
ho_track; HRC=$?
wait $PT; PRC=$?
log "tracks: held-out rc $HRC, pilot rc $PRC"
RC=1
if [ $HRC -eq 0 ] && [ $PRC -eq 0 ]; then
  launch summary 1 4 5 $PY $S6 summary --out $HO --held $HELD --pilot-out $PI --fam $FAM; RC=$?
  grep -h "FLOOR6 SUMMARY" $LOGS/summary.log | tail -1 | tee -a $DLOG
fi
kill $SPID 2>/dev/null
log "FLOOR6 DONE rc $RC (held-out $HRC, pilot $PRC)"
exit $RC
