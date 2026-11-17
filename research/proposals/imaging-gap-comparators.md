# Proposal: measure the imaging-quality gap between GeMClean and RML/learned imagers

Status: **proposed, 2026-11-11 (digest [2026-11-11](../digests/2026-11-11.md), rank 3).
Nothing built or measured. A comparison study: it decides whether an imaging
method proposal is worth writing, and makes no novelty claim itself.**

## What exists

DF5-O ([df5o-deconv-oracles.md](../df5o-deconv-oracles.md), merged) froze a
simulated MeerKAT field with known truth, WSClean and pfb-imaging 0.0.11 as
oracles, and the tolerances A1 and A2. WSClean Högbom and pfb kclean/Clark meet
them; WSClean multiscale fails A1 on three sources; **pfb `sara` at the
release's recipe settings had not converged in 10 major cycles (residual rms
30σ)**. pfb-imaging needs Python < 3.14, so it runs in DF5-O's container. So
the question "does a sparsity-regularised imager beat CLEAN here?" is open, and
this proposal closes it on DF5-O's field and GeMClean's truth skies.

## Hypothesis

Run to convergence, a sparsity-regularised imager (pfb `sara`, MeerKAT-validated)
recovers extended emission with at least 2 × lower model error than GeMClean
multiscale, at no more than 5 × its wall time. If true, a GeMClean minor loop or
post step from that family is worth a proposal; if false, GeMClean (= WSClean
3.7) is the state of the art on these skies, and that is recorded.

Sources: pfb-imaging (Bester et al. 2024, cited in
[literature-2024-2026.md](../literature-2024-2026.md) 3.3); HyperAIRI (Tang et al.
2025, [arXiv:2510.15198](https://arxiv.org/abs/2510.15198)); R2D2 (cited in the
2026-10 scan; trained per telescope); MPoL as a small-case RML control
([arXiv:2502.00100](https://arxiv.org/abs/2502.00100)).

## Oracle and data

- **DF5-O's field and scorer**, unchanged (its A1, A2 and section 6.5 bounds).
- **GeMClean's truth skies:** S1-S3 and held-out H1-H4
  ([gemclean-heldout.md](../gemclean-heldout.md); H4 holds 30 points, 6
  Gaussians of FWHM 20-200″ and a 25-Gaussian curved tail) and M1
  ([g5-multiscale.md](../g5-multiscale.md)). New held-out skies are drawn and
  registered before any run.
- **Real data, runtime only:** the ESO 137-006 pilot.
- **Extra score:** model convolved with a common Gaussian beam against the
  truth convolved with it (relative L2, aperture fluxes on point and extended
  components). The scorer is validated on the truth itself (control ratio
  1.000 ± 0.002) before use; E1's scorer was not.

## Arms

| Arm | Tool and version | Settings |
| --- | --- | --- |
| G | GeMClean (main), multiscale, G4 masks | G5's settings |
| W | WSClean 3.7 | as G (parity control) |
| U | pfb-imaging 0.0.11 `sara` (PyPI's latest, checked 2026-11-11), DF5-O's container | DF5-O's recipe, then run to its `tol` (not capped at 10 major cycles), then tuned on S skies only within a stated budget |
| A | HyperAIRI or R2D2, only if released weights fit MeerKAT uv coverage | as released |

## Tolerance to freeze (proposed)

- **Gap found:** U (or A) relative L2 ≤ 0.5 × G's on at least 3 of 4 held-out
  skies, extended-aperture flux within 2 % of truth, DF5-O's A2 met, at ≤ 5 ×
  G's wall time (-j16, heavy lock).
- **No gap:** U within 0.8-1.25 × G on held-out skies. Recorded.
- **U does not converge** within 5 × G's time: recorded as DF5-O's open item
  answered ("not at comparable cost").
- **Parity:** W against G within G5's bounds, else the run is void.

## Expected cost

Medium. No rang code; DF5-O's container and recipe exist. G and W take minutes
per 2048² sky, U up to hours; about a day of heavy-lock time in all. A depends
on usable weights (basp-group R2D2-RI, last commit 2025-12-09).

## Owner decisions

1. Approve; choose whether arm A is in.
2. Whether "5 × wall time" is an acceptable cost bound for a quality claim.
