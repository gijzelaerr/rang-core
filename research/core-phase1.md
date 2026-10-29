# Rang core, phase 1: fused statistics pass

Protocol frozen 2026-10-29 in `b928d2a`, before any phase 1 code was
written. Status: **implemented; measured: criterion 4 failed as frozen; post-hoc
criterion 4b passes** (archive [core-phase1.json](results/core-phase1.json)). This is
phase 1 of the port plan in
[stack-consolidation-feasibility.md](stack-consolidation-feasibility.md)
section 9.4. It is a reimplementation; under AGENTS.md it is not a scientific
contribution, and no archived result may change because of it.

## Scope

A new Rust crate in `core/` (package `rang-core`, GPL-3.0-or-later) with a C
ABI loaded through ctypes, like the existing kernels. PyO3 is deferred: the
existing kernels use ctypes, the checks build offline, and ctypes needs no new
crates. The crate depends on the root `rang-toy` crate as an rlib for the
existing normal-equation, TV and trend kernels; files in `src/` are not
edited, because their hashes are recorded in result receipts.

One pass over the visibility cells computes, for given gains on a
time × frequency gain grid:

- the prediction $\hat V_{pq}=G_p M_{pq} G_q^{H}$ and residual
  $r=V-\hat V$, with the model either a stored per-cell column or a scalar
  spectrum $S(\nu)I$;
- per split (train, validation, test) the sum and count of the per-cell
  weighted squared residual $\tfrac14\sum_c w_c|r_c|^2$, and the count of
  cells whose prediction is invalid (either antenna's gain invalid);
- per baseline, the whitened residual amplitude
  $a=\|\sqrt w\circ r\|_F$ on eligible (train) cells, from which the robust
  log-amplitude score $z$ of `residual_features` is computed;
- per gain bin and antenna, the antenna-diagonal Gauss–Newton blocks
  $\operatorname{Re}(J_p^{T}WJ_p)$ (8×8) and $\operatorname{Re}(J_p^{T}Wr)$
  (8), for any number of antennas. This is the general path the solver in
  phase 2 will use. The full 32×32 four-station block is computed only on the
  validation path, by the existing `rang_toy::response::normals`.

Ingest stays in Python for phase 1 (`state.npz`, `diagnostics.npz`); zarr
ingest in Rust is a later step of phase 1 with its own check.

## Inputs (frozen)

- Fixture clean case: `outputs/tv-response-wsl-20261029-01/clean/state.npz`
  and `trials/clean-t2-f32/diagnostics.npz` (gains 7 × 128 × 4 × 2 × 2,
  complex128, grid 2 integrations × 32 channels), with
  `trials/clean-t2-f32/metrics.json`. These are the host's reproduction of
  `results/gain-tv-response.json`.
- LUNO slice: `outputs/luno-support-20261029-01/extract/group1/*.npy` and
  `outputs/luno-solve-20261029-02/solve/gains.npy`, `gain_flags.npy`, as used
  by `examples/survey_luno_solved.py`.

Data are cast to complex128 before any arithmetic, as NumPy does in
`flagging_workflow.solve` (complex64 DATA minus a complex128 prediction).

## Acceptance criteria (frozen)

1. **Residuals.** On the fixture, residuals equal `diagnostics.npz`
   `residuals` on every cell: maximum absolute difference ≤ 1e-12 Jy and
   relative ≤ 1e-12 where |r| > 1e-6.
2. **Split losses.** Train, validation and test losses equal `metrics.json`
   `losses` to 1e-12 relative. The loss is the mean over split cells of the
   per-cell mean over four correlations of $w|r|^2$; a split containing an
   invalid prediction or a non-finite value reports no loss (None), as in
   [flagging_workflow.py:455-464](../python/rangtoy/flagging_workflow.py:455).
   Invalid-prediction counts equal `metrics.json` exactly.
3. **MAD scores.** $z$ equals `rangtoy.flagging.residual_features` on the
   same whitened residuals and train mask to 1e-12 absolute. This oracle is
   the Python function, not an archived file, because $z$ is not archived.
4. **Normals from fused residuals.** On the fixture, the existing
   `training_normals` kernel fed with the fused residuals gives the same
   32×32 blocks $\mathbf H_b$ and vectors $\mathbf b_b$ as when fed with the
   archived residuals, to 1e-13 relative (maximum entry difference over
   maximum entry). Cells are the train cells whose prediction is valid.
5. **Antenna-diagonal blocks.** Each per-antenna 8×8 block from the fused
   pass equals the matching diagonal block of the full 32×32 normals to
   1e-13 relative, and the 8-vector equals the matching slice of
   $\mathbf b$. Checked on the fixture and on the LUNO slice at the solved
   gains. LUNO extract arrays carry no DATA, so DATA is taken as zero there
   and both paths see the same residual $r=-\hat V$.
6. **No side effects.** The pass writes no file; the validation script
   writes only its receipt in a fresh `outputs/` directory and a compact
   archive in `results/`.
7. **Cost (reported, not gated in phase 1).** Wall time and peak RSS of the
   fused pass on both inputs, measured with `/usr/bin/time` and logged in
   `tool-timings.md`, next to the NumPy and native-normals times it replaces.

Failure of any of 1–6 is recorded here with the numbers, not hidden; the
phase is not marked done until all pass.

## Measured result of the frozen run (2026-10-29)

Run `outputs/core-phase1-20261029-01`, with the core code as committed with
this section. The validator that ran was an earlier version of
`examples/validate_core_phase1.py` with criteria 1–6 only; the committed
version adds criterion 4b and the stronger side-effect check and changes
nothing else. Exit status 1, because criterion 4 failed.

| Criterion | Measured | Frozen limit | Outcome |
| --- | --- | --- | --- |
| 1 residuals | max 5.7e-14 Jy absolute; max 3.5e-13 relative where \|r\| > 1e-6; NaN positions identical | 1e-12 | pass |
| 2 split losses | train 2.0e-15, validation 4.2e-16, test 1.0e-15 relative; invalid-prediction counts equal | 1e-12 | pass |
| 3 robust scores | max 1.9e-14 absolute | 1e-12 | pass |
| 4 normals from fused residuals | $\mathbf H$ 0 relative; $\mathbf b$ **4.9e-11** relative to max\|b\| | 1e-13 | **fail** |
| 5 diagonal blocks | fixture and LUNO: $\mathbf H$ and $\mathbf b$ 0 relative (73,720 and 117,556 cells) | 1e-13 | pass |
| 6 side effects | the run directory held only `result.json` | – | pass, but the check was weak (see below) |

Criterion 4 tested only $\mathbf b$ in practice: $\mathbf H$ does not depend
on the residuals, so its agreement is automatic.

**Diagnosis (measured after the failure).** The criterion is ill-posed at a
converged solution. $\mathbf b=\operatorname{Re}(J^{T}Wr)$ is the gradient,
which is close to zero at the optimum, so its largest entry (0.43) is
tiny compared with the terms that cancel to produce it. The fused and NumPy
residuals on these cells differ by at most 3.7e-15 Jy, which is rounding in
the 2×2 products. $\mathbf b$ is linear in the residual: the kernel applied to
the residual difference reproduces the $\mathbf b$ difference (1.8e-11 against
2.1e-11). Dividing by max\|b\| therefore magnifies rounding by the
cancellation factor, not an implementation error.

The weak criterion-6 check confirmed only that the run directory was empty
before the receipt was written. The rerun also compares sizes and
modification times of every input file and `git status --porcelain` before
and after.

## Post-hoc criterion 4b (defined after the frozen run failed)

This criterion was written after seeing the failure above and is labelled
post-hoc everywhere it is reported. It keeps the frozen constant, 1e-13; only
the scale changes, from max\|b\| to a bound that does not vanish at the
optimum. By Cauchy–Schwarz, for each bin and parameter $i$,

```math
|b_i|=\Big|\sum_k w_k J_{ki} r_k\Big|
\le\sqrt{\sum_k w_k J_{ki}^2}\sqrt{\sum_k w_k r_k^2}
=\sqrt{H_{ii}\,\chi^2_{\text{bin}}},
```

where $k$ runs over the real residual rows of the bin's selected cells and
$\chi^2_{\text{bin}}$ is their weighted squared residual.

4b. $\mathbf H$ as in criterion 4 (1e-13 relative), and
$\max_{\text{bin},i}|\Delta b_i|/\sqrt{H_{ii}\chi^2_{\text{bin}}}\le10^{-13}$
over entries with a positive bound, with $\chi^2_{\text{bin}}$ from the
archived residuals.

The rerun goes to a fresh `outputs/core-phase1-20261029-02`. The phase is
reported as "implemented; measured: criterion 4 failed as frozen; post-hoc 4b
…" with the rerun's outcome, never as "phase 1 passed".

## Measured result of the rerun (2026-10-29)

Run `outputs/core-phase1-20261029-02` with the code committed in `ec67abd`.
Archive: [core-phase1.json](results/core-phase1.json).

- Criteria 1, 2, 3, 5 and 6 pass with the same numbers as the frozen run.
- Criterion 4 fails again as frozen (b 4.9e-11 relative to max\|b\|). The
  code is deterministic and unchanged, so this is expected.
- Post-hoc criterion 4b passes. The largest
  $|\Delta b_i|/\sqrt{H_{ii}\chi^2_{\text{bin}}}$ is 2.9e-15, against 1e-13.
  The largest bound is 1.9e5, against max\|b\| = 0.43.
- The stronger side-effect check passes: 13 input files have unchanged sizes
  and modification times, `git status --porcelain` is unchanged, and the run
  directory held nothing before the receipt.
- Cost (reported, not gated): the whole validator took 1.08 s and 391 MB peak
  RSS. In-process, the fused pass took 0.057 s on the fixture, against
  0.149 s for the NumPy residual and split-MSE path it replaces. On LUNO it
  took 0.046 s, against 0.132 s for the existing full-normal kernel with its
  NumPy preparation. These are in-process timings, not the end-to-end
  speedup that section 6 of the feasibility study measures.

Phase 1 is reported as "implemented; measured: criterion 4 failed as frozen;
post-hoc 4b passes". Phase 2 builds on these blocks.
