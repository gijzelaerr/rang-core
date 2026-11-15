# Rang: a fix for multiscale's compact-source flux miss (issue #23, step 4)

Status, 2026-11-16: **proposed.** Sections 1-7 are frozen in this commit, before any code or run.
Results will be added as section 8; any later change to sections 1-7 is dated and labelled post hoc.

Issue [gijzelaerr/rang-core#23](https://github.com/gijzelaerr/rang-core/issues/23), step 4.
Steps 1-3: [multiscale-df5o-a1.md](multiscale-df5o-a1.md) and
[results/multiscale-df5o-a1.json](results/multiscale-df5o-a1.json).
Field, oracle and tolerances: [df5o-deconv-oracles.md](df5o-deconv-oracles.md), sections 1, 3, 4 and 6.5.
GeMClean's multiscale: [g5-multiscale.md](g5-multiscale.md).

## 1. What steps 1-3 found

- GeMClean `-multiscale` shares WSClean 3.7's miss on DF5-O's field. p23 fails A1 (ΔS/S +0.159,
  +13.6 µJy against a tolerance of 13.3). p16 and p26 pass by under 1 µJy.
- The excess is on nearly every point source: 33 of the 34 points ≥ 20σ_ap are high, median
  +16.0 µJy.
- Post hoc, it is nearly cancelled by a local negative ring (r < d ≤ 2r), so the small scales
  redistribute flux rather than add it.
- `-multiscale-scale-bias 0.8` (v3) removes the miss but raises the inner residual RMS to
  1.4862 µJy, above DF5-O 6.5's multiscale bound of 1.4753. Removing the large scales (v1, v2) and
  `-multiscale-gain 0.1` (v4) leave the miss.

## 2. Mechanism to test

This is a reading of the code and of step 3's numbers. It is not yet measured.

radler's bias factor is `β^(−log2(s / 2b))`, with `β` = `-multiscale-scale-bias` (0.6) and `b`
the **theoretic beam**, `1 / max |uvw|/λ`. radler's automatic scales are `0, 4b, 8b, …`, so its
first non-zero scale gets bias `1/β` = 1.67. This is Offringa & Smirnov (2017, MNRAS 471, 301)
eq. 3, which is written relative to the first non-zero scale α₁.

On DF5-O's field:

- **The beams differ by 4.7×.** The theoretic beam is about 2.47 px (4.9″). The natural-weighted
  PSF has a FWHM of 11.58 × 7.23 px.
- **The scale list follows the fitted beam.** DF5-O's list, `0, 24, 48, 96, 192`, is `0, 2b_f,
  4b_f, …` with `b_f = 12 px`.
- **The bias still follows the theoretic beam.** With a user list, radler (WSClean 3.7 and radler
  HEAD) keeps `b` theoretic. So the biases are 3.2, 5.4, 9 and 15, not the 1.67, 2.78, 4.63 and
  7.72 that radler gives its own first four non-zero scales.

A point source of flux `S` has a scale-`s` convolved peak of `S · psf_peak(s)`. Its biased peak is
`S · bias(s) · psf_peak(s)`:

| scale (px) | psf_peak | bias | bias × psf_peak |
| ---: | ---: | ---: | ---: |
| 24 | 0.5026 | 3.2 | 1.61 |
| 48 | 0.3263 | 5.4 | 1.76 |
| 96 | 0.1572 | 9 | 1.41 |
| 192 | 0.0512 | 15 | 0.77 |

Every scale up to 96 px beats scale 0 (1.0) on a bare point. So points are first cleaned with
24-96 px components, and the delta scale then fills the core. That matches step 3's numbers:

- **The 24 px scale.** It took 21,767 components in gc-multiscale and 1,182 in v3. At β = 0.8 its
  product is 0.83, below 1.
- **The negative 96 px scale.** It holds −13.2 mJy.
- **The ring.** The local negative ring nearly cancels the aperture excess.

Hypothesis H0: **the miss comes from scales above zero winning the selection on point sources.**
It goes when every non-zero scale's `bias × psf_peak` falls below 1. The residual RMS stays within
the bound only if the large scales keep enough bias for extended emission.

## 3. Candidate fixes and hypotheses (frozen)

One change from `gc-multiscale` per arm (step 1-3's argv, section 5). Parameter values are fixed
here and are not tuned after any run.

| arm | change | source | upstream? | hypothesis (prediction on the seen field) |
| --- | --- | --- | --- | --- |
| `b065` | `-multiscale-scale-bias 0.65` | WSClean docs: natural or Briggs weighting "may call for a higher bias"; a LOFAR case was better at 0.7 | setting, both tools | 24 px product 1.34: miss smaller, A1 may still fail |
| `b070` | `-multiscale-scale-bias 0.7` | as above | setting, both tools | product 1.13: miss smaller; A1 pass or marginal; RMS below v3's |
| `b075` | `-multiscale-scale-bias 0.75` | as above | setting, both tools | product 0.96: A1 passes; RMS near v3's, likely above the bound |
| `b080` | `-multiscale-scale-bias 0.8` (v3, measured) | step 3 | setting, both tools | A1 passes, RMS 1.4862 fails (measured); run on the held-out field and in WSClean for the record |
| `ref1` | bias referenced to the first listed non-zero scale: `bias = β^(−log2(s / (α₁/2)))`, giving 1.67, 2.78, 4.63 and 7.72 (new option `-multiscale-bias-reference first-scale`) | O&S 2017 eq. 3; radler's own automatic-scale biases | **no** (radler references `b` theoretic for user lists) | products 0.84, 0.91, 0.73, 0.39: A1 passes. Large scales keep more bias than in v3 (2.78 against 2.08 at 48 px; 7.72 against 3.25 at 192), so RMS is below v3's and may be within the bound |
| `reff` | bias referenced to the fitted beam, `b = b_f` = `field.json`'s `fwhm_major_px` (new option `-multiscale-bias-reference <pixels>`): biases 1.03, 1.71, 2.85, 4.75 | the scales' own beam | **no** | products 0.52, 0.56, 0.45, 0.24: A1 passes; close to Högbom on compact flux; RMS likely above the bound |
| `cap` | point cap: `bias(s) ← min(bias(s), c / psf_peak(s))`, `c = 0.9` (new option `-multiscale-point-cap 0.9`): biases 1.79, 2.76, 5.73 and 15 (192 px uncapped) | GeMClean's own; a related PSF-peak normalisation is commented out in radler's `SetScaleInfo` (`max(1, psf_peak·kernel0/(kernel·psf0))`) | **no** (not in radler 3.7 or HEAD) | a bare point is always selected at scale 0, and the large scales keep radler's bias: A1 passes; RMS closest to the default among the bias arms |
| `noneg` | `-no-negative` (new GeMClean option, radler's `allow_negative_components = false`: signed peaks, positions `≥` threshold, signed sub-minor maximum) | WSClean `-no-negative` | setting, both tools | no negative ring or negative 96 px flux. Over-cleaning by a broad component then stays in the residual: compact excess smaller, A1 uncertain, RMS up |
| `gauss` | `-multiscale-shape gaussian` | WSClean (docs: "rarely noticeable") | setting, both tools | shares the miss |
| `s48` | `-multiscale-scales 0,48,96,192` | removes the 24 px scale (step 3 removed only large ones) | setting, both tools | 48 px product 1.76 > 1: shares the miss |
| `sauto` | no `-multiscale-scales` (radler's automatic scales from the theoretic beam: 0, about 9.9, 19.8, 39.5, 79, 158, 316 px) | WSClean default | setting, both tools | the first scale (about 10 px) still beats the delta on points, but its kernel lies inside the 11.6 px aperture. Redistribution is then mostly within the aperture: miss smaller, outcome open |

Not candidates, with their measured outcomes cited:

- v1, v2 and v4 of step 3 (the miss is kept);
- DF5-O's `ws-multiscale-mask` (auto-mask, `-fit-spectral-pol 4`): p23 +0.142, so it fails;
- `-no-multiscale-fast-subminor`, which GeMClean refuses (G5).

Controls on every field:

- `gc-multiscale` (default) with the new binary. On the seen field its 17 model FITS must equal
  step 1-3's bit for bit. Otherwise the default has changed, and nothing is scored until that is
  explained.
- `gc-hogbom`.

## 4. Fields

**Seen field D:** DF5-O's field as used in steps 1-3:

- `D:\rang\outputs\u23-20261113-01\field`, checked against `field.json` before the first run and
  after the last;
- WSL copy `~/Github/rang/outputs/df5o-20261031-01/field` for WSClean (ext4).

**Held-out field H (frozen now; not used in steps 1-3):**

- **Generator.** `examples/simulate_df5_field.py`, unchanged except that the two seeds become
  arguments (`--sky-seed`, `--noise-seed`). The defaults stay 20261031 and 5101.
- **Same instrument.** Array, track, channels, noise level, grid and sky model are all unchanged,
  so H has DF5-O's uv coverage and PSF.
- **First choice of seeds:** sky seed **20261116**, noise seed **5116**.
- **Fallback seeds**, only if the rule below rejects the first: (20261117, 5117), then
  (20261118, 5118).
- **Rule.** H is the first seed pair on which `gc-multiscale` (default) fails A1 on at least one
  source with ΔS > 0. The rule looks only at the default baseline, never at a candidate.
- **If none of the three pairs fails:** H is the third pair, and the decision falls on the margin
  clauses of section 6, with the outcome labelled "held-out field shows no miss". Every simulated
  pair is recorded.
- **Thresholds and scales:** H's threshold and scales are its own `field.json`'s
  `threshold_3sigma_jy` and `multiscale_scales_px`, by DF5-O's rule.
- **Scope of the claim.** Any claim from H is limited to this array, this track and natural
  weighting: H is the same PSF on a different sky.

## 5. Settings and oracle

- **GeMClean argv:** step 1-3's (`multiscale-df5o-a1.md` section 3) with the field's threshold and
  scales, then the arm's change. Each arm runs under `tools/heavy_lock.py run --slots 4 --mem 6`,
  with `-j 4`.
- **The binary:** built from this branch, profile `gemclean`. The sha256 is recorded.
- **WSClean 3.7:** DF5-O's image `rang-o-casa:6.7.6.14` and argv
  (`examples/oracle_wsclean_clean.py`), with the arm's same change, for every arm that WSClean can
  express (`b065`-`b080`, `noneg`, `gauss`, `s48`, `sauto`). Inputs are on WSL ext4. Each run is
  booked as 4 slots and 3 GB, or 2 slots when inputs are on 9p.
- **The arms with no WSClean equivalent** (`ref1`, `reff`, `cap`) are compared with WSClean's
  default `ws-multiscale`.
- **WSClean baselines:**
  - on D, DF5-O's `ws-multiscale` r1 and r2 (not rerun);
  - on H, `ws-multiscale` r1 and r2, and `ws-hogbom` r1 (whether A1 is attainable on H).
- **The scorer:** step 1-3's `measure.py`, which wraps `examples/compare_df5o.py` unchanged.
  Before scoring, the reproduction of DF5-O's `ws-multiscale-r1` measure file is repeated, to
  1e-9 relative.
- **Recorded per arm:**
  - A1 and A2 failures;
  - per-source ΔS, ΔS/S and ΔS/σ_ap;
  - the worst A1 ratio `max |ΔS| / (0.05 S + 3σ_ap)` over sources ≥ 20σ_ap;
  - the median ΔS of the point sources ≥ 20σ_ap;
  - the ring pedestal;
  - total ratio, spurious flux, inner and full core-recomputed residual RMS;
  - per-scale components and flux (GeMClean), major cycles and components;
  - wall time and peak RSS.

## 6. Tolerances and decision rule (frozen)

The tolerances are inherited from DF5-O sections 4 and 6.5 and from step 1-3. On field F, an arm
**passes** when all five hold:

1. **A1 without the multiscale exemption:**
   - total MFS model flux within 2 % of the truth;
   - every source with `S ≥ 20σ_ap` (points, Gaussians and the radio galaxy) within
     `0.05 S + 3σ_ap`.
2. **A2:** points within 0.1 PSF FWHM, extended sources within 0.25.
3. **The residual (A3, multiscale class):** the core-recomputed inner-half RMS within F's bound.
   The bound is `min(ws-multiscale repeats) + max(0.02 · min, 2 × spread)`. On D that is
   **1.4753 µJy**; on H it is computed the same way from H's two `ws-multiscale` repeats, before
   any candidate is scored on H.
4. **Margin:** the worst A1 ratio is at most **0.9**, so a pass cannot be scraped by under 1 µJy
   as p16 and p26 were.
5. **The offset itself:** the median ΔS of the points ≥ 20σ_ap is at most **half** of
   `gc-multiscale`'s (default) on the same field (on D, ≤ +8.0 µJy of +16.0). The clause is void
   when the baseline's median is ≤ 0.

Outcomes:

- **A fix (gain claim)** is an arm that passes on D **and** on H, with the same setting and no
  change after H is seen.
  - When WSClean, with the same setting, also passes on both fields, the fix is a **known
    upstream setting**: a documented recommendation, not novelty.
  - When only GeMClean's arm passes (`ref1`, `reff`, `cap`, or an upstream setting that WSClean
    fails), the claim is a **GeMClean option** that passes where WSClean's default fails. Section 7
    applies.
- **Several arms pass:** all are reported. The recommendation is the passing arm with the lowest
  inner RMS on **D**, because H is not used to choose. The default is not changed in this task;
  changing it is a coordinator decision.
- **An arm passing on D but failing on H:** it is recorded as **not generalising**, and no claim is
  made.
- **No arm passes on both: null.**
  - The best documented limit for v0.3.0 is the arm with the smallest worst A1 ratio on H among
    the arms within H's RMS bound, with its numbers.
  - Beside it go the default's numbers: the median point offset and the worst A1 ratio, on both
    fields.
- **Not part of the decision:** the extended sources' ΔS/S, spurious flux and cost. A2 and A1
  cover the extended sources ≥ 20σ_ap.
- **Bias 0.8 against Högbom.** Bias 0.8 nearly degenerates to Högbom, which already passes A1. The
  RMS clause separates a fix from Högbom, which fails it (1.6041 µJy on D). The per-scale
  components and flux are reported for every arm so that a Högbom-like pass is visible.

## 7. Novelty check (done before any code)

- **Scale bias above 0.6 for natural weighting.** This is **known upstream**. WSClean's
  multiscale page says Briggs or natural weighting may call for a higher bias, and gives a LOFAR
  case that was better at 0.7. `b065`-`b080` are settings, not novelty.
- **The bias's reference beam for a user scale list.** radler HEAD (`109057d`, 2026-11-12; cloned
  2026-11-16) still sets `first_auto_scale_size = beam_size_in_pixels * 2` in `SetScaleInfo`,
  with WSClean passing the theoretic beam (`minTheoreticalBeamSize`).
  - None of radler's 46 commits since `76fe447` changes the bias. The multiscale-related ones are
    speed changes to the residual update and the PSF convolutions (`01fe54f`, `542eb62`,
    `dadc1a0`, `f8709be`) and per-scale masks and RM synthesis (`feb03c7`, `bf29139`).
  - O&S 2017 write the bias relative to α₁, and derive its bounds (0.5 < β < 0.66) for scales on
    the `α₁ · 2^k` ladder with α₁ tied to the beam.
  - Referencing a user list's bias to its first scale (`ref1`) or to the fitted beam (`reff`) is
    therefore **not in radler**.
  - It is a small change of convention, not a new algorithm. If it passes, the right outcome is a
    documented GeMClean option and a note on how WSClean users can approximate it, not a claim of
    a better method.
- **The point cap (`cap`).** No upstream equivalent was found. radler's `SetScaleInfo` keeps,
  commented out, a bias from PSF peaks (`max(1, psf_peak·kernel0/(kernel·psf0))`). So the idea of
  normalising scale selection by the PSF response is known and was set aside upstream.
  - CASA's and Moresane's automatic biases come from the PSF or the SNR (WSClean docs).
  - Cornwell (2008) uses `1 − 0.6 s/s_max`.
  - The cap is GeMClean's combination, and any gain from it is an implementation choice, not a
    method claim.
- **`-no-negative`, Gaussian shape, scale lists.** These are upstream settings.
- **Literature on point flux in MS-CLEAN.** O&S 2017 note that scales smaller than α₁ can take
  point sources from the delta scale, and that a badly chosen bias over-cleans some scales. They
  give no compact-flux analysis. No upstream report of this +5 to +38 µJy point offset under
  natural weighting was found.
- **Novelty bar (AGENTS.md).** Even a pass is a correction against WSClean's default on one
  instrument configuration, not a state-of-the-art gain. It is reported as such.

## 8. Results

Not yet measured.
