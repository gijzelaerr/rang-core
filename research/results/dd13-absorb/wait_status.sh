#!/usr/bin/env bash
# Every 30 min: rewrite the status file; exit when both lanes have ended.
R=D:/rang/outputs/dd13-20261127; S=C:/Users/gijsm/Github/rang/outputs/status/dd13-absorb.md
while true; do
  done_a=$(grep -c "loop-QP12 end" $R/times.log); done_b=$(grep -c "loop-ATp3 end" $R/times.log)
  {
    echo "# dd13-absorb (DD13, issue #15) status"
    echo "- $(date '+%Y-%m-%d %H:%M') (auto, every 30 min). Note frozen ab879867; branch dd13-absorb; CI green on e2ebbf44."
    echo "- Gates: R13 PASS (bitwise); UV FAIL as frozen (1.8 % of weight below 1,074 lambda), UV12 not run."
    echo "- Lanes on glacier (8 slots/20 GB each): A QA12 -> QP12; B SA12 -> ATP12 -> ATa3 -> ATp3."
    echo "- Jobs ended: $(grep ' end ' $R/times.log | grep loop- | awk '{print $1":"$4}' | tr '\n' ' ')"
    for a in QA12 SA12 QP12 ATP12 ATa3 ATp3; do
      f=$R/logs/loop-$a.log; [ -f $f ] && echo "- $a: $(grep -o "^$a cycle [0-9]*" $f | tail -1)$( [ -f $R/loop/$a/stopped.json ] && echo ' (stopped by stage rule)')"
    done
    echo "- Next: diag, score, section 10, archive, cleanup, check_all --quick, push."
  } > $S
  grep -E "Traceback|Error" $R/logs/loop-*.log >/dev/null 2>&1 && echo "ERROR in a loop log"
  grep -E "rc=[1-9]" $R/times.log && echo "a job failed"
  [ "$done_a" -ge 1 ] && [ "$done_b" -ge 1 ] && { echo "both lanes ended"; exit 0; }
  sleep 1800
done
