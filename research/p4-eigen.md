# Big plan task P4: survey eigensolver, same decision, faster algorithm

Protocol frozen 2026-10-30 in the commit that adds this file, before any
change to `src/` and before any measurement. Status: **implemented and
measured: every frozen identity criterion passes (all 13,989 recorded
`anchored_response` calls give the same status and ranks under both
solvers; the smallest margin to the 1e-10 cutoff is a factor 7.3e7 above
and 1.6e5 below); the survey block is 2.5× faster and the signal stage
about 26 s faster under load; section 6's cost criterion now passes at load
18–22**. Task P4 of [big-plan.md](big-plan.md), proposal P4 of
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

## Implementation (implemented)

- `src/linalg.rs`: `eigen_ql` = `tridiagonalize` (EISPACK `tred2`) +
  `ql_implicit` (`tql2`), ported from the public-domain JAMA listing; the
  QL rotations act on the transposed eigenvector matrix so each update is
  two contiguous rows. 30-iteration cap per eigenvalue, `None` on overrun.
  `linalg::eigen` (Jacobi) is unchanged and still used by `src/lib.rs`.
- `src/response.rs`: `checked_eigen` calls `checked_eigen_with(h, eigen_ql)`;
  an overrun maps to the existing "eigensystem residual failed" (status 1);
  everything after it is unchanged. Two new tests: projected survey-like
  blocks (scalar-model TRAIN normals through the real `gauge_basis` and
  `project`, 2–4 stations) give the same ranks and spectra (1e-12 λmax)
  under both solvers and the expected status; and the ignored
  `p4_dump_audit` (criterion 3).
- Unit tests in `src/linalg.rs` (criterion 5): random symmetric n = 1…32
  (3 each), four exact zero eigenvalues, repeated eigenvalues in blocks of
  8, a 1e-12 cluster, diagonal, tridiagonal, identity, zero and empty
  matrices, and bitwise determinism. Deviation from the protocol wording:
  the "real projected survey matrix" unit test uses synthetic survey-like
  normals (a real block would need archive data in the repository); every
  real survey matrix is covered by criterion 3 instead.
- `examples/bench_p4_eigen.py` (record, replay, dump, diff) and
  `tests/test_p4_eigen.py` (status 0 at 3 and 4 stations, status 3 at 2,
  status 4 for `(H,0,H,0)`, deterministic deltas, the harness end to end).
- No C ABI, Python wrapper, `core/` or Cargo change. Libraries:
  A `librang_toy-jacobi.so` (`452bf8a1…`), B `librang_toy-ql.so`
  (`26e4b437…`, built from `e0f71b8`), both in
  `outputs/p4-eigen-20261030-01/lib/`.

## Results (measured)

Runs: `-02` records every survey and stage under each arm (recorder on),
`-03` replays and audits the recordings, `-04` is the interleaved timing
(recorder off). The suite and analysis scripts are copied into each run
directory (`suite-record.sh`, `suite-timing.sh`, `identity.sh`).

### 1. Statuses and counts against the archives (pass)

| Comparator | Jacobi (A) | QL (B) |
| --- | --- | --- |
| `bench_core_f.py check --target survey` vs core-f baseline (389/43/592/0, label and status SHA256s) | `survey_identical` true (4 runs) | true (4 runs) |
| `check_section6.py` vs section 6 oracle, criteria 1–7, 9–11 | all pass (4 runs) | all pass (4 runs) |
| same, `8_cost` (≤ 2.0 s excluding decode; reported, not gated) | fails 4 of 4 (2.04–3.96 s) | passes 3 of 3 timing runs (1.27–1.44 s); fails the recorder run (2.28 s, load 31) |
| `validate_core_phase2.py` (rank survey 389 × 0, 43 × 3, 592) | all 11 pass | all 11 pass |
| `survey_luno_solved.py` vs `luno-solve-20261029-02/survey/result.json` | – | 524 of 524 leaves equal |
| `survey_luno_support.py` vs `luno-support-20261029-01/survey/result.json` | – | 7,743 of 7,743 leaves equal |
| `audit_luno_support_status.py` vs `status-audit.json` (389 × 0, 43 × 3; 160 × 6; frozen 389 × 4) | – | 16 of 16 leaves equal |
| `core_cli compare prospective` vs `gain-tv-next-prospective.json` | passed (1,875 exact, floats 1.4e-14) | passed, same classes and maxima |
| `core_cli compare signal` vs `gain-tv-next-signal.json` | passed (261 exact, floats 1.7e-11) | passed, same classes and maxima |

B against A, every leaf (`bench_p4_eigen.py diff`, `-03/diff-*.json`): no
non-float difference anywhere, and every leaf the diff set aside is in the
frozen exclusion list (timings, absolute paths, P8's timing digests).
Signal: 566 leaves, only 11 differ (`seconds`, `seconds_total` and
`acceptance_digest_core`), every float equal. LUNO solved and support, status audit: all leaves
equal. Prospective: 4,666 leaves, 109 volatile (`seconds`,
`seconds_total`, `native_response_seconds`,
`frozen_train_responses_sha256`), 404 floats differ by at most 1.8e-12
relative (the response diagnostics and the forecasts built on the
deltas, largest in `predicted_cost_removed_benefit`), no count, status or
decision differs. Section 6 and phase 2: only
timings and peak RSS (a float, 1e-3 relative) differ. The bench-f
`check.json` differs only in its timing parts (`parts_min`,
`parts_median`, `seconds`, load).

### 2. Per-call identity (pass)

| Recorded calls | Calls | Status counts | Status and ranks identical | max ‖Δδ‖∞ / max gain | `max_relative_step` margin to 0.1 |
| --- | ---: | --- | --- | ---: | ---: |
| section 6 survey `(H,0,0,0)` | 432 | 389 × 0, 43 × 3 | yes | 0 | n/a (step 0) |
| phase 2 survey | 432 | 389 × 0, 43 × 3 | yes | 0 | n/a |
| LUNO solved survey | 432 | 389 × 0, 43 × 3 | yes | 0 | n/a |
| LUNO support survey | 1,184 | as archived | yes | 0 | n/a |
| LUNO support status audit | 2,368 | as archived | yes | 0 | n/a |
| prospective stage | 72 | all 0 | yes | 1.9e-14 | factor 1.14 |
| signal stage | 9,069 | 9,034 × 0, 35 × 3 | yes | 1.3e-14 | factor 1.14 |

Each recording replays through both libraries with the recorded status
(`recorded_status_equals_a`), and the B-arm recordings replay identically
too. Largest relative diagnostic difference (signal): `max_relative_step`
1.6e-13, curvature diagnostics 2.7e-15–4.8e-15, ranks exactly equal. The
trust decision `max_relative_step ≤ 0.1` is identical on every call.

### 3. Rank decision at the 1e-10 cutoff, with margins (pass)

`p4_dump_audit` on every recorded call (both solvers, full and kept
matrices; `-03/audit-*.tsv`). Margins are factors relative to the cutoff
1e-10 λmax:

| Calls | Through eigen | Ranks equal | max \|λ_B − λ_A\| / λmax | smallest retained / cutoff | largest discarded / cutoff | most negative / cutoff |
| --- | ---: | --- | ---: | ---: | ---: | ---: |
| section 6 / phase 2 | 432 | yes | 3.1e-15 | 1.18e8 | 4.3e-6 | −3.9e-6 |
| LUNO solved | 432 | yes | 3.3e-15 | 1.18e8 | 3.6e-6 | −3.5e-6 |
| LUNO support + audit | 864 + 1,728 (320 + 640 stop at the gauge check, status 6) | yes | 3.7e-15 | 7.30e7 | 6.3e-6 | −4.9e-6 |
| prospective | 72 | yes | 2.9e-15 | 6.40e8 | 3.0e-6 | −3.0e-6 |
| signal | 9,069 | yes | 3.3e-15 | 6.40e8 | 4.0e-6 | −4.0e-6 |

**Smallest margin over all bins: the smallest retained eigenvalue is
7.3e7 times the cutoff (7.3e-3 λmax), and the largest discarded one is
1.6e5 times below it (6.3e-16 λmax); the nonpositivity check at −cutoff
has a margin of 2.0e5.** The discarded eigenvalues are the four gauge
directions (and, for status 3, the rank-deficient ones) at rounding level,
and the solvers agree to 3.7e-15 λmax, as the n·ε argument predicted. No
decision is near the threshold, so neither solver's rounding can flip one.

### 4. Speed (measured, A/B interleaved, load 18–32)

Rule: B's minimum below A's minimum by more than A's median-minus-minimum.

| Measurement | A min / median | B min / median | Speed-up (min) | Rule |
| --- | ---: | ---: | ---: | --- |
| survey block (`bench_core_f`, min of 7 per run, 3 runs; load 18–25) | 0.843 / 0.885 s | 0.339 / 0.377 s | 2.5× | met |
| of which the 432 `anchored_response` calls | 0.582 / 0.639 s | 0.114 / 0.124 s | 5.1× | met |
| single call, ctypes replay of the 432 section 6 calls (7 alternating passes, 3 runs; load 30–31) | 1.71 / 1.82 ms | 0.346 / 0.355 ms | 4.9× | met |
| section 6 pass excluding decode (`prototype_section6.py`; load 18–20) | 2.04 / 2.48 s | 1.27 / 1.35 s | 1.6× | met |
| of which `rank_survey` | 1.20 / 1.33 s | 0.477 / 0.490 s | 2.5× | met |
| signal stage wall (`core_cli signal`, 3 runs; load 25–31) | 67.2 / 78.9 s | 49.7 / 52.8 s | −17.5 s (min), −26 s (median) | met |
| prospective stage wall (3 runs; load 22–32) | 39.0 / 40.1 s | 28.1 / 39.8 s | – | met formally, not claimed |

The prospective stage makes only 72 calls (about 0.1 s of eigen work at
1.4 ms saved per call); its one fast B run is load, not P4, so no speed-up
is claimed there. The review's estimates (survey 0.73 → 0.28 s, signal
−11 s at quiet load) are met for the survey (0.34 s under load 22) and
exceeded for signal under load, where Jacobi's 2 ms calls suffer more from
contention. The remaining per-call cost (about 0.27 ms in the survey,
0.35 ms in the replay) is the projection, the residual check and the
ctypes boundary, not the eigensolver.

## Open items

- The pointing toy (`src/lib.rs:388,404`, `linalg::solve`) still uses
  Jacobi; switching it would move pointing archives and needs its own
  protocol.
- Section 6's `8_cost` criterion now passes at load 18–22 with QL but is
  still load-bound (failed once at load 31 with the recorder on).
- The rest of `anchored_step` (Vec-of-Vec projection, O(n³) matmuls) is now
  the larger share of a call; not changed here.

## Measurement log

Date for every row: 2026-10-30. Load is the 1-minute average.

| Tool run | Input | Wall | Peak RSS | Notes |
| --- | --- | ---: | ---: | --- |
| `uv venv -p python3.14` + `uv pip install -e '.[pointing,beam,test,imaging]' ruff maturin numcodecs` (public PyPI) | worktree | 14.2 s | 390 MB | |
| `cargo +1.93 build --release --offline` root, core; `maturin develop --release --offline` | base `4167141` | 5.9 s, 12.3 s, 0.5 s | 380 MB | load 9–18; A library frozen from this build |
| `cargo test` / `clippy` / `fmt` / `build` root crate, during implementation | branch | under 1 min each | – | first test run failed my own 2-station rank expectation (scalar model gives rank 8 of 12, as documented); test corrected; clippy `needless_range_loop` allowed on the EISPACK port |
| targeted pytest: `test_p4_eigen.py`, `test_flagging_influence.py`, `test_flagging_response.py`, `test_native_support_diagnostics.py` (B library) | 55 tests | 1.6 s | 78 MB | 55 passed |
| record suite `-02`, both arms (11 steps each) | archived inputs | A: section 6 11.8 s, check 43.5 s, phase 2 5.0 s, bench-f 14.4 s, LUNO solved 1.6 s, support 5.3 s, audit 6.1 s, prospective 40.2 s, signal 94.9 s; B: 9.3, 39.3, 3.3, 8.5, 1.2, 2.7, 2.8, 37.1, 55.9 s | 973 MB (signal) | load 29–33; `section6-check` exit 1 both arms (`8_cost` only) |
| identity analysis `-03`: 14 replays, 7 dumps, 7 `p4_dump_audit` runs, 15 diffs | `-02` recordings | replays 1–80 s (signal 80 s, 77 s), audits 0.5–30 s | 480 MB | load 28–34; all pass |
| timing suite `-04`: 6 × bench-f survey, 6 × section 6 + check, 6 × prospective, 6 × signal, interleaved; 3 × replay microbenchmark | archived inputs | 15.5 min in all; replays 9.6–10.5 s | 838 MB (signal) | load 18–32; Jacobi `section6-check` exit 1 (`8_cost`) 3 of 3, QL exit 0 3 of 3 |
| `bash tools/check-all.sh` (once, on `6d3199b` plus this document) | branch | 1,380 s (pytest 558 passed in 1,296 s) | not measured | load 31–41; overall PASS; log `outputs/p4-eigen-20261030-05/check-all.log` |

## For the coordinator

- **STATE.md, new entry.** "P4 survey eigensolver (big plan wave 2),
  2026-10-30 (`p4-eigen.md`): the anchored-response kernel's two 32 × 32
  eigenproblems per call now use Householder tridiagonalisation + implicit
  QL (`linalg::eigen_ql`) instead of classical Jacobi; Jacobi stays for the
  pointing toy and the A/B. All 13,989 `anchored_response` calls of the
  section 6 / phase 2 / LUNO surveys and the signal and prospective stages
  replay with identical statuses and ranks; every archive comparator passes
  as before (389 / 43 / 592, LUNO solved and support surveys leaf for leaf,
  signal and prospective comparators); the smallest margin to the 1e-10 rank
  cutoff over all bins is 7.3e7 above and 1.6e5 below. Under load 18–32:
  survey block 0.84 → 0.34 s, 1.7 → 0.35 ms per call, section 6 pass
  excluding decode 2.0 → 1.3 s (its `8_cost` criterion passes again at load
  18–22), signal stage 67 → 50 s (minimum), 79 → 53 s (median)."
- **tool-timings.md rows.** The measurement log above, prefixed "P4".
- **Upstream observations.** None for RATT (CARACal, caracal-pipeline,
  Stimela, QuartiCal) or non-RATT projects: the change is internal to
  rang's root crate; LAPACK (`numpy.linalg.eigh`) was not used in the kernel,
  keeping the root crate dependency-free.
- **Evidence to keep.** `outputs/p4-eigen-20261030-01/lib` (both libraries
  and their SHA256), `-03/` (replay JSONs, `audit-*.tsv`, `diff-*.json`,
  `identity.sh`), `-04/timings.tsv` and `replay-section6-*.json`, and
  `-02/timings.tsv` with the two arms' comparator receipts
  (`*-compare.json`, `section6-check/result.json`, `phase2/result.json`).
  The `calls-*.npz` recordings in `-02` (about 200 MB) can be dropped once
  merged; they are reproducible with `bench_p4_eigen.py record`.
