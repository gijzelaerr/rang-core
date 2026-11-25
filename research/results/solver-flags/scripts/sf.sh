#!/bin/bash
# solver-flags (#58, #59), research/solver-flags.md section 7: shards with done-markers on nash.
#   bash sf.sh setup | qcvenv | e2n ARM | a1-gen | a1 ARM | oracle | score
set -euo pipefail
WT=${SF_WT:-$HOME/Worktrees/rang/solver-flags}  # arm R runs from its own frozen worktree
PY=$WT/.venv/bin/python
S=$WT/research/results/solver-flags/scripts
SRC=$HOME/rang-data/outputs/e2n-20261116
R=$HOME/rang-data/outputs/solver-flags-20261125
QC=$HOME/Build/tmp/20261125-solver-flags/venv-qc027
source "$HOME/.rang-env.sh"
LOCK="python3 $HOME/Github/rang/tools/heavy_lock.py run"
NICE="nice -n 19 ionice -c3"
mkdir -p "$R/logs" "$R/cfg"
log() { echo "$(date -Is) $*" >> "$R/logs/driver.log"; }
shard() { [ -e "$R/done.$1" ]; }
mark() { touch "$R/done.$1"; log "$1 done"; }
ARM=${2:-}

case ${1:-} in
setup)
  # Rebuilt for every code change: the marker is the commit.
  head=$(basename "$WT")-$(git -C "$WT" rev-parse --short HEAD)
  if ! shard "setup-$head"; then
    cd "$WT"
    [ -x .venv/bin/python ] || uv venv -q -p 3.12 .venv
    $NICE uv pip install -q -p .venv/bin/python --index-url https://pypi.org/simple maturin numpy scipy astropy pyyaml
    $LOCK --slots 8 --mem 16 -- $NICE env CARGO_BUILD_JOBS=8 bash -c \
      "cd $WT && VIRTUAL_ENV=$WT/.venv $WT/.venv/bin/maturin develop --release -q" > "$R/logs/build-$head.log" 2>&1
    "$PY" -c "import rang; print(rang.__file__)" >> "$R/logs/build-$head.log"
    mark "setup-$head"
  fi
  ;;
qcvenv)
  if ! shard qcvenv; then
    mkdir -p "$(dirname "$QC")"
    uv venv -q -p 3.12 "$QC"
    $NICE uv pip install -q -p "$QC/bin/python" --index-url https://pypi.org/simple "quartical==0.2.7" > "$R/logs/qcvenv.log" 2>&1
    "$QC/bin/python" -c "import quartical, importlib.metadata as m; print(m.version('quartical'))" >> "$R/logs/qcvenv.log"
    mark qcvenv
  fi
  ;;
e2n)
  ms=$R/e2n-$ARM.ms
  if ! shard "copy-$ARM"; then
    rm -rf "$ms" "$ms.flagversions"
    $LOCK --slots 1 --mem 2 -- $NICE bash -c "cp -a $SRC/e2n.ms $ms && cp -a $SRC/e2n.ms.flagversions $ms.flagversions"
    $NICE "$PY" "$WT/research/results/dl0-profile/scripts/dl0_restore.py" "$ms" \
      rang_flag_20261117T015729Z "$R/restore-$ARM.json"
    mark "copy-$ARM"
  fi
  if ! shard "cfg-$ARM"; then
    cp "$WT/research/results/e2n-scripts/e2n.yaml" "$WT/research/results/e2n-scripts/mk_rfi_flagging_calibrator_fields_firstpass.yaml" "$R/cfg/"
    [ "$ARM" = R ] || cp "$S/../mk_rfi_flagging_mild.yaml" "$R/cfg/"
    "$PY" -I "$S/sf_cfg.py" "$R/cfg/e2n.yaml" "$R/cfg/e2n-$ARM.yaml" "$ARM"
    mark "cfg-$ARM"
  fi
  if ! shard "run-$ARM"; then
    log "run-$ARM start $(git -C "$WT" rev-parse --short HEAD)"
    $LOCK --slots 3 --mem 32 -- $NICE env RAYON_NUM_THREADS=3 /usr/bin/time -v -o "$R/logs/run-$ARM.time" \
      "$PY" -m rang.core_cli run "$R/cfg/e2n-$ARM.yaml" "$ms" > "$R/logs/run-$ARM.log" 2>&1
    grep -q "apply: done" "$R/logs/run-$ARM.log" && mark "run-$ARM"
  fi
  ;;
a1-gen)
  A=$R/a1
  mkdir -p "$A"
  if ! shard a1-gen; then
    $LOCK --slots 8 --mem 24 -- $NICE /usr/bin/time -v -o "$R/logs/a1-gen.time" \
      "$PY" -m rang.simtruth_ms generate full "$A/gen" --workers 8 > "$R/logs/a1-gen.log" 2>&1
    mark a1-gen
  fi
  ;;
a1)
  A=$R/a1
  if ! shard "a1-cfg-$ARM"; then
    cp "$WT/research/results/e1-chain-scripts/e1_config.yaml" "$A/e1.yaml"
    cp "$WT/research/results/e2n-scripts/mk_rfi_flagging_calibrator_fields_firstpass.yaml" "$A/"
    [ "$ARM" = R ] || cp "$S/../mk_rfi_flagging_mild.yaml" "$A/"
    # A1 full's flux-calibrator interval needs 9.4 GiB (flag-residual): 24, inside the 32 GB booking.
    "$PY" -I "$S/sf_cfg.py" "$A/e1.yaml" "$A/a1-$ARM.yaml" "$ARM" 24
    mark "a1-cfg-$ARM"
  fi
  if ! shard "a1-copy-$ARM"; then
    rm -rf "$A/a1-$ARM.ms"; $NICE cp -a "$A/gen/a1-full.ms" "$A/a1-$ARM.ms"; mark "a1-copy-$ARM"
  fi
  if ! shard "a1-run-$ARM"; then
    log "a1-run-$ARM start $(git -C "$WT" rev-parse --short HEAD)"
    $LOCK --slots 2 --mem 32 -- $NICE env RAYON_NUM_THREADS=2 /usr/bin/time -v -o "$R/logs/a1-run-$ARM.time" \
      "$PY" -m rang.core_cli run "$A/a1-$ARM.yaml" "$A/a1-$ARM.ms" > "$R/logs/a1-run-$ARM.log" 2>&1
    grep -q "apply: done" "$R/logs/a1-run-$ARM.log" && mark "a1-run-$ARM"
  fi
  ;;
*) echo "usage: sf.sh setup|qcvenv|e2n ARM|a1-gen|a1 ARM" >&2; exit 2;;
esac
