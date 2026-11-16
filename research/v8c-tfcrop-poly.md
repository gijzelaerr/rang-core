# V8c tfcrop: CASA's piecewise-polynomial template, a proposal

Issue #8, after [v8-tfcrop.md](v8-tfcrop.md) (closed 2026-11-16, H failed
as frozen; 7 of 21 informative development cases after three gate runs).
Branch `v8c-tfcrop-poly` from `v8-tfcrop` `1b760e2`, written 2026-11-16
before any new probe and before any new tfcrop code.

**Status: proposed (frozen at this commit).**

## 1. Hypothesis and what is not claimed

- **HP (identification).** CASA 6.7.6.14's tfcrop band template F (the
  robust fit of the time-mean spectrum under `freqfit='poly'`, and of the
  channel-mean time series under `timefit='poly'` by transposition) is a
  rule that can be written down from probes alone and reproduces CASA's F
  on noisy averages to the precision the gate needs (about 1e-4 relative or
  better; v8-tfcrop.md section 7 puts the need at 6e-4 for noise 0.1 at
  cutoff 3).
- **HG (parity).** `rang.tfcrop` with that rule, and V8's identified pieces
  (D1, D3, D4; D2 and D5 as revised here), passes G1-G4 (section 5) on every
  informative development case, and then on every informative held-out case
  at its one comparison.
- Not claimed: novelty (a reimplementation is not novelty, `AGENTS.md`);
  better flagging than Tricolour or AOFlagger; speed.

## 2. What V8 left, and what is not taken as settled

Settled in V8 and reused: D1 (per-row statistic), D3 (time = transposed
frequency), D4 (window statistics), pre-flagged input, E1 (extension over
all correlations), CASA's invariance to an amplitude scale (b08).

V8 ruled out, on plane counts only: float32 normal equations, a different
abscissa, a different stage schedule, two-sided clipping, refitting after
flagging. A plane count (planes equal to CASA) is a blind score: it says a
model is wrong, not how. Because this note measures F directly (section 4),
**these are re-tested against the measured F, not carried over**. V8's R1
readout reached only about 1e-3; a likely cause is that its row sd was made
mostly of the misfit itself (the non-test cells were the bare band), so the
readout and the quantity read were coupled. Section 4's readout removes that
coupling.

Remaining failures this note targets: syn-noise T1/T3/T4/T5 (precision 0.914,
recall 0.756 at T1), A1 (precision 0.55-0.73), syn-rfi T4-T7 (G1/G2 margins).

## 3. Hypotheses about the template (each tested in section 4)

Notation: A the average spectrum over valid channels, F the template, r the
residual (A − F, or A/F − 1), S the set of channels a fit uses.

- **T-a, function of A.** F depends on the plane only through A and the
  validity of each channel (not on the row structure). Tested first (control).
- **T-b, family.** With `maxnpieces=1`, F is exactly one polynomial over the
  band: degree 3 (documentation: "third-order polynomials in each piece").
- **T-c, piece count and boundaries.** With `maxnpieces=k`, F is k cubics
  on contiguous pieces; edges at round(j·n/k), at floor, at ceil, or over
  valid channels only; for n not divisible by k, which rounding.
- **T-d, joins.** Pieces independent (discontinuous at joins), or continuous
  in value and/or slope, or sharing a sample, or blended.
- **T-e, stage schedule.** The fit "begins with a straight line fit across
  the full range, and gradually increases to 'maxnpieces' number of pieces"
  in up to 5 iterations: the piece count and degree of each stage
  (candidates: 1 line then k cubics; 1, 2, ..., k; geometric; by iteration
  index up to 5).
- **T-f, exclusion.** Which channels each stage keeps: one-sided (r ≤ N·σ)
  or two-sided (|r| ≤ N·σ); N fixed (2, 3, ...) or the cutoff; σ the rms of
  r about 0 or the sd about its mean, over the stage's kept channels or all
  valid ones; r absolute (A − F) or relative (A/F − 1).
- **T-g, iterations and stop.** Number of stages; stop when σ changes by
  less than 10 % (documentation) relative, or 0.1 absolute (as D1 found for
  the row rule), or a fixed count.
- **T-h, weighting.** Unweighted least squares; weighted by the number of
  valid times per channel; weighted by 1/A or 1/A² (a fit in relative
  terms); a fit in log A.
- **T-i, linear-algebra precision.** float32 against float64 accumulation,
  only if T-a to T-h leave a residual above the readout precision.

## 4. Probe design (all labelled probe; never gate cases)

Templates as V8 (`tfcrop_probe.py template`; 24 antennas, 276 baselines,
4 correlations = 1,104 planes per MS), with a longer template (more
integrations) where the readout needs more thresholds. CASA runs in
`rang-o-casa:6.7.6.14` on WSL from ext4 copies (`tfcrop_probe.sh`);
`flagdimension='freq'` (or `'time'` for the transposed probes),
`extendflags=False`. Outputs in `D:\rang\outputs\v8c-tfcrop-<date>`.

- **P0, readout calibration (exact-fit designs first).** One average A per
  group, shared by many planes; every plane's rows are mirrored pairs
  A(1 + v) and A(1 − v), so the time mean (and median) is A exactly. Every
  row carries a known alternating pattern ±e over all channels that sets its
  sd (one D1 pass: sd below 0.1), plus a few test cells at
  ±(cutoff·e·(1 + d)) on a linear ladder of d across planes and rows. A
  test cell is flagged where |(A/F)(1 + v) − 1| exceeds cutoff × the row sd,
  so the crossings bracket A/F at that channel; the misfit enters the sd at
  second order only, and the forward model computes the sd exactly for any
  candidate F. Measured F per group: the per-channel brackets inverted
  jointly with the row sd (iterated). First on A = exact cubics, lines and
  piecewise cubics, where any fit reproduces A: the readout must return
  F = A to its stated precision before it is used on anything else.
- **P0c, control (T-a).** The same A with two different row structures
  (the readout rows, and Gaussian mirrored rows as V8's NA) must give the
  same F, read by the readout planes and checked by forward modelling the
  Gaussian planes.
- **P1, single piece on noisy A (T-b, T-f, T-g, T-h).** `maxnpieces=1` on
  A = smooth band × (1 + η·g), η in {1e-3, 3e-3, 0.01, 0.03}, with and
  without positive spikes. Is F one cubic to readout precision? If so, is
  it the least-squares cubic of some kept set? Scan the T-f/T-g/T-h space
  against the measured F; if no kept set reproduces it, test weights.
- **P2, influence.** A = exact cubic with one channel perturbed by δ (small
  positive, small negative, large positive): ΔF over the band gives the
  support of a channel's influence (piece extents, coupling at joins), the
  symmetry of the response (plain against weighted least squares) and the
  exclusion's sidedness.
- **P3, pieces (T-c, T-d, T-e).** `maxnpieces` 2, 3, 7 (and 4, 5, 9 if
  needed) on n = 256 and one n not divisible by the counts (for example
  250): fit exact cubics to the measured F over sliding windows to locate
  the breakpoints; check continuity at the joins; then the staged schedule
  against noisy A.
- **P4, time direction.** One transposed readout (`timefit='poly'`,
  `flagdimension='time'`) as confirmation of D3 for the polynomial.
- **P5, proxy check (guards the gate runs).** Fresh-seed N-type planes
  (V8's N1 recipe, `syn-noise`-like bandpasses, noise 0.1; seeds not used
  before, chosen at the time of the run and recorded) under `freqfit='poly'`
  with `maxnpieces` 1 and 7, `freqfit='line'`, and CARACal's call (T5).
  **No development gate run is spent until the model reaches precision and
  recall ≥ 0.98 of CASA's added flags on every P5 arm.** P5 is a guard, not
  a gate; its seeds are probes, never gate cases.

## 5. Data, split and gate (frozen)

- **Development cases:** V8's 26 cases (section 3 of v8-tfcrop.md:
  `syn-noise`, `syn-rfi`, `a1`, `luno`, arms T1-T8 as V8b section 4.1),
  against the same CASA outputs (`D:\rang\scratch\v8b-20261113\casa-02`).
  They were opened in V8 and remain development cases.
- **Held-out cases (opened once, after the development gate passes):**
  (i) V8's held-out set, never run under tfcrop by V8b, V8 or this note:
  `eso137-ho` (V8b amendment 1), `luno-ho2` (V8b amendment 3), the five
  public SKA fixture MSs (`outer_scans.zip`, sha256 `d4dae56f…144f`), arms
  T4 and T5; (ii) new synthetic cases from V8b's `build_tfcrop` recipe with
  seeds frozen here and never generated before this commit: `syn-noise-ho`
  (seed 20261171, no RFI) and `syn-rfi-ho` (seed 20261172, RFI), arms T1,
  T4 and T5.
- **Gate (carried over from V8 and V8b section 5.1 unchanged).** A case is
  one (input, arm); cells are FLAG's (row, channel, correlation) cells;
  A = cells flagged after the arm and not before. G1 FLAG equal on ≥ 99.9 %
  of cells; G2 per baseline |rang − CASA| flag fraction ≤ 1e-3; G3 precision
  and recall of rang's A against CASA's A each ≥ 0.98; G4 FLAG_ROW equal on
  every row. A case is informative when CASA's A holds at least 0.01 % of the
  cells; uninformative cases are reported and do not count.
- **Scope of the gate.** Every informative development case counts against
  HG, whatever the cause of a failure (the template, D2's open points, D5's
  open cases or anything else); a failure is diagnosed per case and recorded,
  but no case is excluded after the fact.

## 6. Decision rule, budget and stop rule (frozen)

- **HP is met** when, on the probes of section 4, the written rule
  reproduces the measured F within the readout precision on P0-P3 and P5
  passes; **not met** otherwise, with the closest rule and its residuals
  recorded.
- **HG passes** when every informative development case passes G1-G4 within
  at most **three development gate runs**, and then every informative
  held-out case passes at its one comparison. A held-out failure stays a
  failure here; a later fix and rerun are labelled post hoc.
- **Budget.** Probes are not rationed by count. Identification ends at the
  end of 2026-11-17 (two working sessions, as V8), or earlier when the rule
  is identified. No gate run before P5 passes.
- **Null branch (HP not met by the budget):** no gate run is spent;
  `rang.tasks.flagdata` keeps refusing `mode='tfcrop'`; the measured F per
  probe group, the readout precision, every rule tested and its residual
  against the measured F are recorded in section 8; the held-out cases stay
  closed.
- **Miss branch (HP met, HG fails on development):** the per-case G1-G3
  numbers and the diagnosis are recorded; tfcrop stays refused; held-out
  closed.
- **Pass branch:** the held-out cases are opened once. If they pass, a Rust
  kernel in `core/` (equal to the NumPy reference on every probe plane) is
  in scope, then `rang.tasks.flagdata` accepts tfcrop as v8-tfcrop.md
  section 5's pass branch describes. **No Rust kernel before the held-out
  cases pass.**
- Development differences are fixed in rang's code, never in the gate. Any
  change to sections 1-6 after this commit is a dated amendment labelled
  post hoc.

## 7. Method and provenance (clean room)

- Sources: casadocs (the `flagdata` task page and the "Mode tfcrop" text),
  the version-exact `casatasks.flagdata.__doc__` of the 6.7.6.14 image
  (`D:\rang\outputs\v8-tfcrop-20261116\flagdata-doc.txt`), and CASA's
  behaviour on probe MSs. No CASA source and no port derived from it is
  read; nothing is written from recalled CASA internals. A choice that
  cannot be tied to a documentation sentence or a probe is a hypothesis and
  is tested before it is used.
- Every process (CASA, analysis sweeps, pytest, gate runs) runs under
  `python C:\Users\gijsm\Github\rang\tools\heavy_lock.py run --slots 1
  --mem <G> -- <cmd>`, without exception.
- Walls in `research/tool-timings.md`; status in `outputs/status/v8c-tfcrop.md`.

## 8. Results (filled in as work proceeds)

(empty at the freeze)
