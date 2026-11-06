#!/usr/bin/env bash
# Whole imaging jobs for research/gridder-theory.md: gemclean's default against
# the visibility-free major cycle (-gram-operator), on the benchmark skies S1-S3
# and the optimisation skies point, disc, crowded. One job at a time, each under
# the heavy lock; every job prints wall time and load.
#
# Usage: bash examples/gridder_gram_jobs.sh OUT_DIR GRAM_F64 GRAM_F32 [SKY ...]
# GRAM_F64 and GRAM_F32 are S,THETA for the double and single precision runs.
set -uo pipefail
root=$(cd "$(dirname "$0")/.." && pwd)
bin=$root/core/target/release/gemclean
out=$1
f64=$2
f32=$3
shift 3
skies=("$@")
[ ${#skies[@]} -eq 0 ] && skies=(s1 s2 s3 point disc crowded)
bench=/home/gijsm/Build/tmp/20261102-gmclean-bench
opt=/home/gijsm/Build/tmp/20261102-gmclean-opt
mkdir -p "$out"
for sky in "${skies[@]}"; do
  case $sky in
    s1|s2|s3) ms=$bench/$sky.ms; common="-weight briggs 0.5 -niter 1000000 -gain 0.1 -nmiter 1000 -abs-threshold 0.0001 -data-column DATA -field 0" ;;
    point) ms=$opt/point/sim.ms; common="-weight briggs 0 -niter 1000000 -abs-threshold 1e-4" ;;
    disc) ms=$opt/disc/sim.ms; common="-weight briggs 0 -niter 1000000 -abs-threshold 1e-3" ;;
    crowded) ms=$opt/crowded/sim.ms; common="-weight briggs 0 -niter 1000000 -abs-threshold 3e-4" ;;
    *) echo "unknown sky $sky"; exit 2 ;;
  esac
  while read -r mode flags; do
    name=$sky-$mode
    cmd="$bin -name $out/$name -size 2048 2048 -scale 1.5asec $common -j 8 -no-update-model-required $flags $ms"
    echo "$cmd" > "$out/$name.cmd"
    flock /home/gijsm/.rang-heavy.lock bash -c "
      read -r load1 _ < /proc/loadavg
      s=\$(date +%s.%N)
      /usr/bin/time -v -o $out/$name.time $cmd > $out/$name.log 2>&1
      e=\$(date +%s.%N)
      read -r load2 _ < /proc/loadavg
      echo \"$name wall \$(echo \"\$e - \$s\" | bc) load \$load1 \$load2\" | tee -a $out/jobs.tsv
    "
  done <<EOF
base
gram -gram-operator $f64
bnw -beam-no-w
gram-bnw -gram-operator $f64 -beam-no-w
single -single -wgridder-accuracy 1e-4
gram-single -single -wgridder-accuracy 1e-4 -gram-operator $f32
EOF
done
