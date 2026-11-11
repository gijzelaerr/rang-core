# Proposal: self-calibration as one regularised problem (gains and image together)

Status: **proposed, 2026-11-11 (digest [2026-11-11](../digests/2026-11-11.md), rank 1).
Nothing built or measured. Owner approval needed before any work.**

## Problem it targets (measured)

`rang-core selfcal` ports CARACal's loop: image, then solve, then apply, repeated
([c5-selfcal.md](../c5-selfcal.md)). Against simulated truth it fails C5's frozen
T2 gate on development and held-out cases: round-1 phase median 2.0-2.5° against
1.0°, p95 10-17° against 1.5-3°, errors on the outer antennas. C5 shows
post hoc that the unmasked CLEAN model absorbs the gain errors on long
baselines; a model imaged from data corrected by the true gains meets every
limit (0.03° / 0.08°). CARACal's masks
([c5b-selfcal-masks.md](../c5b-selfcal-masks.md)) and an oracle mask from the
true sky do not fix it (phase p95 9.3-16.8°).

## Hypothesis

Solving gains and image as **one** objective, with a sparsity or positivity prior
on the image and a smoothness prior on the gains in time, stops the image
absorbing antenna-factorable errors that the loop's alternating steps let
through. On C5's held-out truths it meets C5's T2 gate where the loop does not.

Prior art (digest sections 2 and 7): Ikeda et al. 2024 (ALMA, PRIISM,
[arXiv:2412.03183](https://arxiv.org/abs/2412.03183)); Kim et al. 2024 and 2025
(resolve, VLBI, [arXiv:2407.14873](https://arxiv.org/abs/2407.14873),
[arXiv:2511.16556](https://arxiv.org/abs/2511.16556)); Comrade.jl (EHT). None is
tested on MeerKAT L band with a truth gate. Novelty is not claimed by porting
any of them; it would come only from meeting a gate the state-of-the-art loop
fails, at comparable cost.

## Oracle and data

- **Truth:** C5's simulated sets (`examples/c5_selfcal_sim.py`: 32 antennas,
  64 channels, seven scans of 16 integrations, `pa` and `delay` truths, gains
  constant over 8-integration blocks), development and held-out seeds as
  registered in C5 and C5b. Gate code: `examples/check_c5.py` (`check_c5.T2`),
  unchanged.
- **Held out, new:** two fresh seeds drawn and registered before any run, with a
  different sky (more extended flux) so the method is not tuned to C5's skies.

## Arms (matched effort)

| Arm | What | Role |
| --- | --- | --- |
| L | CARACal's loop, C5b's gated arm `m` (multiscale, CARACal masks) | state of the art as shipped |
| L+ | the loop with the best settings found in an equal tuning budget (rounds, solint, masks, `niter`), chosen on development cases only | tuned state of the art; guards against a weak baseline |
| J | joint objective (method), hyperparameters chosen on development cases only, same budget as L+ | the method |
| T | model from truly corrected data (C5 section 7) | upper bound, reported |

## Tolerance to freeze (proposed)

- **Success:** J meets every row of C5's T2 table on all held-out cases, and L+
  does not; or both meet it and J costs ≤ 0.5 × L+'s wall time.
- **Null:** J's phase p95 within 20 % of L+'s on held-out cases. Recorded as a
  negative result.
- **Image check:** J's restored image within G3's flux bounds of the truth
  sky, so the gains are not bought with a wrong sky.
- **Cost:** J's wall time ≤ 2 × L+'s at -j1 and -j16 on an idle host
  (heavy lock), else "quality at higher cost" and not a novelty claim.

## Expected cost

Medium-large. A JAX reference (the AGENTS.md JAX allowance covers the pointing
solver only; this needs an owner decision) or a Rust implementation over the
existing predict (`core/src/predict.rs`) and gain Jacobians (`core/src/solve.rs`,
`core/src/prox_solver.rs`). C5's sets are small (32 antennas, 64 channels), so
runs take minutes; tuning L+ is the largest cost.

## Owner decisions

1. Approve, and say whether a JAX reference path is allowed here.
2. Whether L+'s tuning budget is "N runs" or "N hours".
