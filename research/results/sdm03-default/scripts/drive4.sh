#!/bin/bash
# sdm03-default unattended driver (research/sdm03-default.md section 8): drive.sh dry | main | d1 | summary
# Not under the lock itself; every heavy step books the heavy lock with its real thread count and memory,
# at most $CAP slots booked by this driver at once. Rerunnable: a step with logs/<name>.ok is skipped.
source ~/Build/tmp/20261118-sdm03/env.sh
MODE=$1
mkdir -p $RUN $LOGS $OUT/sims
DLOG=$LOGS/driver-$MODE.log
status(){ { echo "# sdm03-default status (nash driver $MODE, $(date '+%F %H:%M %Z'))"; echo; echo "Driver PID $(cat $B/drive-$MODE.pid 2>/dev/null), log $DLOG"; echo "Running: $(cd $RUN && ls *.job 2>/dev/null | sed 's/\.job$//' | tr '\n' ' ')"; echo; tail -8 $DLOG | sed 's/^/    /'; } > $OUT/status.md.tmp 2>/dev/null && mv $OUT/status.md.tmp $OUT/status.md; }
log(){ echo "$(date -Is) $*" | tee -a $DLOG; status; }
admit(){ # N NAME: a job of CAP slots (a cost pair) waiting holds back every smaller one
  local booked; booked=$(cat $RUN/*.job 2>/dev/null | awk '{s+=$1} END{print s+0}')
  [ $1 -lt $CAP ] && ls $RUN/*.want >/dev/null 2>&1 && return 1
  [ $(( booked + $1 )) -le $CAP ]
}
launch(){ # NAME SLOTS MEM_GB cmd...
  local name=$1 n=$2 mem=$3 rc; shift 3
  [ -f $LOGS/$name.ok ] && return 0
  while true; do
    exec 9>$RUN/.lk; flock 9
    if admit $n $name; then echo "$n" > $RUN/$name.job; rm -f $RUN/$name.want; flock -u 9; break; fi
    [ $n -ge $CAP ] && touch $RUN/$name.want
    flock -u 9; sleep 30
  done
  log "start $name ($n slots, $mem GB)"
  $LOCK run --slots $n --mem $mem -- nice -n 19 ionice -c3 env RAYON_NUM_THREADS=$n OMP_NUM_THREADS=$n OPENBLAS_NUM_THREADS=$n MKL_NUM_THREADS=$n /usr/bin/time -f "TIME $name %e s %M KB" "$@" >> $LOGS/$name.log 2>&1
  rc=$?
  rm -f $RUN/$name.job
  [ $rc -eq 0 ] && touch $LOGS/$name.ok
  printf '%s\t%s\t%s\t%s\t%s\n' "$name" "$n" "$mem" "$rc" "$(grep '^TIME' $LOGS/$name.log | tail -1)" >> $OUT/timing.tsv
  log "end $name rc $rc ($(grep '^TIME' $LOGS/$name.log | tail -1))"
  return $rc
}
arm(){ # TAG ARM MS STATE KIND COLUMN SLOTS MEM
  launch arm-$1-$2 ${7:-8} ${8:-32} $PY $SD image $2 --kind $5 --ms $3 --prefix $4/img/$2/image --mask $MASK --column $6
}
seen_state(){ # SRC DST: link floor-6's state (read only), never its family2
  mkdir -p $2
  for f in $1/*; do b=$(basename $f); case $b in family2|summary.json) continue;; esac; [ -e $2/$b ] || ln -s $f $2/$b; done
}
pair(){ # TAG ARM_A MEM_A ARM_B MEM_B MS STATE: both under one 16-slot booking (amendment 2)
  [ -f $LOGS/arm-$1-$2.ok ] && [ -f $LOGS/arm-$1-$4.ok ] && return 0
  launch pair-$1-$2-$4 16 $(( $3 + $5 )) bash $B/pair.sh $1 $2 $4 $6 $7
}
real_arms(){ # TAG STATE MS: section 2's ESO137 arms, A0 paired with SDa for cost
  local t=$1 st=$2 ms=$3
  pair $t A0 16 SDa 32 $ms $st || return 1
  pair $t Sa 32 Sm 32 $ms $st || return 1
  pair $t SDm03 32 W-SDa 48 $ms $st || return 1
  launch score-$t 4 16 $PY $SD real --group MAIN_4 -- score $(for a in A0 SDa Sa Sm SDm03 W-SDa; do echo $a=$st/img/$a/image; done) --out $st --held $HELD
}
real_track(){ # GROUP -> 0 done, 3 a condition or gate failed (next candidate), 1 error
  local g=$1 r=$OUT/r-$1
  launch fetchmeta-$g 1 2 $PY $SD fetchms --group $g --root $Z --src $E2A --phase meta || return 1
  launch meta-$g 1 4 $PY $SD real --group $g -- meta --out $r --held $HELD --zarr $Z || { log "STOP $g: section 3.1's conditions (meta.json)"; return 3; }
  launch gains-$g 1 4 $PY $SD real --group $g -- fetch --out $r --held $HELD --zarr $Z --gains $r/gains || { log "STOP $g: no gain group within 1 s"; return 3; }
  launch fetchdata-$g 2 4 $PY $SD fetchms --group $g --root $Z --src $E2A --phase data || return 1
  launch build-$g 1 12 $PY $SD real --group $g -- build --out $r --held $HELD --zarr $Z --gains $r/gains || { [ -f $r/build/GH.json ] && { log "STOP $g: gate GH"; return 3; }; return 1; }
  launch copy-$g 1 6 $PY $SD real --group $g -- copy --out $r --held $HELD || return 1
  launch selfcal-$g 8 32 $PY -m rang.core_cli selfcal $P1 $r/P/pilot.ms --run-dir $r/P/run || return 1
  launch state-$g 4 16 $PY $SD real --group $g -- state --out $r --held $HELD --cal2 $r/build/cal2.ms --g1 $r --ms4 $r/P/pilot.ms || return 1
  $PY -c "import json,sys; p=json.load(open('$r/pilot.json')); sys.exit(0 if p['Sp_health']['pass'] and p['HB']['pass'] else 3)" || { log "STOP $g: gate GS1 or HB"; return 3; }
  real_arms $g $r $r/P/pilot.ms
}
next_cand(){ local c; exec 8>$RUN/.cand; flock 8; c=$(head -1 $RUN/cands); sed -i 1d $RUN/cands; flock -u 8; echo $c; }
worker(){
  local c rc
  while true; do
    c=$(next_cand); [ -z "$c" ] && { log "no candidate left"; return 4; }
    real_track $c; rc=$?
    if [ $rc -eq 3 ]; then log "candidate $c not used (rc 3); next"; continue; fi
    [ $rc -eq 0 ] && echo $c >> $RUN/used
    log "candidate $c track rc $rc"; return $rc
  done
}
sim_track(){ # SKY [--sky-seed S --noise-seed N]
  local s=$1 d=$OUT/sims/$1; shift
  launch sim-$s 4 16 $PY $G3 $d.ms --sky $s --catalogue $d.json "$@" || return 1
  launch simprep-$s 4 24 $PY $SD simprep $d.ms $d.json $d.prep || return 1
  for a in A0 SDa Sa W-SDa; do launch arm-$s-$a 8 16 $PY $SD image $a --kind sim --ms $d.ms --prefix $d.img/$a/image --column DATA || return 1; done
  launch simscore-$s 4 24 $PY $SD simscore $d.prep $(for a in A0 SDa Sa W-SDa; do echo $a=$d.img/$a/image; done)
}
summary(){
  local used real=() g
  for g in $(cat $RUN/used 2>/dev/null); do real+=("$g=$OUT/r-$g=$g"); done
  launch summary-$MODE-$(date +%H%M%S) 1 4 $PY $SD summary $OUT/summary-$MODE.json --logs $LOGS \
    --real "${real[@]}" --seen pilot=$OUT/seen-pilot=pilot s10=$OUT/seen-s10=s10 \
    --sim $(for s in X1 X2 X3 X4; do echo $s=$OUT/sims/$s.prep; done) --seen-sim D1=$OUT/sims/D1.prep
  grep -h "SDM03 SUMMARY" $LOGS/summary-$MODE-*.log | tail -1 | tee -a $DLOG
}
echo $$ > $B/drive-$MODE.pid
log "driver $MODE start, commit $(git -C $WT rev-parse --short HEAD), extension $(sha256sum $WT/python/rang/_core.abi3.so | cut -c1-16)"
( while sleep 300; do status; done ) & SPID=$!
RC=0
case $MODE in
  dry)  # section 3.3: seen data only
    seen_state $F6/pilot $OUT/seen-pilot
    real_arms pilot $OUT/seen-pilot $F5/g1/P/pilot.ms & P1PID=$!
    sim_track D1; R1=$?
    wait $P1PID; R2=$?
    log "dry tracks: D1 rc $R1, pilot rc $R2"
    summary; RC=$(( R1 + R2 ));;
  main)
    [ -f $RUN/cands ] || printf 'MAIN_1\nMAIN_6\nMAIN_2\nMAIN_3\n' > $RUN/cands
    worker & W1=$!; sleep 5; worker & W2=$!
    sim_track X1 --sky-seed 20261841 --noise-seed 20261851 & S1=$!
    sim_track X2 --sky-seed 20261842 --noise-seed 20261852 & S2=$!
    sim_track X3 --sky-seed 20261843 --noise-seed 20261853 & S3=$!
    sim_track X4 --sky-seed 20261844 --noise-seed 20261854 & S4=$!
    for p in $W1 $W2 $S1 $S2 $S3 $S4; do wait $p; r=$?; log "track pid $p rc $r"; RC=$(( RC + r )); done
    summary
    # scan 10 (seen, reported only) after the reserve and the fresh skies (amendment 4)
    seen_state $F6/ho $OUT/seen-s10; real_arms s10 $OUT/seen-s10 $F6/ho/P/pilot.ms; log "seen s10 rc $?"
    summary;;
  d1) sim_track D1; RC=$?;;
  sims)  # X1-X3 alone (X4 ran on in the main driver) (rerun after the restart left partial outputs, amendment 4)
    sim_track X1 --sky-seed 20261841 --noise-seed 20261851 & S1=$!
    sim_track X2 --sky-seed 20261842 --noise-seed 20261852 & S2=$!
    sim_track X3 --sky-seed 20261843 --noise-seed 20261853 & S3=$!
    for p in $S1 $S2 $S3; do wait $p; r=$?; log "track pid $p rc $r"; RC=$(( RC + r )); done;;  # the seen sky alone (rerun after the venv fix, amendment 2)
  summary) summary;;
esac
kill $SPID 2>/dev/null
log "SDM03 DONE $MODE rc $RC"
exit $RC
