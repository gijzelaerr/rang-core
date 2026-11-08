#!/usr/bin/env bash
# The measured runs of research/gram-solver.md, stage by stage. Run from the
# worktree root after building gram_solver_bench and gemclean in release. Each stage
# holds the heavy lock throughout (GRAM_HELD in gram_solver_run.sh), so nothing runs
# in parallel and a stage is not interleaved with other sessions job by job. A job
# whose counters exist is skipped.
#
#   SOLVER_ROOT=DIR bash examples/gram_solver_jobs.sh STAGE [STAGE ...]
#
# DIR/prep/{s1,s2,s3} hold the arrays of gemclean_bench_compare.py prepare, and
# DIR/prep/sN.json the catalogues. λ = 100 µJy is CLEAN's threshold in the
# benchmark: at the optimum of signed ℓ1 the residual peak is λ.
set -u
ROOT="${SOLVER_ROOT:-$HOME/Build/tmp/20261103-gram-solver}"
export SOLVER_ROOT="$ROOT"
R=examples/gram_solver_run.sh
LMAX=2.4453593497e2
L=1e-4
MAJOR="cycles=15 gamma=0.2 iters=400 outer_kkt=2e-6 kkt=2e-6 lambda=$L"

counts() {
    # Instructions by difference: read, setup, N applies, N passes.
    $R s1 c-read read
    $R s1 c-exact-apply apply backend=exact reps=10
    $R s1 c-gram-setup setup backend=gram s=8 theta=0.69
    $R s1 c-gram-apply apply backend=gram s=8 theta=0.69 reps=50
    $R s1 c-psf-setup setup backend=psf
    $R s1 c-psf-apply apply backend=psf reps=200
    for k in 4 16; do
        $R s1 c-read-k$k read stride=$k
        $R s1 c-exact-apply-k$k apply backend=exact reps=5 stride=$k
        $R s1 c-gram-setup-k$k setup backend=gram s=8 theta=0.69 stride=$k
        $R s1 c-gram-apply-k$k apply backend=gram s=8 theta=0.69 reps=20 stride=$k
    done
}

spectrum() {
    $R s1 sp-exact spectrum backend=exact power=30 lanczos=30
    $R s1 sp-gram spectrum backend=gram s=8 theta=0.69 power=100 lanczos=80
    $R s1 sp-coarse spectrum backend=gram s=6 theta=1.18 power=100 lanczos=80
}

matched() {
    # The same iterates: one start, one step, one λ, on both backends.
    local args="prior=l1signed lambda=$L lmax=$LMAX iters=300 checkpoints=50,100,200,300"
    $R s1 m-gram solve backend=gram s=8 theta=0.69 $args
    $R s1 m-exact solve backend=exact $args
}

accuracy() {
    # The minimiser of each operator: inner FISTA on the PSF, outer on G̃, warm
    # from the exact solution, then scored by the exact certificate.
    local x0="$ROOT/runs/s1/c1-x.f64"
    for st in 2:1.0 4:1.2 6:1.18 8:0.69; do
        local s="${st%:*}" t="${st#*:}"
        $R s1 acc-s$s-t$t solve backend=psf prior=l1signed x0="$x0" lmax=$LMAX \
            outer_s=$s outer_theta=$t cycles=4 gamma=0 iters=150 outer_kkt=2e-6 \
            kkt=2e-6 lambda=$L
    done
}

recipes() {
    # S1, wholly on the Gram operator (inner and outer): the λ schedule of the PSF
    # run for 8 cycles, so that its objective can be read against c1 at each cycle.
    $R s1 r-gram solve backend=gram s=8 theta=0.69 outer_same=1 \
        prior=l1signed lmax=$LMAX $MAJOR cycles=8
    # PSF inner, Gram outer: visibility-free after the setup.
    $R s1 r-psfgram solve backend=psf outer_s=8 outer_theta=0.69 prior=l1signed $MAJOR
}

s2() { $R s2 c1 solve backend=psf prior=l1signed $MAJOR; }
s3() { $R s3 c1 solve backend=psf prior=l1signed $MAJOR; }
s2nn() { $R s2 d1 solve backend=psf prior=l1 $MAJOR; }

sara() {
    # SARA-style on S2: non-negative, 4 levels, db1-db8 and Dirac, warm dual, 2 dual
    # iterations a step. Each run's λ is in coefficient units of the scaled frame, so
    # the effective threshold on a point is about 3 λ. sara1 reports a poor schedule.
    local args="backend=psf prior=sara levels=4 bases=8 dual=2 every=10 outer_kkt=0"
    $R s2 sara1 solve $args lambda=1e-4 cycles=7 iters=100 gamma=0.2
    $R s2 sara2 solve $args lambda=3.3e-5 cycles=12 iters=100 gamma=0.07
}

base() {
    # The CLEAN models as raw arrays for the exact certificate (evals).
    local b=/mnt/d/rang/outputs/20261102-gemclean/bench
    mkdir -p "$ROOT/base"
    "${GRAM_PY:-python}" - "$ROOT/base" "$b" <<'PY'
import sys

import numpy as np
from rang.core_imaging import read_fits

out, bench = sys.argv[1:3]
models = {
    "gem": f"{bench}/gmclean-184c3bc/s1-abs-nominres-fast-j16-model.fits",
    "wsc": f"{bench}/wsclean/s1-abs-nominres-hogbom-j16-model.fits",
}
for tag, path in models.items():
    m = np.squeeze(read_fits(path)[0]).astype(np.float64)
    np.ascontiguousarray(m.T).tofile(f"{out}/s1-{tag}.f64")
    np.ascontiguousarray(np.maximum(m, 0).T).tofile(f"{out}/s1-{tag}-pos.f64")
PY
}

control() {
    # The reference of the accuracy table: exact outer cycles, same start and iterations.
    $R s1 acc-exact solve backend=psf prior=l1signed x0="$ROOT/runs/s1/c1-x.f64" \
        lmax=$LMAX cycles=4 gamma=0 iters=150 outer_kkt=2e-6 kkt=2e-6 lambda=$L
}

score() {
    # Every model through the benchmark's scorer, and the remaining certificates.
    local c="${GRAM_PY:-python} examples/gemclean_bench_compare.py score"
    local p="$ROOT/prep" w=/mnt/d/rang/outputs/20261102-gemclean/bench/wsclean
    local bin="${GRAM_BIN:-core/target/release/gram_solver_bench}" run="$ROOT/runs/s1"
    mkdir -p "$ROOT/scores" "$ROOT/evals"
    for d in s1 s2 s3; do
        $c "$p/$d" "$p/$d.json" "$w" "$ROOT/scores/wsc-$d.json" \
            --jobs "$d-abs-nominres-hogbom-j16" "$d-abs-nominres-fast-j16"
        $c "$p/$d" "$p/$d.json" "$ROOT/runs/$d" "$ROOT/scores/gem-$d.json" --jobs "gem-$d"
    done
    $c "$p/s1" "$p/s1.json" "$run" "$ROOT/scores/sol-s1.json" --jobs c1 d1 r-gram r-psfgram \
        acc-s8-t0.69 acc-s6-t1.18 acc-s4-t1.2 acc-s2-t1.0 acc-exact
    $c "$p/s2" "$p/s2.json" "$ROOT/runs/s2" "$ROOT/scores/sol-s2.json" --jobs c1 d1 sara1 sara2
    $c "$p/s3" "$p/s3.json" "$ROOT/runs/s3" "$ROOT/scores/sol-s3.json" --jobs c1
    RAYON_NUM_THREADS=8 $bin "$p/s1" "$run" ev eval backend=exact eval_eps=1e-6 lambda=$L \
        prior=l1signed s=8 theta=0.69 \
        files="$run/acc-exact-x.f64,$run/r-gram-x.f64,$run/r-psfgram-x.f64" \
        > "$ROOT/evals/s1-recipes.jsonl" 2>&1
    for d in s2 s3; do
        RAYON_NUM_THREADS=8 $bin "$p/$d" "$ROOT/runs/$d" ev eval backend=exact eval_eps=1e-6 \
            lambda=$L prior=l1signed files="$ROOT/runs/$d/c1-x.f64" > "$ROOT/evals/$d-c1.jsonl" 2>&1
    done
}

evals() {
    # Exact certificates of saved models, each with the operator's error there.
    # Output: ROOT/evals/NAME.jsonl (eval mode writes no counters).
    local bin="${GRAM_BIN:-core/target/release/gram_solver_bench}" run="$ROOT/runs/s1"
    local list="$run/c1-x.f64,$ROOT/base/s1-gem.f64,$ROOT/base/s1-wsc.f64"
    for k in 50 100 200 300; do
        list="$list,$run/m-gram-x$k.f64,$run/m-exact-x$k.f64"
    done
    mkdir -p "$ROOT/evals"
    RAYON_NUM_THREADS=8 $bin "$ROOT/prep/s1" "$run" ev eval backend=exact eval_eps=1e-6 \
        lambda=$L prior=l1signed s=8 theta=0.69 files="$list" > "$ROOT/evals/s1-main.jsonl" 2>&1
    RAYON_NUM_THREADS=8 $bin "$ROOT/prep/s1" "$run" ev eval backend=exact eval_eps=1e-9 \
        lambda=$L prior=l1signed files="$run/c1-x.f64" > "$ROOT/evals/s1-eps9.jsonl" 2>&1
    for st in 2:1.0 4:1.2 6:1.18 8:0.69; do
        local s="${st%:*}" t="${st#*:}"
        RAYON_NUM_THREADS=8 $bin "$ROOT/prep/s1" "$run" ev eval backend=exact eval_eps=1e-6 \
            lambda=$L prior=l1signed s=$s theta=$t files="$run/acc-s$s-t$t-x.f64" \
            > "$ROOT/evals/s1-acc-s$s-t$t.jsonl" 2>&1
    done
}

gemclean_base() {
    # GeMClean at this commit with the benchmark's command, counted.
    local data=/mnt/d/rang/outputs/20261102-gemclean/bench/data
    for d in s1 s2 s3; do
        local run="$ROOT/runs/$d" name="gem-$d"
        [ -s "$run/timing/$name.perf" ] && continue
        perf stat -x, -e instructions,cycles \
            -o "$run/timing/$name.perf" /usr/bin/time -v -o "$run/timing/$name.txt" \
            core/target/release/gemclean -name "$run/$name" -size 2048 2048 \
            -scale 1.5asec -weight briggs 0.5 -niter 1000000 -gain 0.1 \
            -nmiter 1000 -abs-threshold 100e-6 -data-column DATA -field 0 -j 8 \
            -no-update-model-required "$data/$d.ms" > "$run/$name.log" 2>&1
    done
}

for stage in "$@"; do
    echo "== $stage waiting $(date +%H:%M:%S)"
    exec 9>>/home/gijsm/.rang-heavy.lock
    flock 9
    export GRAM_HELD=1
    echo "== $stage $(date +%H:%M:%S) load $(cut -d' ' -f1-3 /proc/loadavg)"
    "$stage"
    echo "== $stage done $(date +%H:%M:%S)"
    flock -u 9
    exec 9>&-
done
