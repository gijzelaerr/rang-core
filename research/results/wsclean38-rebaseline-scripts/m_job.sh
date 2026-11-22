#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
# m_job.sh RUN... : arm M of research/wsclean38-rebaseline.md on nash, one WSClean 3.8 run at a
# time under nash's heavy lock (shared, 8 slots), nice 19, ionice -c3.
set -u
here=$(dirname "$(readlink -f "$0")")
export MSM_OUT=$HOME/rang-data/outputs/wsclean38-20261118/m
export MSM_H4=$HOME/rang-data/outputs/stop28-default-20261117/data/h4.ms
export MSM_PILOT=$HOME/rang-data/outputs/stop28-default-20261117/in/pilot/cal2.ms
log=$MSM_OUT/m_job.log
echo "START $(date -Is) :: $*" >>"$log"
for r in "$@"; do
  mem=8; [ "${r:0:2}" = PM ] && mem=16
  t=$(date +%s)
  python3 ~/Github/rang/tools/heavy_lock.py run --slots 8 --mem $mem -- nice -n 19 ionice -c3 \
    python3 "$here/m_runs.py" w "$r" >>"$log" 2>&1
  echo "RUN $r rc=$? wall=$(($(date +%s) - t))s $(date -Is)" >>"$log"
done
echo "END $(date -Is)" >>"$log"
