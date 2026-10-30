#!/usr/bin/env bash
# WSClean 3.7 reference images for the certified CLEAN comparison
# (research/clean-certified-imaging.md). Runs inside the O-CASA image
# (rang-o-casa:6.7.6.14, WSClean 3.7), one thread, no network, on a private
# copy of O-CASA run -01's calibrated c.ms (WSClean writes MODEL_DATA when it
# cleans; the O-CASA copy is never touched).
#
# Usage: bash examples/clean_certified_wsclean.sh RUN_DIR [image]
#   RUN_DIR must not exist. Each job writes RUN_DIR/<name>-*.fits,
#   RUN_DIR/<name>.log and RUN_DIR/timing/<name>.txt ("wall_s max_rss_kb exit").
set -euo pipefail
root=$(cd "$(dirname "$0")/.." && pwd)
run=$(realpath -m "$1")
image=${2:-rang-o-casa:6.7.6.14}
src=${CLEAN_CERTIFIED_MS:-/home/gijsm/Github/rang/outputs/o-casa-20261030-01/c.ms}
mkdir "$run" "$run/timing"
cp -r "$src" "$run/c.ms"

common=(-gridder wgridder -data-column CORRECTED_DATA -field 1 -size 512 512 -scale 8asec
  -weight briggs 0.5 -pol I -j 1)

wsc() {  # wsc <name> <extra wsclean args...>
  local name=$1; shift
  docker run --rm --user "$(id -u):$(id -g)" --network none --tmpfs /tmp -e HOME=/tmp \
    -e OMP_NUM_THREADS=1 -v "$run:/run" -w /run "$image" \
    /usr/bin/time -f "%e %M %x" -o "/run/timing/$name.txt" \
    wsclean "${common[@]}" "$@" -name "/run/$name" /run/c.ms > "$run/$name.log" 2>&1
}

# Dirty images: the recorded O-CASA setting (reproduces r1-*.fits), then
# without WSClean's minimum-grid-resolution upsampling, then also at the
# wgridder's highest documented accuracy.
wsc d-recorded -niter 0 -make-psf
wsc d-nominres -niter 0 -make-psf -no-min-grid-resolution
wsc d-nominres-acc6 -niter 0 -make-psf -no-min-grid-resolution -wgridder-accuracy 1e-6

# CLEAN references (settings chosen for this study, research note §3):
# Högbom-type minor loop, gain 0.1, mgain 0.8, absolute threshold, no mask,
# major-cycle limit lifted, exact settings matched by the rang driver.
threshold=${CLEAN_CERTIFIED_THRESHOLD:-0.05}
niter=${CLEAN_CERTIFIED_NITER:-100000}
# "fast" is WSClean's default sub-minor loop, "hogbom" its plain minor loop
# (-no-fast-subminor), which subtracts the image-size PSF at every step.
for variant in recorded nominres; do
  for loop in fast hogbom; do
    extra=()
    [ "$variant" = nominres ] && extra+=(-no-min-grid-resolution -wgridder-accuracy 1e-6)
    [ "$loop" = hogbom ] && extra+=(-no-fast-subminor)
    wsc "c-$variant-$loop" -niter "$niter" -gain 0.1 -mgain 0.8 -nmiter 0 \
      -abs-threshold "$threshold" -no-update-model-required "${extra[@]}"
  done
done
echo "## done $run"
