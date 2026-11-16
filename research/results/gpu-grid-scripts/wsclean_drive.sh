#!/usr/bin/env bash
# WSClean arms of issue #12's timing, in WSL: S1, H2, H3 x -mgain 0.8, 0.9 x 3 repeats, each under an
# exclusive heavy_lock hold; a ticket that waits 10 min at the head of the queue is withdrawn and
# retried 10 min later. Usage: bash wsclean_drive.sh
D=$(cd "$(dirname "$0")" && pwd)
OUT=/mnt/d/rang/outputs/20261116-gpu-grid/wsclean
mkdir -p "$OUT"
for rep in 1 2 3; do
  for sky in s1 h2 h3; do
    for mg in 0.8 0.9; do
      name=$sky-minres-mgain$mg-r$rep
      while [ ! -f "$OUT/$name.txt" ]; do
        err=$(mktemp)
        python3 $HOME/Github/rang/tools/heavy_lock.py run -- bash "$D/wsclean_run.sh" $sky $mg $rep 2> "$err" &
        pid=$!
        head=0
        while kill -0 $pid 2>/dev/null; do
          sleep 5
          [ -f "$OUT/$name.load" ] && { wait $pid; break; }
          if tail -1 "$err" | grep -q behind; then head=0; else head=$((head + 5)); fi
          if [ $head -ge 600 ]; then
            kill $pid; echo "$name withdrawn $(date +%T)" | tee -a "$OUT/withdrawn.txt"; sleep 600; break
          fi
        done
        wait $pid 2>/dev/null
        rm -f "$err"
      done
      tail -1 "$OUT/$name.log" >/dev/null
    done
  done
done
echo "wsclean arms done"
