# Proposal: sidereal visibility averaging for repeated MeerKAT tracks

Status: **proposed, 2026-11-11 (digest [2026-11-11](../digests/2026-11-11.md), rank 4).
Nothing built or measured. A cost claim only; no novelty claim (the method is
published for LOFAR).**

## Hypothesis

For N calibrated tracks of one MeerKAT field, averaging visibilities across
tracks at equal sidereal time and matching (u, v, w) before imaging gives an
image within noise-level tolerance of imaging all N tracks together in
GeMClean, at about N times less gridding cost and data volume.

Source: de Jong et al. 2025, sidereal visibility averaging on LOFAR
([arXiv:2501.07374](https://arxiv.org/abs/2501.07374)), used for the 200 h
ELAIS-N1 image ([arXiv:2611.06152](https://arxiv.org/abs/2611.06152)). Deep
MeerKAT fields (LADUMA, MIGHTEE, MeerKAT pulsar fields) are multi-track, so
the cost case is MeerKAT-relevant; only the cost is claimed, never novelty.

## Oracle and data

- **Simulated truth:** N = 4 tracks of one field from `rang.simtruth`
  (`examples/a1_simtruth.py`), same sky, independent noise seeds, the same
  LST range, slightly different start LST (as real tracks), calibrated with
  the true gains so only averaging is tested.
- **Oracle:** GeMClean and WSClean 3.7 imaging the four MSs jointly.
- **Cost arms (the stronger baselines):** joint imaging with
  baseline-dependent averaging (WSClean 3.7 `-baseline-averaging`, applied
  per track), and per-track images stacked with inverse-variance weights
  (common in multi-track surveys; deconvolution per track). SVA must beat
  the cheapest of these at the quality bound, not only plain joint imaging.
- **Real data:** only if the owner names a public multi-track MeerKAT field;
  none is in hand.

## Tolerance to freeze (proposed)

- **Quality:** SVA image against the joint image: rms difference ≤ 0.1 × the
  joint image's noise, point-source fluxes within 0.5 %, restoring beam within
  1 %, with time and bandwidth smearing at the field edge reported against
  the joint image.
- **Cost:** imaging wall time and peak memory ≤ 0.4 × joint and ≤ 0.7 × the
  cheapest other cost arm that meets the same quality bound, at N = 4 (-j16,
  heavy lock), including the averaging step.
- **Null:** quality met but no cost win over the best cost arm, or quality
  not met at the outer field.

## Expected cost

Small to medium: an averaging step over the MS reader and writer
(`core/src/ms.rs`, `core/src/ms_write.rs`), simulation that exists, and a few
heavy-lock hours.

## Owner decisions

1. Approve as a cost study with no novelty claim.
2. Name a public multi-track MeerKAT field if a real-data arm is wanted.
