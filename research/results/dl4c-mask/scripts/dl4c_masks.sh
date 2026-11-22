#!/bin/bash
# DL4c section 9 step 4: the masks of arms P (R cases) and T (T cases), from finished A images.
#   bash dl4c_masks.sh R1 R2 T1 ...
# T masks: the bench scorer's pixelised truth (`truth` subcommand) convolved with A's beam, cut at
# 5 x the simulator's Briggs image rms (prep meta noise.briggs_image_rms; the images use Briggs 0.5).
set -euo pipefail
WT=$HOME/Worktrees/rang/dl4c-mask
PY=$WT/.venv/bin/python
S=$WT/research/results/dl4c-mask/scripts
R=$HOME/rang-data/outputs/dl4c-mask-20261120
source "$HOME/.rang-env.sh"
LOCK="python3 $HOME/Github/rang/tools/heavy_lock.py run"
NICE="nice -n 19 ionice -c3"
mkdir -p "$R/masks" "$R/truth"
for c in "$@"; do
  a=$R/img/$c-A
  [ -e "$a/done" ] || { echo "$c: A not done" >&2; continue; }
  case $c in
    R*) out=$R/masks/$c-P
        [ -e "$out.json" ] || $LOCK --slots 1 --mem 8 -- $NICE "$PY" -I "$S/dl4c_mask.py" posterior "$a" "$out.fits" "$out.json";;
    T*) t=$R/truth/$c; out=$R/masks/$c-T
        if [ ! -e "$t/done" ]; then
          mkdir -p "$t"
          $LOCK --slots 4 --mem 24 -- $NICE env RAYON_NUM_THREADS=4 "$PY" -I "$WT/examples/gemclean_bench_compare.py" \
            truth "$R/prep/$c/out" "$R/sim/$c/catalogue.json" "$t" --name truth > "$t/truth.log" 2>&1
          touch "$t/done"
        fi
        noise=$("$PY" -I -c "import json,sys; print(json.load(open(sys.argv[1]))['noise']['briggs_image_rms'])" "$R/prep/$c/out/meta.json")
        [ -e "$out.json" ] || $LOCK --slots 1 --mem 8 -- $NICE "$PY" -I "$S/dl4c_mask.py" truth "$a" "$t/truth-model.fits" "$noise" "$out.fits" "$out.json";;
  esac
done
