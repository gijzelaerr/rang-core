# DD3c: pinning the facet flux scale with the catalogue fluxes

Issue #15, the last pinning option after [DD3b](dd3b-flux-pin.md), on branch
`dd3c-catalogue` (coordinator decision, 2026-11-23). Sections 1-4 are
frozen 2026-11-23, before any code that tests them.

Status: **measured 2026-11-23: the pin works.** Gate L passes on every cycle, and T1, T2 and T3 pass in both arms: T1 3.57e-3 (limit 3.72e-3; unpinned 3.89e-3), false flux 0.61 %. Facet d3's amplitude bias falls from 2.46 % to 1.01 %. Recommendation for DD4 in section 6.

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

Run `D:/rang/outputs/dd3c-20261123-C`:
- `R/` and `O/cycle-0..4`, plus `compare.json`.
- Rang from `dd3b-pin`'s build at `34e70cd1`. Only the shared rule changed
  in this branch (`7678f4f6`). QuartiCal 0.2.7 and WSClean 3.7 as in DD3.
- Archive: [results/dd3c-catalogue-pin/](results/dd3c-catalogue-pin/).

**Gate L: pass at every cycle.**

| Cycle | components (R = O) | max \|ΔP\| | flags | residual (rel.) |
| --- | --- | --- | --- | --- |
| 0 | 69 | 1.6e-6 | equal | 1.8e-6 |
| 1 | 138 | 1.3e-6 | equal | 1.0e-5 |
| 2 | 126 | 1.2e-6 | equal | 4.5e-5 |
| 3 | 44 | 1.2e-6 | equal | 1.3e-4 |
| 4 | – | 1.4e-6 | equal | 1.5e-4 |

**Gate T: passes in both arms, with identical numbers.**

| Measure | DD3 unpinned | **DD3c catalogue pin** | limit |
| --- | --- | --- | --- |
| T1 median | 3.89e-3 | **3.57e-3** | ≤ 3.72e-3: pass |
| T1, d0 / d1 / d2 / d3 | 3.4e-3 / 2.2e-3 / 3.9e-3 / 2.5e-2 | 3.3e-3 / 1.7e-3 / 3.9e-3 / 1.2e-2 | – |
| amplitude bias `\|P\|/\|P_true\|`, d3 | 1.0246 | **1.0101** | – |
| T2 bright | 0.978 (d3) | 1.000 (pinned, catalogue = truth) | pass by construction |
| T2 faint (≥ 30 mJy) | 0.985-1.044 | 0.997-1.045 | pass |
| T3 false flux | 0.42 % | 0.61 % | pass |

**Outcome under section 4: the pin works.** Facet d3 is still the weakest
facet. Its error is 1.2e-2, against the complete-model solve's 6.9e-3, and
1 % of its amplitude bias remains. That remaining bias comes from the
facet's faint sources, whose flux still trades with the gains.

Cost (indicative): rang 5 cycles about 5 min. QuartiCal 65-88 s per cycle.

## 6. Recommendation for DD4

**Take arm C to real data**, with these settings:
- `diag_complex` DD at the frozen cap (150 iterations, 1e-7, 0.99);
- per-facet model columns, facet predict and facet imaging (WSClean
  equivalent `-feather-size 0`);
- the shared Högbom rule, with the facet-centre sources' fluxes held at
  their catalogue values.

It is the only variant tested that passes the truth gates. Like DD3, it
matches QuartiCal + WSClean cycle for cycle. The other variants fail:

| Variant | Why it fails |
| --- | --- |
| Unpinned (DD3) | lets the faintest facet drift (T1 and T2 fail) |
| Normalised (DD3b N) | pins to a convention, not the sky |
| Phase-first (DD3b P) | diverges in QuartiCal |
| Phase-first, own gain (DD3b P′) | leaves 12 % false flux |

**Field: ESO137**, if the owner approves the external catalogue for it.
- The catalogue pin needs credible apparent fluxes for each facet's
  brightest source.
- ESO137 already needs a deeper field model from an external catalogue
  before beam and pointing can be reopened (STATE). That is an open owner
  decision, and one catalogue would serve both.
- On real data the pin moves any catalogue flux error into that facet's gain
  amplitude. The catalogue fluxes must be the apparent ones, with the
  primary beam applied, or the DD gains absorb the beam.

If the external catalogue is not approved, use **E2-N** with the pinned
fluxes taken from its own DI self-calibrated image.
- That pins the scale to the DI calibration, which is the conventional
  choice.
- It must use the Nyquist pixel and `-no-min-grid-resolution` that DD2b's
  audit requires for E2-N.

What DD4 has to add before any claim:
- the primary-beam treatment of the pinned fluxes;
- a facet layout from the field's bright sources (DD1-DD3 used four given
  centres);
- a measure on real data, since there is no truth: the residual rms around
  the off-axis source and the dynamic range, against the same loop in
  QuartiCal + WSClean, the oracle the parity results make available.
