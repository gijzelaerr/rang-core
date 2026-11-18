# Proposal: restate GeMClean's WSClean comparisons against WSClean 3.8

Status: **proposed, 2026-11-18 (digest [2026-11-18](../digests/2026-11-18.md), rank 1).
Nothing built or measured. A re-measurement of existing results against the
current release of the oracle; no novelty claim. Owner approval needed.**

## Why now

WSClean 3.8 (2026-11-17,
[changelog](https://wsclean.readthedocs.io/en/latest/changelogs/v3.8.html))
changes the parts of WSClean that rang's archived comparisons rest on:
multiscale with "far fewer FFTs" and a residual update that no longer wraps
PSF sidelobes around the image; per-scale FITS masks
(`-multiscale-fits-mask`); wgridder recentering and an updated ducc0
wgridder. [pol-join-squared.md](../pol-join-squared.md) section 7 also
expects 3.8 to carry the theoretic-beam fix !1068 (different default
multiscale scales); the 3.8 changelog read on 2026-11-18 does not name it,
so confirming it in 3.8's source is step one. The GeMClean comparisons
cited below are against 3.7 (`rang-wsclean-native:3.7`, or nash's system
WSClean 3.7). Users will
compare GeMClean with the WSClean they install, which from now on is 3.8.

## Hypotheses (each decided separately)

- **H-speed.** GeMClean's `-j 16` lead in
  [gemclean-speed.md](../gemclean-speed.md) (faster on all seven skies,
  narrowly on H2 and H3) shrinks against 3.8; the `-j 1` result (WSClean
  faster on H1-H3) stays or widens. Expected: mostly from the multiscale and
  gridder changes, so largest on multiscale runs.
- **H-mask.** With `-multiscale-fits-mask` and the new residual update,
  WSClean 3.8 no longer diverges on RM and PM, the arms where 3.7 did
  ([gemclean-ms-mask.md](../gemclean-ms-mask.md)); GeMClean's confinement
  result (M1, C) is unchanged.
- **H-ms.** On the multiscale cases of
  [multiscale-flux-fix.md](../multiscale-flux-fix.md) and
  [df5o-deconv-oracles.md](../df5o-deconv-oracles.md), 3.8's model flux and
  residual measures move by less than the frozen tolerances of those notes,
  so their outcomes stand; if not, which outcomes change.

## Oracle (pinned)

WSClean v3.8 from source, `-DPORTABLE=OFF`, built like
`tools/oracles/wsclean-native/` (3.7), with EveryBeam ≥ 0.9.0 (3.8's
requirement) and the radler and ducc0 versions its source fetches (record the
commits). The 3.7 image stays for reproducing the archived results. Same
host and hold as the archived runs (see gemclean-speed.md), or
both versions rerun on one host if that is not possible.

## Data

The archived truth skies and settings, unchanged: S1-S3 and H1-H4 with the
gemclean-speed settings (threshold 100 µJy, Briggs 0.5, gain 0.1; GeMClean
at 1e-6 and coarse `-single -wgridder-accuracy 1e-4`); the ms-mask arms RM
(on H4) and PM (the pilot with Dms03's settings); the DF5-O simulated field.
No new data; held-out skies (H9-H16) only if a protocol change needs them.

## Tolerance to freeze (before any 3.8 run)

- Parity: 3.8 dirty image and PSF against 3.7 on S1 within the existing
  gridder tolerance of [df1-wgridder.md](../df1-wgridder.md) (where they
  should agree), or the difference recorded with its cause from the
  changelog.
- H-speed: "lead changed" if a median of three repeats moves by more than the
  3.7 runs' repeat spread on at least two skies.
- H-mask: divergence as defined in gemclean-ms-mask (radler's limit firing).
- H-ms: the frozen tolerances of the notes cited, unchanged.
- Cost bound: one evening's exclusive hold for speed; the rest shared.

## Expected cost

A 3.8 container build (about the 3.7 build's time, see
[tool-timings.md](../tool-timings.md)); about 2 h exclusive for the speed
table (seven skies, two thread counts, three repeats, five WSClean
settings); about 1 h shared for the mask and multiscale arms.

## Matched comparison (AGENTS.md novelty rule)

No novelty is claimed. The comparison is against the strongest current
baseline: WSClean 3.8 built for the host's CPU, with the tuned settings
already used against 3.7 (`minres`, `-mgain` 0.8/0.9/0.95) rather than
defaults. Any statement in the docs or README that GeMClean is faster than
WSClean is then re-stated against 3.8.

## Owner decisions

1. Approve the rerun, and whether 3.8 replaces 3.7 as the default oracle
   for new notes.
2. Whether results stated against 3.7 in the docs are re-worded once the
   3.8 numbers exist.
