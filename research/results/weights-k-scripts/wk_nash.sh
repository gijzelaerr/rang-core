#!/bin/bash
# weights-k (#48 research/weights-48.md, #60 research/k-fallback-60.md): nash shards with
# done-markers. Every job nice 19 + ionice -c3 through the main checkout's heavy lock.
#   bash wk_nash.sh build        # venv and extension of the nash worktree
#   bash wk_nash.sh A|B|C        # copy, flags, calibrate (and apply for A, B) of one arm
#   bash wk_nash.sh c4           # katdal venv, --chanbin 4 conversion, flag+calibrate+apply
set -euo pipefail
WT=$HOME/Worktrees/rang/weights-k
PY=$WT/.venv/bin/python
S=$WT/research/results/weights-k-scripts
SRC=$HOME/rang-data/outputs/e2n-20261116
R=$HOME/rang-data/outputs/weights-k-20261125
source "$HOME/.rang-env.sh"
LOCK="python3 $HOME/Github/rang/tools/heavy_lock.py run"
NICE="nice -n 19 ionice -c3"
mkdir -p "$R/logs" "$R/cfg"
log() { echo "$(date -Is) $*" >> "$R/logs/driver.log"; }
shard() { [ -e "$R/done.$1" ]; }
mark() { touch "$R/done.$1"; log "$1 done"; }

cfg() {
  shard cfg && return
  cp "$WT/research/results/e2n-scripts/e2n.yaml" \
     "$WT/research/results/e2n-scripts/mk_rfi_flagging_calibrator_fields_firstpass.yaml" "$R/cfg/"
  # A and B: calibrate and apply (E2-N's frozen configuration otherwise)
  sed 's/^  stages: \[flag, calibrate, apply, image, selfcal\]$/  stages: [calibrate, apply]/' \
    "$R/cfg/e2n.yaml" > "$R/cfg/e2n-ca.yaml"
  grep -q '^  stages: \[calibrate, apply\]$' "$R/cfg/e2n-ca.yaml"
  grep -q '^  calwt: false$' "$R/cfg/e2n-ca.yaml"
  sed 's/^  calwt: false$/  calwt: true/' "$R/cfg/e2n-ca.yaml" > "$R/cfg/e2n-ca-calwt.yaml"
  grep -q '^  calwt: true$' "$R/cfg/e2n-ca-calwt.yaml"
  # C: calibrate only, refantmode strict
  sed -e 's/^  stages: \[calibrate, apply\]$/  stages: [calibrate]/' \
      -e 's/^  refant: auto$/  refant: auto\n  refantmode: strict/' "$R/cfg/e2n-ca.yaml" > "$R/cfg/e2n-c-strict.yaml"
  grep -q '^  refantmode: strict$' "$R/cfg/e2n-c-strict.yaml"
  # c4: flag, calibrate, apply on the --chanbin 4 conversion
  sed 's/^  stages: \[flag, calibrate, apply, image, selfcal\]$/  stages: [flag, calibrate, apply]/' \
    "$R/cfg/e2n.yaml" > "$R/cfg/e2n-c4.yaml"
  grep -q '^  stages: \[flag, calibrate, apply\]$' "$R/cfg/e2n-c4.yaml"
  sed 's/^  calwt: false$/  calwt: true/' "$R/cfg/e2n-c4.yaml" > "$R/cfg/e2n-c4-calwt.yaml"
  sha256sum "$R/cfg/"* > "$R/done.cfg"
}

case "${1:-}" in
build)
  if ! shard build; then
    log "build start"
    cd "$WT"
    [ -x "$PY" ] || uv venv -q .venv
    uv pip install -q --python "$PY" -e '.[test,imaging,casacure]' maturin
    $LOCK --slots 8 --mem 8 -- $NICE env CARGO_TARGET_DIR="$WT/target" \
      "$WT/.venv/bin/maturin" develop --release --offline -m core/py/Cargo.toml > "$R/logs/build.log" 2>&1
    "$PY" -c "import rang, rang._core; print(rang.__file__)" >> "$R/logs/build.log"
    mark build
  fi ;;
A|B|C)
  arm=$1; cfg
  D=$R/$arm
  if ! shard copy$arm; then
    log "copy$arm start"; rm -rf "$D"; mkdir -p "$D"
    $LOCK --slots 1 --mem 2 -- $NICE cp -a "$SRC/e2n.ms" "$SRC/e2n.ms.flagversions" "$D/"
    mark copy$arm
  fi
  if ! shard prep$arm; then
    p=$arm; [ "$arm" = C ] && p=B
    $LOCK --slots 1 --mem 8 -- $NICE "$PY" -I "$S/k60_prep.py" "$D/e2n.ms" "$p" "$R/prep-$arm.json" \
      > "$R/logs/prep-$arm.log" 2>&1
    mark prep$arm
  fi
  if ! shard run$arm; then
    c=$R/cfg/e2n-ca.yaml; [ "$arm" = C ] && c=$R/cfg/e2n-c-strict.yaml
    log "run$arm start"
    $LOCK --slots 6 --mem 24 -- $NICE env RAYON_NUM_THREADS=6 /usr/bin/time -v -o "$R/logs/run$arm.time" \
      "$PY" -m rang.core_cli run "$c" "$D/e2n.ms" > "$R/logs/run$arm.log" 2>&1
    mark run$arm
  fi ;;
c4)
  cfg
  D=$R/c4; V=$HOME/Build/tmp/20261125-weights-k/katdal
  if ! shard katdal; then
    mkdir -p "$(dirname "$V")"; uv venv -q --python 3.12 "$V"
    uv pip install -q --python "$V/bin/python" katdal
    mark katdal
  fi
  if ! shard convert; then
    log "convert start"; rm -rf "$D"; mkdir -p "$D"
    RDB=$SRC/mvf/1735268787/1735268787_sdp_l0.full.rdb
    $LOCK --slots 4 --mem 32 -- $NICE /usr/bin/time -v -o "$R/logs/convert.time" \
      "$V/bin/python" "$V/bin/mvftoms.py" -f -a --chanbin 4 \
      --flags static,cam,data_lost,ingest_rfi,predicted_rfi \
      --scans 1,3,5,9,13,15,17,19,21,23,25,29,33,35 -o "$D/e2n-c4.ms" "$RDB" > "$R/logs/convert.log" 2>&1
    grep -c "token=" "$R/logs/convert.log" | sed 's/^/token lines in log: /' >> "$R/logs/convert.log" || true
    mark convert
  fi
  if ! shard runc4; then
    log "runc4 start"
    $LOCK --slots 6 --mem 24 -- $NICE env RAYON_NUM_THREADS=6 /usr/bin/time -v -o "$R/logs/runc4.time" \
      "$PY" -m rang.core_cli run "$R/cfg/e2n-c4.yaml" "$D/e2n-c4.ms" > "$R/logs/runc4.log" 2>&1
    mark runc4
  fi ;;
k60score)
  shard runA && shard runB && shard runC || { echo "arms not done"; exit 1; }
  $LOCK --slots 1 --mem 8 -- $NICE "$PY" -I "$S/k60_score.py" "$R"     "$WT/research/results/e2n-followup/rerun/fu-kcompare.json" "$R/k60-score.json" > "$R/logs/k60score.log" 2>&1
  mark k60score ;;
w48A|w48c4)
  # #48 held-out arms (research/weights-48.md section 4) on arm A's MS or on c4's.
  if [ "$1" = w48A ]; then M=$R/A/e2n.ms; RAW=$SRC/e2n.ms; CB=16; CW=$R/cfg/e2n-ca-calwt.yaml; O=$R/w48/A
  else M=$R/c4/e2n-c4.ms; RAW=$M; CB=4; CW=$R/cfg/e2n-c4-calwt.yaml; O=$R/w48/c4; fi
  need=runA; [ "$1" = w48c4 ] && need=runc4
  shard $need || { echo "$need not done"; exit 1; }
  mkdir -p "$O"
  W="$LOCK --slots 4 --mem 48 -- $NICE env RAYON_NUM_THREADS=4 $PY -I $S/w48_real.py"
  for F in J1744-5144 J0408-6545 ASKAPJ1745; do
    for arm in raw unity rmad rclip; do
      tag=$1.$F.$arm
      shard $tag && continue
      $W weights "$M" "$RAW" $F $arm "$O/$F-$arm-weights.json" $CB > "$O/$F-$arm.log" 2>&1
      $W n "$M" $F "$O/$F-$arm-n.json" $CB >> "$O/$F-$arm.log" 2>&1
      $W image "$M" $F "$O/$F-$arm-img" 4 >> "$O/$F-$arm.log" 2>&1
      if [ $F = ASKAPJ1745 ]; then
        if [ $arm = raw ]; then
          $LOCK --slots 4 --mem 32 -- $NICE "$PY" -m rang.gemclean -name "$O/i-raw" -field $F -pol I             -weight natural -niter 0 -size 2048 2048 -scale 3asec -no-update-model-required -j 4 "$M"             >> "$O/$F-$arm.log" 2>&1
          "$PY" -I "$S/w48_real.py" sources "$O/i-raw-dirty.fits" "$M" $F "$O/sources.csv" >> "$O/$F-$arm.log" 2>&1
        fi
        $W lc "$M" $F "$O/sources.csv" "$O/$F-$arm-lc" >> "$O/$F-$arm.log" 2>&1 || true
      fi
      mark $tag
    done
  done
  if ! shard $1.applycalwt; then
    $LOCK --slots 6 --mem 24 -- $NICE env RAYON_NUM_THREADS=6 /usr/bin/time -v -o "$R/logs/$1-calwt.time"       "$PY" -m rang.core_cli run --force apply "$CW" "$M" > "$O/applycalwt.log" 2>&1
    mark $1.applycalwt
  fi
  for F in J1744-5144 J0408-6545 ASKAPJ1745; do
    tag=$1.$F.calwt; shard $tag && continue
    $W weights "$M" "$RAW" $F calwt "$O/$F-calwt-weights.json" $CB > "$O/$F-calwt.log" 2>&1
    $W n "$M" $F "$O/$F-calwt-n.json" $CB >> "$O/$F-calwt.log" 2>&1
    $W image "$M" $F "$O/$F-calwt-img" 4 >> "$O/$F-calwt.log" 2>&1
    [ $F = ASKAPJ1745 ] && { $W lc "$M" $F "$O/sources.csv" "$O/$F-calwt-lc" >> "$O/$F-calwt.log" 2>&1 || true; }
    mark $tag
  done ;;
*) echo "usage: wk_nash.sh build|A|B|C|c4|k60score|w48A|w48c4"; exit 2 ;;
esac
log "$1 finished"
