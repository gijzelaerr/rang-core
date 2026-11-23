# DD3c: pinning the facet flux scale with the catalogue fluxes

Issue #15, the last pinning option after [DD3b](dd3b-flux-pin.md), on branch
`dd3c-catalogue` (coordinator decision, 2026-11-23). Sections 1-4 are
frozen 2026-11-23, before any code that tests them.

Status: **proposed**.

## 1. Why

- In DD3's loop, facet d3's gain amplitude and its model flux traded off.
- DD3b's two pins did not fix this.
  - Normalising to mean |g| = 1 pins each facet at the convention.
  - Phase-only first cycles did not help: QuartiCal's DD `phase` diverges,
    and rang's own-gain variant left 11.8 % false flux.
- The remaining pin holds the start model's catalogue fluxes fixed. The four
  facet-centre sources keep their catalogue flux in every cycle. Their
  facet's gain amplitude is then fixed by them, because the model flux there
  can no longer move.

## 2. Arm C (frozen)

Everything is DD3's (data, start model M₀, grid, facets, `diag_complex` at
the frozen cap, the H5parm, WSClean with `-feather-size 0` and
`<name>-model-pb.fits`, the gates), with one change to the shared Högbom
rule:

- Peaks are not searched within ±2 pixels (a 5 × 5 box) of the four
  catalogue sources (M₀'s components).
- So no component is added there, and those sources keep their M₀ flux in
  every cycle.
- The rest of the rule is DD3's. That includes amendment A1: peaks are
  searched only at least 3 pixels inside the facets.

The arm runs in rang (R) and in QuartiCal + WSClean (O), and the same rule
is applied to each arm's own residual.

## 3. Gates (DD3's, unchanged)

- **L:** per cycle, the component lists are identical (fluxes within
  `1e-5 + 1e-4 |f|`), the gain products within 1e-5, the flags equal, and
  the residual within 1e-3 of the peak.
- **T1:** the median gain-product error is at most 3.72e-3.
- **T2:** the bright sources' model flux is within 2 % of the truth, and
  sources of at least 30 mJy within 10 %.
  - The bright sources' flux is pinned to the catalogue. Here the catalogue
    equals the truth, so T2's bright part passes by construction and is
    reported as such.
- **T3:** false flux is at most 1 %.

Reported, not gated: T1 per direction, and the median amplitude bias
`|P|/|P_true|` per direction.

## 4. Decision rule (named before any result)

- **Pin works:** L holds and T1 and T3 pass. T2's faint part must pass too.
- **Pin insufficient:** L holds and T fails. Record which part.
- **Parity failure:** L fails. Record the first differing quantity.

Not tested here: a catalogue with flux errors. On real data the pin
transfers catalogue errors to the facet gains, so its size on real data is
for DD4.

## 5. Measured result

Not yet measured.
