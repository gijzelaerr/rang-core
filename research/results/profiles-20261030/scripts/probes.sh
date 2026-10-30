#!/usr/bin/env bash
# S1 probes: OpenBLAS A/B, scaling with baselines and channels, Cargo
# profile / target-cpu variants through RANG_CORE_LIB (ctypes).
# Usage: bash probes.sh outputs/simplification-review-20261030-NN
set -uo pipefail
cd ~/Worktrees/rang/simplification-review
export PATH=$HOME/.cargo/bin:$PATH
export RUSTUP_TOOLCHAIN=1.93
out=$1; shift
[ -e "$out" ] && { echo "$out exists"; exit 2; }
mkdir -p "$out"
py=.venv/bin/python
S=/mnt/c/Users/gijsm/AppData/Local/Temp/claude/C--Users-gijsm-Github-rang/aa19215f-384c-42dc-a46d-e0ce70222d6d/scratchpad/s1
F=outputs/core-k-20261030-01/fetch
log=$out/timings.tsv
printf 'step\twall_s\tuser_s\tsys_s\tmax_rss_kb\tcpu_pct\tstatus\tload_before\n' > "$log"
run() {
  local name=$1; shift
  echo "## $name"
  local lb; lb=$(cut -d' ' -f1-3 /proc/loadavg)
  /usr/bin/time -o "$out/$name.time" -f '%e\t%U\t%S\t%M\t%P' "$@" > "$out/$name.log" 2>&1
  local status=$?
  printf '%s\t%s\t%s\t%s\n' "$name" "$(tail -1 "$out/$name.time")" "$status" "$lb" >> "$log"
}
# 1. OpenBLAS A/B, alternating order.
for i in 1 2 3; do
  run pre-default-$i $py examples/precondition_luno_campaign.py "$out/pre-default-$i"
  run pre-blas1-$i env OPENBLAS_NUM_THREADS=1 $py examples/precondition_luno_campaign.py "$out/pre-blas1-$i"
done
for i in 1 2; do
  run camp-blas1-$i env OPENBLAS_NUM_THREADS=1 $py $S/profile_campaign.py $F "$out/camp-blas1-$i" --images original
  run camp-default-$i $py $S/profile_campaign.py $F "$out/camp-default-$i" --images original
done
# 2. Scaling probes (labelled probes; one image, no section 6 reference).
for b in 1 2 3 6; do
  run scale-b$b env OPENBLAS_NUM_THREADS=1 $py $S/profile_campaign.py $F "$out/scale-b$b-c2048" --baselines $b --channels 2048 --images original --no-reference
done
for c in 512 1024; do
  run scale-c$c env OPENBLAS_NUM_THREADS=1 $py $S/profile_campaign.py $F "$out/scale-b6-c$c" --baselines 6 --channels $c --images original --no-reference
done
# 3. Build variants of the core crate outside the checkout.
B=$HOME/Build/tmp/20261030-rang-s1
mkdir -p $B
( cd core && /usr/bin/time -f 'build default %e s' cargo build --offline --release -q --target-dir $B/default ) 2>&1 | tail -1
( cd core && CARGO_PROFILE_RELEASE_LTO=thin CARGO_PROFILE_RELEASE_CODEGEN_UNITS=1 /usr/bin/time -f 'build lto %e s' cargo build --offline --release -q --target-dir $B/lto ) 2>&1 | tail -1
( cd core && CARGO_PROFILE_RELEASE_LTO=thin CARGO_PROFILE_RELEASE_CODEGEN_UNITS=1 RUSTFLAGS="-C target-cpu=x86-64-v3" /usr/bin/time -f 'build v3 %e s' cargo build --offline --release -q --target-dir $B/v3 ) 2>&1 | tail -1
ls -la $B/*/release/librang_core.so
for v in default lto v3; do
  run bench-$v env RANG_CORE_LIB=$B/$v/release/librang_core.so $py examples/bench_core_f.py check "$out/bench-$v" outputs/core-f-20261029-01/baseline.json --target solve
  run camp-$v env OPENBLAS_NUM_THREADS=1 RANG_CORE_LIB=$B/$v/release/librang_core.so $py $S/profile_campaign.py $F "$out/camp-$v" --images original
done
run blosc-v3 env RANG_CORE_LIB=$B/v3/release/librang_core.so $py examples/bench_core_f.py check "$out/blosc-v3" outputs/core-f-20261029-01/baseline.json --target blosc
echo "## done"
cat "$log"
