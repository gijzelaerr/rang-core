# Proposal: measure the imaging-quality gap between GeMClean and RML/learned imagers

Status: **proposed, 2026-11-11 (digest [2026-11-11](../digests/2026-11-11.md), rank 3).
Nothing built or measured. A comparison study: it decides whether an imaging
method proposal is worth writing, and makes no novelty claim itself.**

## Hypothesis

On MeerKAT L-band skies with known truth, a sparsity-regularised imager
(pfb-imaging's uSARA, MeerKAT-validated) recovers extended emission with at
least 2 × lower model error than GeMClean multiscale, at no more than 5 × its
wall time. If true, a GeMClean minor loop or post step from that family is
worth a proposal; if false, GeMClean (= WSClean 3.7) is the state of the art
here, and that is a recorded result.

Sources: pfb-imaging (Bester et al. 2024, in
[literature-2024-2026.md](../literature-2024-2026.md) 3.3; its recommendation 12,
now actionable because GeMClean deconvolves); HyperAIRI (Tang et al. 2025,
[arXiv:2510.15198](https://arxiv.org/abs/2510.15198)); R2D2 (cited in the 2026-10
scan; needs training per telescope); MPoL as a small-case RML control
([arXiv:2502.00100](https://arxiv.org/abs/2502.00100)).

## Oracle and data

- **Truth skies:** G2-G5's simulated skies with known components: S1-S3 and
  held-out H1-H4 ([gemclean-heldout.md](../gemclean-heldout.md)), M1
  ([g5-multiscale.md](../g5-multiscale.md)); H4 and M1 hold Gaussians and an
  arc. The skies are fixed; new held-out skies are drawn before any run.
- **Real data, runtime and visual only:** the ESO 137-006 pilot.
- **Score:** the model convolved with a common Gaussian beam against the truth
  convolved with the same beam: relative L2, flux in apertures on point and
  extended components, and peak residual. The scorer is validated on the truth
  itself (control ratio 1.000 ± 0.002) before use, which E1 lacked.

## Arms

| Arm | Tool and version | Settings |
| --- | --- | --- |
| G | GeMClean (this branch's main), multiscale, G4 masks | G5's settings |
| W | WSClean 3.7 | same as G (parity control) |
| U | pfb-imaging 0.0.11 (PyPI), uSARA | defaults, then tuned on S skies only |
| A | HyperAIRI or R2D2, only if released weights fit MeerKAT uv coverage | as released |

## Tolerance to freeze (proposed)

- **Gap found:** U (or A) relative L2 ≤ 0.5 × G's on at least 3 of 4 held-out
  skies, flux in extended apertures within 2 % of truth, at ≤ 5 × G's wall time
  (-j16, heavy lock).
- **No gap:** U within 0.8-1.25 × G on held-out skies. Recorded.
- **Parity:** W against G within G5's bounds, else the run is void.

## Expected cost

Medium. pfb-imaging installs from PyPI (Linux; WSL), no code in rang. Each
2048² sky takes minutes for G and W and up to hours for U; the arms total about a
day of heavy-lock time. A depends on finding usable weights (basp-group
R2D2-RI, last commit 2025-12-09).

## Owner decisions

1. Approve; choose whether arm A is in.
2. Whether "5 × wall time" is an acceptable cost bound for a quality claim.
