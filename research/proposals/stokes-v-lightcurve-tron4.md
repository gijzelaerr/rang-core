# Proposal: Stokes V light curves and the TRON IV burst as a real-data control

Status: **proposed, 2026-11-25 (digest [2026-11-25](../digests/2026-11-25.md), rank 2;
issue [#62](https://github.com/gijzelaerr/rang-core/issues/62), v0.6.0).
Nothing built or measured. A correctness and detection claim on one
published event; no novelty claim.**

## Hypothesis

`rang-core lightcurve` with a Stokes V option, run on the SMGPS 1.28 GHz
pointing that contains PM J14111−6155 at 8 s and with `--channels-out`,
recovers the published burst: a minute-long, ~100 % circularly polarised
event peaking at 7.7 mJy, with a drifting, ~300 MHz-wide dynamic-spectrum
feature cutting off near 1.65 GHz, and no detection at the epoch four hours
later.

Source: Ramaila, Smirnov et al. 2026, TRON IV
([arXiv:2611.23447](https://arxiv.org/abs/2611.23447)). The earlier TRON
papers and the TRON ω Cen held-out set are in
[v1-timeseries-scope.md](../v1-timeseries-scope.md); no public TRON code
was found.

## Why now

#9's P1 and P2 ([ts-p1.md](../ts-p1.md), [ts-p2.md](../ts-p2.md),
[ts-p3.md](../ts-p3.md), [ts-p4.md](../ts-p4.md)) passed parity with WSClean
and the DFT, but the real-track bias gates were measured only with injected
pulses on ESO137 scan 10. `python/rang/lightcurve.py` is Stokes I only
(`core_weights.stokes_i`). The TRON IV burst is a published real event
with a light curve, a polarisation fraction and a dynamic spectrum to
compare against.

## Oracle and data

- **Step 1 (parity, simulated):** Stokes V light curves and dynamic spectra
  on a regenerated tsp2-held simulation with V-polarised injections, against
  WSClean 3.7 `-pol V -intervals-out -channels-out` and a NumPy DFT (the
  P2 gates D1, D2 with their frozen tolerances).
- **Step 2 (one blind read):** the SMGPS pointing of TRON IV, calibrated by
  `rang-core run`, read once after step 1 is frozen. Reference: TRON's
  published light curve and dynamic spectrum (literature only). TRON's sets
  come through the owner's SARAO token (owner decision 2 of
  [v1-timeseries-scope.md](../v1-timeseries-scope.md)); the observation ID
  and size were not checked.

## Tolerance to freeze

- **Step 1:** D1 and D2 at |Δ| ≤ 1e-3 σ per cell against NumPy and WSClean,
  as P2 froze them for Stokes I (P2 measured 2.3e-12 σ and 1.8e-6 σ).
- **Step 2 success:** a Stokes V detection ≥ 5 σ_snap at the source within
  ±2 intervals of TRON's peak time, peak flux within ±30 % of 7.7 mJy,
  |V|/I ≥ 0.7, and the dynamic-spectrum cut-off within ±100 MHz of
  1.65 GHz. **Null:** no ≥ 5 σ V interval. **Cost bound:** light-curve
  step ≤ 2× the Stokes I run on the same MS.

## Matched comparison

TRON's own result is the state of the art and is literature only; the
matched tool comparison is WSClean `-pol V -intervals-out` on the same
calibrated MS at equal intervals, against which rang must agree within
step 1's tolerance. No speed claim.

## Expected cost

Step 1: about 1 day (Stokes V in `lightcurve.py` and the Rust DFT sums, a
CLI flag, a CHANGELOG line). Step 2: fetch plus one `rang-core run` on a
single SMGPS pointing (size not checked), shared slots on nash.

## Owner decisions

- Whether #9 takes Stokes V before v0.5.0.
- Whether to ask TRON's authors for the observation ID and their light
  curve.
- Whether one published event counts as a held-out read under #9's rules.
