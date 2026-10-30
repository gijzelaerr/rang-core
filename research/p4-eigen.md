# Big plan task P4: survey eigensolver, same decision, faster algorithm

Protocol frozen 2026-10-30 in the commit that adds this file, before any
change to `src/` and before any measurement. Status: **proposed** (protocol
only). Task P4 of [big-plan.md](big-plan.md), proposal P4 of
[simplification-review.md](simplification-review.md) (section 3). Under
AGENTS.md this is engineering, not a scientific contribution: the gate is
that every archived survey decision is reproduced, not improved.

## What changes, and what does not

- `rang_toy::response::checked_eigen` (the two 32 × 32 symmetric
  eigenproblems per `anchored_step` call, behind `rang_response_step`) calls
  a new solver: Householder tridiagonalisation followed by the implicit QL
  algorithm with Wilkinson-type shifts (the EISPACK `tred2`/`tql2` pair), in
  plain Rust, deterministic (no threads, no `mul_add`, fixed iteration order),
  in `src/linalg.rs` (or a new `src/eigen.rs`). Same return convention as
  the Jacobi routine: eigenvalues descending (sorted with `total_cmp`, as
  now), eigenvectors as columns `v[i][k]`.
- If the QL iteration does not converge within a fixed cap (30 iterations
  per eigenvalue), `checked_eigen` returns the existing error string
  "eigensystem residual failed", which maps to status 1. No new status.
- Unchanged: the gauge basis, the projection, `checked_eigen`'s residual
  check (1e-9 × max |H|), the 1e-10 rank cutoff, the 1e-6 damping, the
  `8*nactive-4` rank rule, the nonpositivity check at `-cutoff`, every status
  code, the C ABI and every Python wrapper.
- `linalg::eigen` (classical Jacobi) stays, unchanged, under its name: it is
  still used by the pointing toy (`src/lib.rs`, `linalg::solve`), whose
  archives this task must not move, and it is the A side of every A/B and of
  the unit tests. Switching the pointing toy is out of scope (open item).

## Arms and libraries (frozen)

- **A (Jacobi)**: the root crate built at base commit `4167141` in this
  worktree before any edit (`cargo +1.93 build --release --offline`, P0
  profile: thin LTO, one codegen unit, `x86-64-v3`), copied to
  `outputs/p4-eigen-20261030-01/lib/librang_toy-jacobi.so`
  (SHA256 `452bf8a1f38b794e0b3dec7b47a2ae86560ec44cbc83488c22f9a6d808b91ff0`).
- **B (QL)**: the root crate built from the branch head, copied to
  `outputs/p4-eigen-20261030-NN/lib/librang_toy-ql.so` with its SHA256.
- Every Python run sets `RANG_TOY_LIB` explicitly to one of the two copies
  (without it `rangtoy.build()` would rebuild the working tree and a
  "baseline" could silently load B). The core library is the base build,
  copied to `outputs/p4-eigen-20261030-01/lib/librang_core.so`
  (SHA256 `5b923075…929bc7`), set through `RANG_CORE_LIB` where a tool reads
  it; P4 does not touch `core/`.

## Acceptance criteria (frozen)

1. **Survey statuses and counts identical, B against A and against the
   archives.**
   - Section 6: `examples/bench_core_f.py check --target survey` against
     `outputs/core-f-20261029-01/baseline.json` (`survey_identical`: the
     survey dictionary 389 / 43 / 592 / 0 with 389 × status 0 and 43 ×
     status 3, and the per-bin label and status SHA256s); and
     `examples/prototype_section6.py` + `examples/check_section6.py` against
     `outputs/core-section6-oracle-20261029-01`, every criterion except
     `8_cost` passing (that wall-time criterion is load-bound on this shared
     host, P8; it is reported, not gated, and compared A against B).
   - Phase 2: `examples/validate_core_phase2.py`, every criterion as
     archived (`research/results/core-phase2.json`), including the rank
     survey 389 status 0, 43 status 3, 592 without TRAIN data.
   - LUNO solved survey: `examples/survey_luno_solved.py` on
     `outputs/luno-support-20261029-01/extract` and
     `outputs/luno-solve-20261029-02/solve` equals
     `outputs/luno-solve-20261029-02/survey/result.json` (and
     `research/results/meerkat-luno-solved.json`) in every non-timing leaf.
   - LUNO support survey (offline from the archived extraction):
     `examples/survey_luno_support.py` equals
     `outputs/luno-support-20261029-01/survey/result.json`, and
     `examples/audit_luno_support_status.py` equals
     `outputs/luno-support-20261029-01/status-audit.json`, in every
     non-timing leaf (389 × 0 and 43 × 3 for `(H,0,0,0)`, 160 × 6, the
     frozen-call 389 × 4).
   - Signal and prospective: `core_cli signal` / `prospective` on the
     archived inputs (S1 suite command lines), then `core_cli compare
     signal` / `prospective` against `research/results/gain-tv-next-signal.json`
     / `gain-tv-next-prospective.json`: `passed: true` under both arms.
     In addition, the B result equals the A result in every leaf except the
     ones P8 found to vary run to run on unchanged code: every `seconds`
     field, `core_prospective`'s `frozen_train_responses_sha256` (hashes
     `full_training_normals_seconds`), `core_signal`'s
     `acceptance_digest_core` (includes `metrics.seconds`), and absolute
     paths. Floats that differ are listed with their largest difference; any
     differing count, status, label, mask hash or decision fails.
2. **Per-call identity.** Every `anchored_response` call made by the section
   6 / phase 2 survey, the LUNO solved and support surveys, and the signal
   and prospective stages is recorded (inputs only, by wrapping the Python
   function in `examples/bench_p4_eigen.py`; no module is edited) and
   replayed through both libraries by direct ctypes calls. Gate: the native
   status equal for every call; for status 0, `full_rank` and `kept_rank`
   equal. Reported (not gated): the largest difference of `delta` relative to
   the largest gain norm, and of each diagnostic relative to its value; the
   smallest margin of `max_relative_step` to its 0.1 trust threshold.
3. **Rank decision at the 1e-10 cutoff, bin for bin, with margins.** The
   recorded inputs are dumped as raw f64 records and an ignored Rust test in
   `src/response.rs` (`P4_DUMP=<file> P4_OUT=<file>`) runs the real
   `gauge_basis` and `project` on the full and kept matrices and both
   solvers, writing per call: ranks under each solver, the largest eigenvalue
   difference relative to `largest`, the smallest retained eigenvalue over
   the cutoff (`min λ>c / c`), the largest discarded eigenvalue over the
   cutoff (`max λ≤c |λ| / c`), and the most negative eigenvalue over the
   cutoff (the `-cutoff` nonpositivity check). Gate: ranks equal for every
   call. Reported: the smallest margin over all calls on each side of the
   cutoff (as a factor), so a reader can judge robustness, and the largest
   eigenvalue difference. Robustness argument, stated before measuring: the
   backward error of Householder + QL is of order n·ε·λmax ≈ 32 × 2.2e-16 ≈
   7e-15 λmax, as is Jacobi's; the cutoff is 1e-10 λmax, so a decision can
   only flip if some eigenvalue lies within about 1e-14 λmax of it, that is
   within a factor of about 1.0001 of the cutoff. The margin table shows
   whether any does.
4. **Eigenvalue agreement** (reported, gated only through 2 and 3): on the
   recorded survey matrices, max |λ_B − λ_A| / λmax; expected about 1e-14.
5. **Rust unit tests** comparing the new solver with Jacobi: random
   symmetric matrices (fixed-seed LCG, n = 1…32), matrices with exactly four
   zero eigenvalues built as QΛQᵀ, repeated eigenvalues, diagonal and
   already tridiagonal matrices, the zero matrix, a cluster at 1e-12 of the
   scale, and a real projected survey matrix. Checked: eigenvalues against
   Jacobi to 1e-12 λmax, reconstruction ‖VΛVᵀ − A‖ and orthogonality
   ‖VᵀV − I‖ to 1e-12, and invariant subspaces (the projector onto each
   cluster of equal eigenvalues), not individual vectors. The existing
   `thirty_two_dimensional_eigen_residual` test keeps passing.
6. **Speed.** core-f's frozen rule: a speed-up is claimed only if B's
   minimum is below A's minimum by more than A's median-minus-minimum
   spread. Measurements, interleaved A/B to cancel load drift (ABAB… then
   BABA…, 1-minute load average from `/proc/loadavg` logged before and after
   every run):
   - survey block: `bench_core_f.py check --target survey` (7 repeats per
     run, parts reported: whole block and the 432 `anchored_response`
     calls), 3 runs per arm;
   - single call: the recorded section 6 calls replayed through ctypes per
     arm (microbenchmark, minimum and median of 7 passes), 3 runs per arm;
   - signal and prospective stages: `core_cli signal` / `prospective`
     wall, 3 runs per arm;
   - section 6 prototype wall excluding decode, as `check_section6.py`
     reports it, 3 runs per arm.
   Siblings share the 8 physical cores; results are labelled with load.
7. **Checks.** `cargo +1.93 build --release --offline`, `clippy -D
   warnings`, `fmt --check`, root crate tests, targeted pytest
   (`tests/test_p4_eigen.py` plus the tests that call `anchored_response`),
   then `bash tools/check-all.sh` once before the final commit.

Failures are recorded as frozen. Any step not listed here is labelled
post hoc.

## Results

Pending.

## Measurement log

Date for every row: 2026-10-30. Load is the 1-minute average.

| Tool run | Input | Wall | Peak RSS | Notes |
| --- | --- | ---: | ---: | --- |
| `uv venv -p python3.14` + `uv pip install -e '.[pointing,beam,test,imaging]' ruff maturin numcodecs` (public PyPI) | worktree | 14.2 s | 390 MB | |
| `cargo +1.93 build --release --offline` root, core; `maturin develop --release --offline` | base `4167141` | 5.9 s, 12.3 s, 0.5 s | 380 MB | load 9–18; A library frozen from this build |
