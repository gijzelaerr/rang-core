# Rang core, phase 1: fused statistics pass

Protocol frozen 2026-10-29, before any phase 1 code was written. Status:
**proposed** until the receipt below exists, then **measured**. This is
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
