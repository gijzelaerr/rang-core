#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# W1 oracle run into a fresh directory (research/w1-writeback.md).
# Usage: bash tools/oracles/w1/run.sh /mnt/d/rang/w1/w1-20261106-NN
# Needs the worktree .venv and the images rang-o-casa:6.7.6.14,
# rang-ms-reader:local and rang-formats-oracle:20261030.
set -euo pipefail
root=$(cd "$(dirname "$0")/../../.." && pwd)
code="$root/tools/oracles/w1"
py="$root/.venv/bin/python"
ex="$root/examples/w1_writeback.py"
run=$(realpath -m "$1")
if [ -e "$run" ]; then echo "$run exists; choose a fresh run directory" >&2; exit 1; fi
mkdir -p "$run/timing" "$run/logs" "$run/out" "$run/wsclean"
declare -A src=(
  [m1]="$HOME/Github/rang/outputs/tv-caracal-wsl-20261029-01/original.ms"
  [m2]="$HOME/Github/rang/outputs/o-casa-20261030-01/c.ms"
)
declare -A field=([m1]=0 [m2]=1)

host() {  # host step, timed
  local name=$1; shift
  echo "## $name"
  /usr/bin/time -f "%e %M %x" -o "$run/timing/$name.txt" "$@" > "$run/logs/$name.log" 2>&1
}
ctr() {  # container step, timed inside the container
  local image=$1 name=$2; shift 2
  echo "## $name"
  docker run --rm --user "$(id -u):$(id -g)" --network none --entrypoint "" \
    --tmpfs /tmp -e HOME=/tmp -e OMP_NUM_THREADS=1 \
    -v "$code:/code:ro" -v "$run:/run" -w /run "$image" \
    /usr/bin/time -f "%e %M %x" -o "/run/timing/$name.txt" "$@" > "$run/logs/$name.log" 2>&1
}
casa() { local name=$1; shift; ctr rang-o-casa:6.7.6.14 "$name" /opt/casa/bin/python -I /code/oracle.py "$@"; }
cc37() { local name=$1; shift; ctr rang-o-casa:6.7.6.14 "$name" python3 -I /code/oracle.py "$@"; }
cc38() {  # this image has no /usr/bin/time: timed on the host, start-up included
  local name=$1; shift
  echo "## $name"
  /usr/bin/time -f "%e %M %x" -o "$run/timing/$name.txt" \
    docker run --rm --user "$(id -u):$(id -g)" --network none --entrypoint "" \
    --tmpfs /tmp -e HOME=/tmp -v "$code:/code:ro" -v "$run:/run" -w /run \
    rang-ms-reader:local python -I /code/oracle.py "$@" > "$run/logs/$name.log" 2>&1
}
dms() { local name=$1; shift; ctr rang-formats-oracle:20261030 "$name" /opt/qc/bin/python -I /code/oracle.py "$@"; }
cpms() { rm -rf "$2" "$2.flagversions"; cp -r "$1" "$2"; if [ -d "$1.flagversions" ]; then cp -r "$1.flagversions" "$2.flagversions"; fi; }
wsc() {  # WSClean dirty image of one column
  local m=$1 col=$2 ms=$3
  ctr rang-o-casa:6.7.6.14 "wsclean-$m-$col" wsclean -gridder wgridder -data-column "$col" \
    -size 512 512 -scale 2asec -weight natural -pol I -niter 0 -j 1 -field "${field[$m]}" \
    -no-update-model-required "${@:4}" -name "/run/wsclean/$m-$col" "/run/$ms"
}

date -u +%FT%TZ > "$run/started.txt"
git -C "$root" rev-parse HEAD > "$run/code-commit.txt"
git -C "$root" status --short > "$run/code-status.txt"
for m in m1 m2; do
  cp -r "${src[$m]}" "$run/$m-pristine.ms"
  cp -r "${src[$m]}" "$run/$m.ms"
  host "write-$m" "$py" "$ex" write "$run/$m.ms" "$run/out/$m-writes.npz"
  cc38 "casacore381-$m" casacore "/run/$m.ms" "/run/out/$m-writes.npz" "/run/$m-pristine.ms" "/run/out/$m-casacore381.json"
  cc37 "casacore371-$m" casacore "/run/$m.ms" "/run/out/$m-writes.npz" "/run/$m-pristine.ms" "/run/out/$m-casacore371.json"
  dms "daskms-$m" daskms "/run/$m.ms" "/run/out/$m-writes.npz" "/run/out/$m-daskms.json"
  casa "casa-list-$m" casa-list "/run/$m.ms" "/run/out/$m-casa-list.json"
  # CASA restores rang's backup.
  cpms "$run/$m.ms" "$run/$m-casarestore.ms"
  casa "casa-restore-$m" casa-flagmanager "/run/$m-casarestore.ms" restore rang_original "/run/out/$m-casa-restore.json"
  host "hash-casarestore-$m" "$py" "$ex" hashes "$run/$m-casarestore.ms" "$run/out/$m-casarestore-hashes.json"
  # rang restores a version CASA saved.
  cpms "$run/$m-pristine.ms" "$run/$m-casasave.ms"
  casa "casa-save-$m" casa-flagmanager "/run/$m-casasave.ms" save casa_v "/run/out/$m-casa-save.json"
  host "scramble-$m" "$py" "$ex" scramble "$run/$m-casasave.ms"
  host "rang-restore-casa-$m" "$py" "$ex" restore "$run/$m-casasave.ms" casa_v
  host "hash-casasave-$m" "$py" "$ex" hashes "$run/$m-casasave.ms" "$run/out/$m-casasave-hashes.json"
  # CASA reads the written columns through its own MS layer.
  for col in corrected model; do
    casa "casa-split-$m-$col" casa-split "/run/$m.ms" "$col" "/run/$m-split-$col.ms" "/run/out/$m-split-$col.json"
    cc37 "split-compare-$m-$col" split-compare "/run/$m.ms" "/run/$m-split-$col.ms" \
      "$( [ $col = corrected ] && echo CORRECTED_DATA || echo MODEL_DATA )" "/run/out/$m-split-compare-$col.json"
  done
  # CASA writes into the CORRECTED_DATA column (added by rang on m1).
  cpms "$run/$m.ms" "$run/$m-applycal.ms"
  casa "casa-applycal-$m" casa-applycal "/run/$m-applycal.ms" "/run/out/$m-applycal.json"
  cc37 "applycal-compare-$m" applycal-compare "/run/$m-applycal.ms" "/run/out/$m-applycal-compare.json"
  for col in DATA CORRECTED_DATA MODEL_DATA; do wsc "$m" "$col" "$m.ms"; done
  # Reported, not gated: QuartiCal 0.2.7 solves G with rang's CORRECTED_DATA
  # (= DATA) as data and MODEL_DATA (= 2 DATA) as model: |g| = 1/sqrt(2).
  cpms "$run/$m.ms" "$run/$m-qc.ms"
  ctr rang-formats-oracle:20261030 "quartical-$m" /opt/qc/bin/goquartical \
    input_ms.path="/run/$m-qc.ms" input_ms.data_column=CORRECTED_DATA \
    input_ms.weight_column=WEIGHT_SPECTRUM input_model.recipe=MODEL_DATA \
    solver.terms=[G] solver.iter_recipe=[50] G.type=diag_complex G.time_interval=0 \
    G.freq_interval=0 solver.robust=false mad_flags.enable=false output.flags=false \
    output.gain_directory="/run/qc-$m/gains.qc" output.log_directory="/run/qc-$m/logs" \
    dask.threads=1 solver.threads=1 dask.scheduler=single-threaded || echo "quartical-$m failed"
  dms "qc-gains-$m" qc-gains "/run/qc-$m/gains.qc" "/run/out/$m-qc-gains.json" || echo "qc-gains-$m failed"
done
# The columns as initialised (MODEL_DATA a unit point at the phase centre).
cp -r "${src[m1]}" "$run/m1u.ms"
host columns-m1u "$py" "$ex" columns "$run/m1u.ms"
field[m1u]=0
wsc m1u MODEL_DATA m1u.ms
wsc m1u DATA m1u.ms -make-psf  # the PSF: a post-hoc check, not gated
# M0 (from run -02): an MS written by the core writer without
# WEIGHT_SPECTRUM, so the added-and-initialised path is read by the
# oracles (casacore and dask-ms; CASA and WSClean need real subtables).
host make-m0 "$py" "$ex" make "$run/m0.ms" 300 64 --flag tiled --seed 20261106
cp -r "$run/m0.ms" "$run/m0-pristine.ms"
host write-m0 "$py" "$ex" write "$run/m0.ms" "$run/out/m0-writes.npz" --no-weights
cc38 casacore381-m0 casacore /run/m0.ms /run/out/m0-writes.npz /run/m0-pristine.ms /run/out/m0-casacore381.json
cc37 casacore371-m0 casacore /run/m0.ms /run/out/m0-writes.npz /run/m0-pristine.ms /run/out/m0-casacore371.json
dms daskms-m0 daskms /run/m0.ms /run/out/m0-writes.npz /run/out/m0-daskms.json
host compare "$py" "$code/compare.py" "$run"
date -u +%FT%TZ > "$run/finished.txt"
