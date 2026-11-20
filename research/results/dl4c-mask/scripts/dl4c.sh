#!/bin/bash
# DL4c (#43), research/dl4c-mask.md: shards with done-markers on nash.
#
#   bash dl4c.sh sim T1|T2|T3        # one simulated case (section 3)
#   bash dl4c.sh prep T1|T2|T3       # the bench scorer's prepare step (truth, noise)
#   bash dl4c.sh image CASE ARM      # one GeMClean image; CASE R1-R3, T1-T3; ARM A, P, T
#
# A rerun skips a shard whose done-marker exists. Each image is one process
# (not checkpointable; an interrupted image is rerun from the start).
set -euo pipefail
WT=$HOME/Worktrees/rang/dl4c-mask
PY=$WT/.venv/bin/python
R=$HOME/rang-data/outputs/dl4c-mask-20261120
source "$HOME/.rang-env.sh"
LOCK="python3 $HOME/Github/rang/tools/heavy_lock.py run"
NICE="nice -n 19 ionice -c3"
mkdir -p "$R/logs"
log() { echo "$(date -Is) $*" >> "$R/logs/driver.log"; }

dec_of() { case $1 in T1) echo -45;; T2) echo -30;; T3) echo -60;; esac; }
sky_seed() { case $1 in T1) echo 20262001;; T2) echo 20262002;; T3) echo 20262003;; esac; }
noise_seed() { case $1 in T1) echo 20262011;; T2) echo 20262012;; T3) echo 20262013;; esac; }
scan_of() { case $1 in R1) echo 6;; R2) echo 8;; R3) echo 10;; esac; }

cmd=$1; shift
case $cmd in
sim)
  c=$1; d=$R/sim/$c; mkdir -p "$d"
  [ -e "$d/done" ] && exit 0
  log "sim $c start"
  $LOCK --slots 4 --mem 16 -- $NICE /usr/bin/time -v -o "$d/time.txt" \
    "$PY" -I "$WT/examples/gemclean_bench_simulate.py" "$d/sim.ms" --sky H4 \
      --dec "$(dec_of "$c")" --sky-seed "$(sky_seed "$c")" --noise-seed "$(noise_seed "$c")" \
      --size 4096 --scale 3 --nchan 64 --fmin 0.856e9 --fmax 1.712e9 --hours 2 --dt 8 \
      --nant 64 --noise-ujy 20 --catalogue "$d/catalogue.json" --noise-out "$d/noise.c64" \
      > "$d/sim.log" 2>&1
  touch "$d/done"; log "sim $c done"
  ;;
prep)
  c=$1; d=$R/sim/$c; p=$R/prep/$c; mkdir -p "$p"
  [ -e "$p/done" ] && exit 0
  log "prep $c start"
  $LOCK --slots 4 --mem 32 -- $NICE /usr/bin/time -v -o "$p/time.txt" \
    "$PY" -I "$WT/examples/gemclean_bench_compare.py" prepare "$d/sim.ms" "$d/catalogue.json" "$p" \
      --size 4096 --scale 3 --noise "$d/noise.c64" > "$p/prep.log" 2>&1
  touch "$p/done"; log "prep $c done"
  ;;
image)
  c=$1; a=$2; d=$R/img/$c-$a; mkdir -p "$d"
  [ -e "$d/done" ] && exit 0
  case $c in
    R*) ms=$R/e2n.ms; sel=(-average-channels 2 -data-column CORRECTED_DATA -field 3 -scans "$(scan_of "$c")");;
    T*) ms=$R/sim/$c/sim.ms; sel=(-data-column DATA -field 0);;
  esac
  case $a in
    A) mask=(-auto-mask 5.0);;
    P|T) mask=(-fits-mask "$R/masks/$c-$a.fits")
         [ -e "$R/masks/$c-$a.fits" ] || { echo "no mask for $c-$a" >&2; exit 2; };;
  esac
  log "image $c $a start"
  $LOCK --slots 8 --mem 48 -- $NICE env RAYON_NUM_THREADS=8 /usr/bin/time -v -o "$d/time.txt" \
    "$PY" -m rang.gemclean -name "$d/image" -j 8 -size 4096 4096 -scale 3asec \
      -weight briggs 0.5 -niter 1000000 -mgain 0.9 -auto-threshold 3.0 -wgridder-accuracy 0.0001 \
      -channels-out 8 -join-channels -fit-spectral-pol 2 -multiscale -unit-weights \
      -no-update-model-required "${sel[@]}" "${mask[@]}" "$ms" > "$d/gemclean.log" 2>&1
  touch "$d/done"; log "image $c $a done"
  ;;
*) echo "unknown $cmd" >&2; exit 2;;
esac
