#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
# d_job.sh: arm D of research/wsclean38-rebaseline.md on nash. ws-multiscale on DF5-O's field,
# one repeat each with nash-native WSClean 3.7 and 3.8, under nash's heavy lock (4 slots),
# nice 19, ionice -c3. examples/oracle_wsclean_clean.py comes from the wsclean-38 branch.
set -u
here=$(dirname "$(readlink -f "$0")")
D=$HOME/rang-data/outputs/wsclean38-20261118/d
mkdir -p "$D/bin" "$D/runs"
cp "$here/docker_shim.sh" "$D/bin/docker" && chmod +x "$D/bin/docker"
export PATH=$D/bin:$PATH
for v in 3.7 3.8; do
  t=$(date +%s)
  python3 ~/Github/rang/tools/heavy_lock.py run --slots 4 --mem 8 -- nice -n 19 ionice -c3 \
    python3 "$D/src/examples/oracle_wsclean_clean.py" run "$D/field" "$D/runs/w$v" ws-multiscale \
      --image rang-wsclean-native:$v >>"$D/d_job.log" 2>&1
  echo "RUN w$v rc=$? wall=$(($(date +%s) - t))s $(date -Is)" >>"$D/d_job.log"
done
