# Rang core, phase 3c-a: component sky prediction

Protocol frozen 2026-10-29 in `ec92311`, before any predictor or oracle code
was written. Status: **implemented; measured: the frozen run failed one
criterion through a validator error; after fixing it, every criterion
passes**. First step of phase 3c (the signal track needs it) and
the "prediction" component of phase 1 in
[stack-consolidation-feasibility.md](stack-consolidation-feasibility.md)
section 9.4. A reimplementation of codex-africanus 0.4.4
`africanus.rime.wsclean_predict` and its spectral model (BSD-3-Clause, notice
kept in the ported file); under AGENTS.md not a scientific contribution.

## What is ported

`wsclean_predict` and `africanus.model.wsclean.spec_model.spectra`, read from
the pinned `rang-flagging:local` image: for components with direction cosines
$(l,m)$, $n=\sqrt{1-l^2-m^2}$, Stokes I flux $I$, spectral coefficients $c_k$,
reference frequency $\nu_0$ and an ordinary or logarithmic polynomial,

```math
S(\nu)=\begin{cases}
I\exp\!\Big(\sum_k c_k\log^k(\nu/\nu_0)\Big) & \text{logarithmic},\\
I+\sum_k c_k(\nu/\nu_0-1)^k & \text{ordinary},
\end{cases}
\qquad
V(u,v,w,\nu)=\sum_s S_s(\nu)\,e^{\,2\pi i\nu(ul+vm+w(n-1))/c}\,G_s(u,v,\nu),
```

with $G_s=1$ for points and, for Gaussians with major and minor FWHM and
position angle, africanus's rotated, scaled exponential envelope. Africanus
compiles without `fastmath` (`africanus/util/numba.py`), so agreement close to
rounding is expected. Rang's NumPy `flagging_signal.spatial_templates` and
`flagging_sky.point_catalog_predict` are independent second oracles.

## Inputs and oracle step (frozen)

`examples/oracle_wsclean_predict.py` runs once in `rang-flagging:local`
(python-casacore and codex-africanus pinned there) into a fresh `outputs/`
directory. It reads `outputs/tv-response-wsl-20261029-01/clean/work.ms`
(UVW of the cross-correlation rows, FIELD phase centre, channel
frequencies 1024–3071) and writes, for three component sets, the inputs and
the africanus visibilities to one `.npz` with a receipt (hashes, versions,
timing):

1. **response**: the two components of `flagging_response.SOURCES` (a point
   and a circular Gaussian, logarithmic spectra), as the response stage
   predicts them;
2. **catalogue**: all 5153 components of the pinned SARAO PKS 1934−638
   catalogue (`outputs/flagging-sky-inputs`, SHA256 `b277bc6d…`), points with
   ordinary polynomials, $(l,m)$ from the phase centre as in
   `point_catalog_predict`;
3. **stress**: 64 seeded components, half points and half elliptical Gaussians
   with random position angles, offsets up to 1 degree, half logarithmic and
   half ordinary polynomials with three coefficients (seed 20261029).

The oracle step is timed and its output hashed before the Rust comparison.

## Acceptance criteria (frozen)

1. **Against africanus.** For every set, row and channel,
   $|V_{\text{Rust}}-V_{\text{africanus}}|\le10^{-12}\sum_s|S_s(\nu)|$.
2. **Against rang's NumPy oracles.** The response set's two per-source
   templates agree with `spatial_templates` times the spectra to the same
   bound; the catalogue set agrees with `point_catalog_predict` on three rows
   (first, middle and last cross row) to the same bound.
3. **Spectra.** The Rust spectra equal africanus `spectra` to 1e-13 relative
   for every component and channel.
4. **No side effects.** Inputs and the tracked tree unchanged.
5. **Cost (reported).** Rust and africanus wall times per set, logged in
   `tool-timings.md` (africanus includes Numba compilation; noted).

The step is reported as passed only if criteria 1–4 pass as frozen; any
failure is recorded with its numbers.

## Measured result (2026-10-29)

**Oracle step.** `outputs/core-phase3c-oracle-20261029-01`, run once in
`rang-flagging:local` (21.9 s with the container): 84 cross rows × 2048
channels of the fixture clean case, oracle SHA256 `557a48d5…`.
Africanus took 8.1 s for the
5153-component catalogue (second call; the first call of the response set,
2.9 s, includes Numba compilation).

**Frozen run** `outputs/core-phase3c-a-20261029-01`: criteria 1, 3 and 4 and
the catalogue part of criterion 2 passed, but the response part of criterion
2 failed with differences of the order of the flux itself. The cause was the
validator, not the predictor: it called `spatial_templates` with its default
source list, which is the signal stage's (different positions, fluxes and
widths), instead of the response stage's list that the oracle used. The
validator was corrected to pass the response sources, labelled in the code,
and nothing else changed.

**Rerun** `outputs/core-phase3c-a-20261029-02`: every criterion passes.
Archive: [core-phase3c-a.json](results/core-phase3c-a.json).

| Set | Components | Rust vs africanus | Spectra | NumPy oracle (max / bound) |
| --- | ---: | --- | --- | --- |
| response | 2 | bit-identical | bit-identical | 1.4e-03 |
| catalogue | 5153 | bit-identical | bit-identical | 3.4e-04 (three rows) |
| stress | 64 | bit-identical | bit-identical | – |

The bound is 1e-12 × Σ|S| per channel. The host-parsed catalogue gives the
same direction cosines as the oracle, bit for bit. Inputs and `git status`
were unchanged.

**Cost (reported).** The Rust predictor takes 8.3 s for the
catalogue, the same as africanus (8.1 s): it is
the same scalar loop, single-threaded. No runtime gain is claimed; the gain
is that prediction now runs in the core process without a column write.
