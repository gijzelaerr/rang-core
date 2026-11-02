#!/usr/bin/env bash
# Run the gmclean benchmark matrix for one imager (research/gmclean-benchmark.md).
#
# Usage:
#   bash examples/gmclean_bench_run.sh IMAGER RUN_DIR [DATASET ...]
#
#   IMAGER   wsclean (WSClean 3.7 in rang-o-casa:6.7.6.14, built-in command)
#            or any other name, with BENCH_TEMPLATE set to its command line
#   RUN_DIR  created if missing; jobs already finished there are skipped
#   DATASET  s1 s2 s3 slice (default: all four)
#
# Environment (all optional):
#   BENCH_DATA      directory holding s1.ms s2.ms s3.ms slice.ms
#                   (default outputs/gmclean-bench-20261102/data)
#   BENCH_THREADS   thread counts, default "16 1"
#   BENCH_MODES     threshold settings, default "auto abs"
#   BENCH_GRIDS     gridding variants, default "minres nominres pad2"
#   BENCH_LOOPS     minor loops, default "fast hogbom"
#   BENCH_FILTER    extended regex; only job names matching it run
#   BENCH_TEMPLATE  command line for a non-WSClean imager, with placeholders
#                   {ms} {datacol} {field} {size} {scale} {threads} {mode}
#                   {abs_threshold} {grid} {loop} {out} {niter}
#                   It must write {out}-model.fits and {out}-residual.fits
#                   in WSClean's FITS orientation (and may write
#                   {out}-image.fits and {out}-report.json). It runs on the
#                   host under /usr/bin/time -v. Example for gmclean (the CLI
#                   is assumed, adapt it to the binary):
#     BENCH_TEMPLATE='/home/gijsm/Worktrees/rang/gmclean-build/core/target/release/gmclean
#       --ms {ms} --data-column {datacol} --field {field} --size {size}
#       --scale-arcsec {scale} --weight briggs --robust 0.5 --gain 0.1 --mgain 0.8
#       --threshold-mode {mode} --abs-threshold {abs_threshold} --auto-threshold 3
#       --auto-mask 5 --threads {threads} --out {out}'
#
# Job name: <dataset>-<mode>-<grid>-<loop>-j<threads>. Per job the run
# directory gets <name>-*.fits, <name>.log, timing/<name>.txt (GNU time -v),
# load/<name>.txt (/proc/loadavg before and after) and jobs.tsv
# (name, exit, wall_s, start ISO time). The Measurement Sets are copied into
# RUN_DIR/ms once; their main-table SHA-256s are recorded before and after
# (ms-sha256-{before,after}.txt) so that a write by the imager shows.
# Settings common to every job: Briggs 0.5, gain 0.1, mgain 0.8, niter 1e6,
# no major-cycle limit (-nmiter 0), Stokes I, wgridder; "auto" is
# -auto-threshold 3 -auto-mask 5, "abs" is -abs-threshold (per dataset
# below); "minres" is WSClean's default minimum grid resolution, "nominres"
# adds -no-min-grid-resolution -wgridder-accuracy 1e-6, "pad2" adds
# -padding 2 to nominres; "hogbom" is -no-fast-subminor. BENCH_MODES=dirty
# (with BENCH_LOOPS=fast) makes the -niter 0 -make-psf dirty images and PSFs
# used to verify the datasets.
set -euo pipefail
root=$(cd "$(dirname "$0")/.." && pwd)
imager=$1
run=$(realpath -m "$2")
shift 2
datasets=("$@")
[ ${#datasets[@]} -eq 0 ] && datasets=(s1 s2 s3 slice)
data=$(realpath -m "${BENCH_DATA:-$root/outputs/gmclean-bench-20261102/data}")
image=rang-o-casa:6.7.6.14
threads_list=${BENCH_THREADS:-"16 1"}
modes=${BENCH_MODES:-"auto abs"}
grids=${BENCH_GRIDS:-"minres nominres pad2"}
loops=${BENCH_LOOPS:-"fast hogbom"}
filter=${BENCH_FILTER:-.}
niter=1000000
if [ "$imager" != wsclean ] && [ -z "${BENCH_TEMPLATE:-}" ]; then
  echo "BENCH_TEMPLATE is required for imager $imager" >&2
  exit 2
fi
mkdir -p "$run/ms" "$run/timing" "$run/load" "$run/tmp"
[ -f "$run/jobs.tsv" ] || printf 'name\texit\twall_s\tstart\n' > "$run/jobs.tsv"

settings() {  # settings <dataset>: sets size scale datacol field abs
  case $1 in
    slice) size=512; scale=8; datacol=CORRECTED_DATA; field=1; abs=0.05 ;;
    s1|s2|s3) size=2048; scale=1.5; datacol=DATA; field=0; abs=${BENCH_ABS_SIM:-0.0001} ;;
    *) echo "unknown dataset $1" >&2; exit 2 ;;
  esac
}

ms_sha() {  # ms_sha <ms> : SHA-256 of the main-table files
  (cd "$1" && find . -maxdepth 1 -type f ! -name table.lock -printf '%f\n' | sort |
    xargs sha256sum)
}

for ds in "${datasets[@]}"; do
  settings "$ds"
  if [ ! -d "$run/ms/$ds.ms" ]; then
    cp -r "$data/$ds.ms" "$run/ms/$ds.ms"
    ms_sha "$run/ms/$ds.ms" > "$run/ms/$ds.ms-sha256-before.txt"
  fi
  for threads in $threads_list; do
    for mode in $modes; do
      for grid in $grids; do
        for loop in $loops; do
          name=$ds-$mode-$grid-$loop-j$threads
          [[ $name =~ $filter ]] || continue
          [ -f "$run/timing/$name.txt" ] && continue
          start=$(date -Iseconds)
          cat /proc/loadavg > "$run/load/$name.txt"
          if [ "$imager" = wsclean ]; then
            args=(-gridder wgridder -data-column "$datacol" -field "$field"
              -size "$size" "$size" -scale "${scale}asec" -weight briggs 0.5 -pol I
              -j "$threads" -no-update-model-required -temp-dir /run/tmp)
            case $mode in
              dirty) args+=(-niter 0 -make-psf) ;;
              auto) args+=(-niter "$niter" -nmiter 0 -gain 0.1 -mgain 0.8
                -auto-threshold 3 -auto-mask 5) ;;
              abs) args+=(-niter "$niter" -nmiter 0 -gain 0.1 -mgain 0.8
                -abs-threshold "$abs") ;;
            esac
            case $grid in
              nominres) args+=(-no-min-grid-resolution -wgridder-accuracy 1e-6) ;;
              pad2) args+=(-no-min-grid-resolution -wgridder-accuracy 1e-6 -padding 2) ;;
            esac
            [ "$loop" = hogbom ] && args+=(-no-fast-subminor)
            s=$(date +%s.%N)
            set +e
            docker run --rm --user "$(id -u):$(id -g)" --network none -e HOME=/tmp \
              -e OMP_NUM_THREADS="$threads" -v "$run:/run" -w /run "$image" \
              /usr/bin/time -v -o "/run/timing/$name.txt" \
              wsclean "${args[@]}" -name "/run/$name" "/run/ms/$ds.ms" > "$run/$name.log" 2>&1
            rc=$?
            set -e
            printf '%s\n' "wsclean ${args[*]} -name /run/$name /run/ms/$ds.ms" > "$run/$name.cmd"
          else
            cmd=${BENCH_TEMPLATE//$'\n'/ }
            for kv in "ms=$run/ms/$ds.ms" "datacol=$datacol" "field=$field" "size=$size" \
              "scale=$scale" "threads=$threads" "mode=$mode" "abs_threshold=$abs" \
              "grid=$grid" "loop=$loop" "out=$run/$name" "niter=$niter"; do
              cmd=${cmd//\{${kv%%=*}\}/${kv#*=}}
            done
            printf '%s\n' "$cmd" > "$run/$name.cmd"
            s=$(date +%s.%N)
            set +e
            OMP_NUM_THREADS=$threads RAYON_NUM_THREADS=$threads \
              /usr/bin/time -v -o "$run/timing/$name.txt" bash -c "$cmd" > "$run/$name.log" 2>&1
            rc=$?
            set -e
          fi
          e=$(date +%s.%N)
          cat /proc/loadavg >> "$run/load/$name.txt"
          wall=$(python3 -c "print(round($e - $s, 3))")
          printf '%s\t%s\t%s\t%s\n' "$name" "$rc" "$wall" "$start" >> "$run/jobs.tsv"
          echo "## $name exit $rc ${wall}s"
        done
      done
    done
  done
  ms_sha "$run/ms/$ds.ms" > "$run/ms/$ds.ms-sha256-after.txt"
  if ! cmp -s "$run/ms/$ds.ms-sha256-before.txt" "$run/ms/$ds.ms-sha256-after.txt"; then
    echo "## WARNING: $ds main table changed during the runs" >&2
  fi
done
rm -rf "$run/tmp"
echo "## done $run"
