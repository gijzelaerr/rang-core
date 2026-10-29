# Rang core, phase 2: full-Jones complex gain solver

Protocol frozen 2026-10-29, before any phase 2 solver code was written.
Status: **proposed**. This is phase 2 of the port plan in
[stack-consolidation-feasibility.md](stack-consolidation-feasibility.md)
section 9.4. It is a reimplementation of QuartiCal 0.2.7's `complex` term
(MIT, copyright 2022 Jonathan Simon Kenyon); under AGENTS.md it is not a
scientific contribution, and no archived result may change because of it.
The ported source file keeps QuartiCal's MIT notice.

## What is ported

QuartiCal's `quartical/gains/complex/kernel.py`, `gains/general/flagging.py`
and `gains/general/inversion.py` for one direction-independent full 2×2
`complex` term, four correlations, single chunk, one thread, no robust
reweighting and no MAD flagging, which is how every rang solve runs
([flagging_workflow.py:330-369](../python/rangtoy/flagging_workflow.py:330)).
Read from the installed 0.2.7 in `rang-flagging:local`:

- **Data flags.** A cell is flagged if any correlation's FLAG is set, its row's
  FLAG_ROW is set, its XX or YY DATA is exactly zero, or its XX or YY weight is
  exactly zero (`flagging/flagging.py` `_initialise_flags`).
- **Initial state.** Gains start at the 2×2 identity. A gain is flagged when no
  unflagged cell of its interval involves its antenna (`init_flags`).
- **Normal equations.** For antenna $p$ on baseline $pq$, with
  $X=MG_q^{H}$, `compute_jhj_jhr` accumulates the 4×4 complex matrix
  $\sum_c K_{ic}w_c\overline{K_{jc}}$ with $K=I\otimes_{\text{row}}X^{T}$
  (`a_kron_bt`) and $J^{H}r=(w\circ r)X^{H}$; antenna $q$ uses the conjugate
  transpose of the weighted residual and $X=M^{H}G_p^{H}$, with the **same**
  per-correlation weight order as $pq$. That last point is a QuartiCal
  property that matters only when the XY and YX weights differ; the port
  reproduces it.
- **Update.** Each 4×4 system is solved by conjugate gradients (at most four
  steps, stop when $r^{H}r<10^{-30}$), warm-started from the previous update
  (`invert_factory`, generalised). On iterations with an even index the update
  is halved in place before it is added; flagged gains are reset to identity
  (`finalize_update`).
- **Convergence and gain flags.** The relative squared change, its trend and
  the soft/hard flag ladder with numbness 1e-6, the stop criterion
  $10^{-7}$ (rang's command) and stop fraction 0.99 (QuartiCal's default);
  `finalize_gain_flags` hard-flags points with trend above 1e-6 and clears
  soft flags (`gains/general/flagging.py`).
- **Not ported.** Other gain types, chains of terms, direction dependence,
  BDA resampling, multi-threaded resampling, robust reweighting, MAD flagging,
  propagation of gain flags into the data flags (rang sets
  `output.flags=false` and checks that FLAG is unchanged), and I/O.

## Inputs (frozen)

- **Fixture clean case.** `outputs/tv-response-wsl-20261029-01/clean`:
  `state.npz` (DATA, model, WEIGHT_SPECTRUM, antennas, times),
  `backups/clean-t2-f32-solve.npz` (the exact FLAG and FLAG_ROW written
  before that solve) and `trials/clean-t2-f32/diagnostics.npz` (QuartiCal's
  gains and validity) with `metrics.json`. Grid 2 integrations × 32 channels,
  50 iterations, stop criterion 1e-7.
- **LUNO slice.** The arrays of `outputs/luno-solve-20261029-02/work.ms`
  (DATA, MODEL_DATA, FLAG, FLAG_ROW, WEIGHT_SPECTRUM, ANTENNA1, ANTENNA2,
  TIME), exported once in the pinned container by
  `examples/export_ms_arrays.py` into a fresh `outputs/` directory, and
  QuartiCal's `solve/gains.npy` and `gain_flags.npy` from the same run
  (archived as [meerkat-luno-solved.json](results/meerkat-luno-solved.json)).
  Same grid and settings.

## Acceptance criteria (frozen)

These follow section 6 of the feasibility study, made specific to the two
inputs. On both inputs:

1. **Gain flags.** The flagged/unflagged state of every gain equals
   QuartiCal's exactly (LUNO `gain_flags.npy != 0`; fixture `~gain_valid`).
2. **Gains.** On every gain QuartiCal leaves unflagged, the maximum absolute
   difference of each complex entry is ≤ 1e-6. The same maximum for the
   baseline products $G_pG_q^{H}$ over unflagged pairs is ≤ 1e-6. The
   number of entries differing by more than 1e-10 is reported, not gated.
3. **Iterations and convergence.** The iteration count equals QuartiCal's
   (LUNO `conv_iter` 50) and the converged fraction equals `conv_perc` to
   1e-12 (LUNO 0.9833234067897558). The fixture's iteration count and
   fraction are not archived; they are reported, not gated.
4. **Residual statistics at the solved gains.** The phase 1 fused pass at the
   Rust gains gives split losses equal to the fused pass at QuartiCal's gains
   to 1e-9 relative (fixture: train, validation and test; LUNO: the
   train-cell loss over the TRAIN cells of the rank survey).

On the fixture only:

5. **TV.** Raw and reference-polar TV totals at the Rust gains equal
   `metrics.json` (`raw_tv` 0.2673258258969277, `tv` 0.14743687007256856)
   to 1e-9 relative, using `rangtoy.flagging.gain_tv` with the archived
   scale.

On LUNO only:

6. **Rank survey.** `examples/survey_luno_solved.py`'s classification at the
   Rust gains is exactly 389 fully identified (status 0), 43 underidentified
   (status 3) and 592 bins without TRAIN data.

Both:

7. **No side effects.** As phase 1 criterion 6: inputs unchanged in size and
   modification time, `git status --porcelain` unchanged, and nothing written
   but the receipt.
8. **Cost (gated, from section 6 criterion 8).** On LUNO, the Rust solve of
   50 iterations takes ≤ 2.0 s wall single-threaded, and a process that
   loads the exported arrays, solves and runs the fused pass peaks at
   ≤ 200 MB RSS, measured with `/usr/bin/time` and logged in
   `tool-timings.md`. QuartiCal's measured times on the same input are 28.3 s
   cold and 3.6 s warm.

A failure of any criterion is recorded here with its numbers and is not
hidden. The phase is reported as passed only if criteria 1–8 pass as frozen.
