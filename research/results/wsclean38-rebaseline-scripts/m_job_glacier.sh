#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
# m_job_glacier.sh RUN... : arm M of research/wsclean38-rebaseline.md (amendment 2) from glacier's
# WSL: WSClean 3.8 (glacier's image) on the archived H4 and pilot, one run at a time under the
# main checkout's heavy lock (shared, 8 slots; 16 GB for PM), nice 10.
set -u
here=$(dirname "$(readlink -f "$0")")
export MSM_OUT=/mnt/d/rang/outputs/wsclean38-20261118/m M_RUNTIME=docker W_IMAGE=rang-wsclean-native:3.8
log=$MSM_OUT/m_job_glacier.log
echo "START $(date -Is) :: $*" >>"$log"
for r in "$@"; do
  mem=8; [ "${r:0:2}" = PM ] && mem=16
  t=$(date +%s)
  nice -n 10 python3 /mnt/c/Users/gijsm/Github/rang/tools/heavy_lock.py run --slots 8 --mem $mem -- \
    python3 "$here/m_runs.py" w "$r" >>"$log" 2>&1
  echo "RUN $r rc=$? wall=$(($(date +%s) - t))s $(date -Is)" >>"$log"
done
echo "END $(date -Is)" >>"$log"
