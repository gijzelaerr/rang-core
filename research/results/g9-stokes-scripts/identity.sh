#!/usr/bin/env bash
# identity.sh OUT MAIN_BIN G9_BIN : criterion A of research/g9-stokes.md. G3's settings on D1, main's
# binary and the G9 binary, five configurations, plus C0 with -pol I given (G9 only); SHA-256 of
# every FITS file; each run under the heavy lock.
set -uo pipefail
O=$1; M=$2; G=$3
ms=/mnt/d/rang/outputs/20261106-g3-spectral/data/D1.ms
BASE=(-size 2048 2048 -scale 1.5asec -weight briggs 0.5 -niter 1000000 -gain 0.1 -nmiter 1000 -data-column DATA -field 0 -j 16)
# IDEXTRA: options both binaries take, such as -no-update-model-required since G6 (main 3defaae
# writes MODEL_DATA after imaging by default; D1.ms is G3's, read in place, never written).
# shellcheck disable=SC2206
BASE+=(${IDEXTRA:-})
declare -A CFGS=(
  [C0]="-abs-threshold 0.00015"
  [C0s]="-abs-threshold 0.00015 -single -wgridder-accuracy 1e-4"
  [C1]="-channels-out 8 -join-channels -fit-spectral-pol 4 -abs-threshold 0.00015"
  [C3]="-channels-out 4 -abs-threshold 0.0003"
  [C4]="-channel-range 2 14 -channels-out 3 -niter 0"
)
run() {  # run TAG BIN CFG EXTRA...
  local tag=$1 bin=$2 cfg=$3; shift 3
  local d=$O/identity/$tag-$cfg
  rm -rf "$d"; mkdir -p "$d"
  # shellcheck disable=SC2086
  flock ~/.rang-heavy.lock /usr/bin/time -v -o "$d/time.txt" "$bin" "${BASE[@]}" ${CFGS[$cfg]} "$@" -name "$d/g" "$ms" > "$d/log.txt" 2>&1
  echo "$tag $cfg rc=$? $(awk -F': ' '/Maximum resident/{print $2}' "$d/time.txt") kB"
  (cd "$d" && sha256sum g-*.fits > sha256.txt && rm -f g-*.fits)
}
for cfg in C0 C0s C1 C3 C4; do
  run main "$M" $cfg
  run g9 "$G" $cfg
done
run g9pol "$G" C0 -pol I
for cfg in C0 C0s C1 C3 C4; do
  if diff -q "$O/identity/main-$cfg/sha256.txt" "$O/identity/g9-$cfg/sha256.txt" > /dev/null; then echo "A $cfg identical ($(wc -l < "$O/identity/main-$cfg/sha256.txt") files)"; else echo "A $cfg DIFFERS"; fi
done
if diff -q "$O/identity/main-C0/sha256.txt" "$O/identity/g9pol-C0/sha256.txt" > /dev/null; then echo "A C0 -pol I identical"; else echo "A C0 -pol I DIFFERS"; fi
