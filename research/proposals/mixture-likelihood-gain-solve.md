# Proposal: RFI as a latent mixture inside the gain solve

Status: **proposed, 2026-11-11 (digest [2026-11-11](../digests/2026-11-11.md), rank 2).
Nothing built or measured. Owner approval needed; it touches the closed
flagging line (see "Why this is not a reopened flagger").**

## Hypothesis

A gain solve whose likelihood is a two-component mixture per visibility (clean
noise, or contaminated with a broad component and a per-antenna, per-interval
prior weight π) gives lower gain error against truth than (a) flagging first
with Tricolour and then solving, and (b) QuartiCal's robust (Student-t
reweighting) mode, on data with known RFI. The E step is a posterior weight per
visibility; the M step is the existing weighted QuartiCal update.

Source: Leeney et al. 2026 ([arXiv:2606.16525](https://arxiv.org/abs/2606.16525)),
curation inside the likelihood; Ducharme et al. 2026
([arXiv:2609.26904](https://arxiv.org/abs/2609.26904)); QuartiCal robust mode
(Mbou Sob et al. 2019, cited in [literature-2024-2026.md](../literature-2024-2026.md) 1.1).

## Why this is not a reopened flagger

Gain-TV flagging, F1, F2 and F3 tried to produce better **flags**. This changes
the **solve**: no flag is written, and the gain error against truth is the only
gated quantity. It is a likely null against arm R (a mixture weight and a
Student-t weight are both reweighting schemes); the stub is ranked second
because the test is cheap and the truth exists.

## Oracle and data

- **Truth:** F-SIM (`python/rang/f2flag_sim.py`, `examples/f2_simulate.py`):
  simulated MeerKAT L-band calibrator observations from `rang.simtruth` with
  known RFI masks and known gains; F2's Q3 metric (gain-product error, ratio to
  T) is the measure ([f2-flagger.md](../f2-flagger.md)).
- **Held out:** F2's held-out drifting carrier and F2/F3's LUNO 1934−638
  injections (real data, injected RFI with known masks); seeds registered
  before any run.
- **Oracles:** QuartiCal 0.2.7 (rang's port equals it; `solver.robust` true and
  false), Tricolour 0.2.1 through rang's port.

## Arms

| Arm | Flags | Solve |
| --- | --- | --- |
| T | Tricolour 0.2.1 | QuartiCal, robust off (rang's default chain) |
| R | none | QuartiCal robust (Student-t) |
| TR | Tricolour | QuartiCal robust |
| M | none | mixture (method) |
| TM | Tricolour | mixture |
| O | truth mask | QuartiCal, robust off (upper bound) |

## Tolerance to freeze (proposed)

- **Success:** M or TM has a held-out gain-product error ≤ 0.90 × the best of
  T, R and TR (median over antennas and intervals), with p95 no worse, at a
  solve time ≤ 1.5 × R's at -j1 and -j16.
- **Null:** within ±5 % of the best of T, R and TR. Recorded as "equivalent to
  existing reweighting".
- **Signal check:** the calibrator flux after F bootstrap within C2d's class B
  of truth, so down-weighting does not bias the scale.

## Expected cost

Small to medium. A weight hook in the solver's per-interval update
(`core/src/solve.rs`) and an E-step kernel; F-SIM and the LUNO injections
exist. Runs are minutes per case; the full grid is a few hours under the
heavy lock.

## Owner decisions

1. Approve, given the flagging line is closed.
2. Whether π is per antenna and interval (proposed) or per baseline.
