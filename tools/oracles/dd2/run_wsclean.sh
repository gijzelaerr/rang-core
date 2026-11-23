#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
# DD2 oracle (research/dd2-facet-imaging.md, section 4): WSClean 3.7
# (rang-wsclean-native:3.7) predict and image with -facet-regions and
# -apply-facet-solutions on rang's H5parms; controls C0-C2, arms P and I.
# Usage (WSL): bash tools/oracles/dd2/run_wsclean.sh SIMDIR RUN SCRATCH
#   SIMDIR   DD1's simulation (dd1.ms)        e.g. /mnt/d/rang/outputs/dd1-20261123-01
#   RUN      DD2's run (prepare's outputs)    e.g. /mnt/d/rang/outputs/dd2-20261123-01
#   SCRATCH  a fresh directory on WSL's ext4  (MS copies)
# MODEL_DATA of each predict is exported as RUN/wsc/predict-<case>.npy with
# python-casacore from QC_VENV (DD1's QuartiCal venv).
set -euo pipefail
sim=$(realpath -m "$1"); run=$(realpath -m "$2"); scratch=$(realpath -m "$3")
venv=${QC_VENV:-$HOME/Build/tmp/20261123-dd15/venv-qc027}
image=rang-wsclean-native:3.7
if [ -e "$scratch" ]; then echo "$scratch exists; choose a fresh directory" >&2; exit 1; fi
mkdir -p "$scratch" "$run/wsc/timing" "$run/wsc/logs"
cp "$run/model.fits" "$scratch/model.fits"
cp "$run/facets.reg" "$scratch/facets.reg"
cp -r "$run/h5" "$scratch/h5"
docker run --rm --entrypoint "" "$image" cat /wsclean-commit.txt > "$run/wsc/wsclean-commit.txt"
common=(-gridder wgridder -wgridder-accuracy 1e-6 -size 3200 3200 -scale 3asec -pol I -j 8)
facets() { echo -facet-regions /w/facets.reg -apply-facet-solutions "/w/h5/$1.h5" amplitude000,phase000; }
wsc() {  # name, args...
  local name=$1; shift
  echo "## $name"
  docker run --rm --user "$(id -u):$(id -g)" --network none --entrypoint "" \
    -v "$scratch:/w" -w /w "$image" \
    /usr/bin/time -f "%e %M %x" -o "/w/time-$name.txt" wsclean "$@" > "$run/wsc/logs/$name.log" 2>&1
  cp "$scratch/time-$name.txt" "$run/wsc/timing/$name.txt"
}
export_model() {  # case
  "$venv/bin/python" -I -c "
import sys, numpy as np, casacore.tables as pt
t = pt.table(sys.argv[1], ack=False); np.save(sys.argv[2], t.getcol('MODEL_DATA')); t.close()
" "$scratch/$1.ms" "$run/wsc/predict-$1.npy"
}
date -u +%FT%TZ > "$run/wsc/started.txt"
# Predicts: one MS copy each (MODEL_DATA is written in place).
for case in C0 C1 P; do
  cp -r "$sim/dd1.ms" "$scratch/$case.ms"
  cp "$scratch/model.fits" "$scratch/pred-$case-model.fits"
  # With facet solutions WSClean 3.7 predicts from the flat-gain model <name>-model-pb.fits (amendment A1).
  cp "$scratch/model.fits" "$scratch/pred-$case-model-pb.fits"
  case $case in
    C0) extra=() ;;
    C1) read -ra extra <<< "$(facets unit)" ;;
    P)  read -ra extra <<< "$(facets solved)" ;;
  esac
  wsc "predict-$case" -predict -name "/w/pred-$case" "${common[@]}" "${extra[@]}" "/w/$case.ms"
  export_model "$case"
  rm -rf "$scratch/$case.ms"
done
# Images (niter 0) of DATA on one copy.
cp -r "$sim/dd1.ms" "$scratch/img.ms"
for case in C0 C1 C2 I; do
  case $case in
    C0) extra=() ;;
    C1) read -ra extra <<< "$(facets unit)" ;;
    C2) read -ra extra <<< "$(facets c2)" ;;
    I)  read -ra extra <<< "$(facets solved)" ;;
  esac
  wsc "image-$case" -name "/w/img-$case" "${common[@]}" -weight natural -niter 0 \
    -data-column DATA -no-update-model-required "${extra[@]}" /w/img.ms
  cp "$scratch/img-$case-dirty.fits" "$run/wsc/image-$case-dirty.fits"
  cp "$scratch/img-$case-image.fits" "$run/wsc/image-$case-image.fits"
  if [ -e "$scratch/img-$case-image-pb.fits" ]; then cp "$scratch/img-$case-image-pb.fits" "$run/wsc/image-$case-image-pb.fits"; fi
done
date -u +%FT%TZ > "$run/wsc/finished.txt"
