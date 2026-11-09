#!/usr/bin/env bash
# batch.sh BIN TAG RUN... : for each RUN, GeMClean (run_g.sh) then WSClean (run_w.sh) unless
# WSClean's run exists already (WSCLEAN=0 skips it, WSCLEAN=force reruns it).
here=$(dirname "$(readlink -f "$0")")
source "$here/cfg.sh"
bin=$1; tag=$2; shift 2
for run in "$@"; do
  bash "$here/run_g.sh" "$bin" "$tag" "$run"
  if [ "${WSCLEAN:-1}" = force ] || { [ "${WSCLEAN:-1}" != 0 ] && [ ! -f "$O/runs/wsclean/$run/w-report-done" ]; }; then
    bash "$here/run_w.sh" "$run" && touch "$O/runs/wsclean/$run/w-report-done"
  fi
done
