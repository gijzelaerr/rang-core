#!/usr/bin/env bash
# Build and verify the gemclean benchmark datasets (research/gemclean-benchmark.md).
#
# Usage: bash examples/gemclean_bench_datasets.sh [OUT_DIR]
#   OUT_DIR defaults to outputs/gmclean-bench-20261102. Makes OUT_DIR/data
#   (s1.ms s2.ms s3.ms with catalogues s1.json s2.json s3.json, the Stokes I
#   noise noise.c64 shared by all three, slice.ms and slice.json), the
#   WSClean -niter 0 checks in OUT_DIR/wsclean-dirty and the scoring inputs
#   in OUT_DIR/prep/<dataset> (examples/gemclean_bench_compare.py prepare).
#   Every step is timed into OUT_DIR/datasets-timing.tsv.
set -euo pipefail
root=$(cd "$(dirname "$0")/.." && pwd)
out=$(realpath -m "${1:-$root/outputs/gmclean-bench-20261102}")
slice_src=${BENCH_SLICE_MS:-/home/gijsm/Build/tmp/20261030-clean-certified-outputs/clean-certified-20261030-02-wsclean/c.ms}
py=$root/.venv/bin/python
d=$out/data
mkdir -p "$d" "$out/prep"
tsv=$out/datasets-timing.tsv
[ -f "$tsv" ] || printf 'step\twall_s\tmax_rss_kb\n' > "$tsv"
timed() {  # timed <step> <command...>
  local step=$1; shift
  /usr/bin/time -f "%e %M" -o "$out/.time" "$@"
  printf '%s\t%s\t%s\n' "$step" "$(cut -d' ' -f1 "$out/.time")" "$(cut -d' ' -f2 "$out/.time")" >> "$tsv"
}

for s in 1 2 3; do
  if [ ! -d "$d/s$s.ms" ]; then
    noise=()
    [ $s = 1 ] && noise=(--noise-out "$d/noise.c64")
    timed "simulate S$s" "$py" "$root/examples/gemclean_bench_simulate.py" "$d/s$s.ms" \
      --sky S$s --catalogue "$d/s$s.json" "${noise[@]}"
  fi
done
if [ ! -d "$d/slice.ms" ]; then
  cp -r "$slice_src" "$d/slice.ms"
  cat > "$d/slice.json" <<'EOF'
{"components": [{"kind": "point", "x": 256.0, "y": 256.0, "l": 0.0, "m": 0.0, "flux": 14.9532}],
 "calibrator_flux_jy": 14.9532,
 "image": {"size": 512, "scale_arcsec": 8.0},
 "note": "PKS 1934-638 at the phase centre; CASA setjy Perley-Butler 2010 Stokes I averaged over the channels with the gridding weights (research/clean-certified-imaging.md section 3)",
 "ms": "copy of /home/gijsm/Build/tmp/20261030-clean-certified-outputs/clean-certified-20261030-02-wsclean/c.ms"}
EOF
fi
timed "wsclean -niter 0 checks" env BENCH_DATA="$d" BENCH_MODES=dirty BENCH_GRIDS="minres nominres" \
  BENCH_LOOPS=fast BENCH_THREADS=16 bash "$root/examples/gemclean_bench_run.sh" wsclean "$out/wsclean-dirty"
w=$out/wsclean-dirty
for ds in s1 s2 s3 slice; do
  [ -d "$out/prep/$ds" ] && continue
  if [ $ds = slice ]; then
    extra=(--size 512 --scale 8 --datacol CORRECTED_DATA --field 1)
  else
    extra=(--size 2048 --scale 1.5 --noise "$d/noise.c64")
  fi
  timed "prepare $ds" "$py" "$root/examples/gemclean_bench_compare.py" prepare "$d/$ds.ms" "$d/$ds.json" \
    "$out/prep/$ds" "${extra[@]}" --wsclean-dirty "$w/$ds-dirty-minres-fast-j16" \
    --wsclean-dirty "$w/$ds-dirty-nominres-fast-j16" > "$out/prep/$ds.log" 2>&1
done
echo "## done $out"
