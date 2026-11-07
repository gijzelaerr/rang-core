#!/usr/bin/env bash
# probe.sh : WSClean 3.7 oracle probe (research/g9-stokes.md, section 2), before any GeMClean run.
# A two-source sky (A: I=1, Q=-0.8; B: I=0.6, Q=+0.5) with per-correlation weights and flags:
# which source does -join-polarizations pick first (linear or squared sum), and which weights
# feed WSCIMGWG per polarisation and channel. Small: 16 dishes, 1 h at 60 s, 4 channels, 512^2.
set -euo pipefail
W=$HOME/Worktrees/rang/fp-g9-stokes
O=/mnt/d/rang/outputs/g9-20261107-01-probe
rm -rf "$O" "$O.code"; mkdir -p "$O" "$O.code"
cp "$W/examples/g9_stokes_simulate.py" "$0" "$O.code/"
git -C "$W" rev-parse HEAD > "$O.code/commit"
cd "$W"
.venv/bin/python examples/g9_stokes_simulate.py "$O/probe.ms" --sky probe --nant 16 --hours 1 --dt 60 \
  --nchan 4 --size 512 --scale 3 --noise-ujy 200 --weights varied --catalogue "$O/probe.json" > "$O/sim.log"
run() {  # run NAME ARGS...
  local name=$1; shift
  mkdir -p "$O/$name/tmp"
  docker run --rm --user "$(id -u):$(id -g)" --network none -e HOME=/tmp -e OMP_NUM_THREADS=4 \
    -v "$O:/data" -w /data/$name rang-wsclean-native:3.7 \
    wsclean -gridder wgridder -no-min-grid-resolution -wgridder-accuracy 1e-6 -no-update-model-required \
    -size 512 512 -scale 3asec -weight briggs 0.5 -data-column DATA -field 0 -j 4 -temp-dir /data/$name/tmp \
    "$@" -name /data/$name/w /data/probe.ms > "$O/$name/log.txt" 2>&1
  rmdir "$O/$name/tmp" 2>/dev/null || true
}
run iq-join-fast -pol IQ -join-polarizations -niter 1 -gain 0.1
run iq-join-slow -pol IQ -join-polarizations -niter 1 -gain 0.1 -no-fast-subminor
run iquv-c2 -pol IQUV -channels-out 2 -niter 0 -make-psf
run iquv-c2-join -pol IQUV -channels-out 2 -join-channels -niter 0 -make-psf
run iquv-c2-joinpol -pol IQUV -channels-out 2 -join-channels -join-polarizations -niter 1 -make-psf
run iquv-c2-nomf -pol IQUV -channels-out 2 -join-channels -no-mf-weighting -niter 0 -make-psf
run iquv-c1 -pol IQUV -niter 0 -make-psf
run q-c1 -pol Q -niter 0 -make-psf
run i-c1 -pol I -niter 0 -make-psf
run xxyy -pol xx,yy -niter 0 -make-psf
echo done
