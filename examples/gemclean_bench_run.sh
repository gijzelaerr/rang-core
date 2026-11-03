#!/usr/bin/env bash
# Run the gemclean benchmark matrix for one imager (research/gemclean-benchmark.md).
#
# Usage:
#   bash examples/gemclean_bench_run.sh IMAGER RUN_DIR [DATASET ...]
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
#   BENCH_LOCK      host lock held for each job, including its load records
#                   (default /home/gijsm/.rang-heavy.lock: heavy jobs on this
#                   host take turns); wall times come from GNU time, not
#                   from jobs.tsv alone, so the wait for the lock is not counted
#   BENCH_TEMPLATE  command line for a non-WSClean imager, with placeholders
#                   {ms} {datacol} {field} {size} {scale} {threads} {mode}
#                   {abs_threshold} {threshold_args} {grid} {loop} {out} {niter}
#                   ({threshold_args}: BENCH_AUTO_ARGS, default
#                   "-auto-threshold 3", for auto; "-abs-threshold X" for abs).
#                   It must write {out}-model.fits and {out}-residual.fits
#                   in WSClean's FITS orientation (and may write
#                   {out}-image.fits and {out}-report.json). It runs on the
#                   host under /usr/bin/time -v. gemclean, one command:
#     bash examples/gemclean_bench_gemclean.sh BINARY RUN_DIR [DATASET ...]
#
# Job name: <dataset>-<mode>-<grid>-<loop>-j<threads>. Per job the run
# directory gets <name>-*.fits, <name>.log, timing/<name>.txt (GNU time -v),
# load/<name>.txt (/proc/loadavg before and after),
# load/<name>.samples.txt (/proc/loadavg every 60 s during the job),
# load/<name>.busy.txt (the commands of every process above 50 % CPU before
# and after the job, WSL and Windows, since both share the hardware) and
# jobs.tsv (name, exit, wall_s, start ISO time). The Measurement Sets are copied into
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
lock=${BENCH_LOCK:-/home/gijsm/.rang-heavy.lock}
exec 9>"$lock"
mkdir -p "$run/ms" "$run/timing" "$run/load" "$run/tmp"
[ -f "$run/jobs.tsv" ] || printf 'name\texit\twall_s\tstart\n' > "$run/jobs.tsv"

settings() {  # settings <dataset>: sets size scale datacol field abs
  case $1 in
    slice) size=512; scale=8; datacol=CORRECTED_DATA; field=1; abs=0.05 ;;
    h3) size=4096; scale=1.5; datacol=DATA; field=0; abs=${BENCH_ABS_SIM:-0.0001} ;;
    s1|s2|s3|h1|h2|h4) size=2048; scale=1.5; datacol=DATA; field=0; abs=${BENCH_ABS_SIM:-0.0001} ;;
    *) echo "unknown dataset $1" >&2; exit 2 ;;
  esac
}

busy() {  # busy <label>: processes above 50 % of one core, WSL then Windows
  echo "== $1 $(date -Iseconds) WSL"
  top -b -n 2 -d 1 -c -w 200 | awk '/^top - /{n++} n==2 && $1 ~ /^[0-9]+$/ && $9+0 > 50'
  echo "== $1 Windows"
  timeout 20 /mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe -NoProfile -Command \
    'Get-CimInstance Win32_PerfFormattedData_PerfProc_Process | Where-Object { $_.PercentProcessorTime -gt 50 -and $_.Name -notmatch "^(_Total|Idle)$" } | ForEach-Object { "$($_.PercentProcessorTime) $($_.Name)" }' \
    2>/dev/null | tr -d '\r' || echo "(not available)"
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
          flock 9
          start=$(date -Iseconds)
          busy before > "$run/load/$name.busy.txt"
          cat /proc/loadavg > "$run/load/$name.txt"
          ( while :; do cat /proc/loadavg; /usr/bin/sleep 60; done ) > "$run/load/$name.samples.txt" &
          sampler=$!
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
            if [ "$mode" = auto ]; then threshold_args=${BENCH_AUTO_ARGS:--auto-threshold 3}
            else threshold_args="-abs-threshold $abs"; fi
            cmd=${BENCH_TEMPLATE//$'\n'/ }
            for kv in "ms=$run/ms/$ds.ms" "datacol=$datacol" "field=$field" "size=$size" \
              "scale=$scale" "threads=$threads" "mode=$mode" "abs_threshold=$abs" \
              "grid=$grid" "loop=$loop" "out=$run/$name" "niter=$niter" \
              "threshold_args=$threshold_args"; do
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
          kill "$sampler" 2>/dev/null || true
          wait "$sampler" 2>/dev/null || true
          busy after >> "$run/load/$name.busy.txt"
          flock -u 9
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
