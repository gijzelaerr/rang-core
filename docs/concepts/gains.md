# Gains, solution intervals and TV maps

## The solver

`rang.core.solve_complex` is a port of QuartiCal 0.2.7's `complex` term: one
direction-independent full 2×2 complex gain per antenna and solution
interval, four correlations, starting from the identity, with QuartiCal's
data flagging and normal-equation inversion
({gh}`research/core-phase2.md`). Robust reweighting is off, as in every
campaign of this project. `rang.core_workflow.core_solve` wraps it with the
fused residual pass and returns the metrics, residuals and TV that the frozen
workflow returned, without a Measurement Set or a subprocess.

**Solution intervals** are a grid of time and frequency bins. The flagging
experiment froze 2 integrations × 32 channels and a cap of 50 iterations;
the tutorials let you change both and compare held-out error. A cap is not
convergence: tutorial 3's iteration sweep and QuartiCal issue 455 show the
chi-squared settling while gains keep moving.

## The unitary gauge

From `rang.notebook.gains.GAUGE_NOTE`:

```{include} ../_generated/gauge_note.md
```

The identifiability survey (`rang.notebook.survey`) counts, per gain bin, the
rank of the 32×32 real normal matrix against the `8n − 4` that a scalar model
can constrain for `n` active stations; a tree-shaped baseline graph falls
short ({gh}`research/flagging-luno-support.md`).

## TV maps

The gain total variation is the anisotropic Frobenius total variation of the
gauge-fixed gains along time and frequency, mapped per antenna, time bin and
frequency bin. It is the guidance `h` of the flagging policy
({doc}`flagging`): rough gains were hypothesised to mark bad data. The
experiment found that lower TV does not consistently mean better prediction,
and that legitimate smooth receiver phases change TV-guided decisions
({gh}`research/flagging-findings.md`).
