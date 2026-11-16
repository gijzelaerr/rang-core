# Rang: a fix for multiscale's compact-source flux miss (issue #23, step 4)

Status, 2026-11-16: **proposed.** Sections 1-7 are frozen in this commit, before any code or run.
Results will be added as section 8; any later change to sections 1-7 is dated and labelled post hoc.

Status, 2026-11-16 (later): **measured, null.** No arm passes on both fields under section 6
(section 8.1). Sections 1-7 are unchanged.

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

Final reading in 8.1-8.8 (2026-11-16, all runs finished). 8.0 is the interim, kept as written.

### 8.0 Interim (2026-11-16 03:40, runs still going; not the final reading)

Run root `D:\rang\outputs\msfix-20261116-01`. Binary from `7de8911`, sha256 `3907730f…ea21`.

**Controls.**

- Default gc-multiscale and gc-hogbom on D are bit-identical to step 1-3's outputs (17 model FITS
  and the MFS residual each).
- The scorer reproduction of DF5-O's ws-multiscale r1 and r2 passed.

**Held-out rule (section 4).** gc-multiscale default passes A1 on all three seed pairs:

| seed pair | worst A1 ratio | median point ΔS |
| --- | ---: | ---: |
| 20261116 / 5116 | 0.99 | +14.5 µJy |
| 20261117 / 5117 | 0.97 | +16.7 µJy |
| 20261118 / 5118 | 0.71 | +18.1 µJy |

- H is therefore the third pair, labelled "held-out field shows no miss".
- WSClean ws-multiscale on H also passes A1 (inner RMS 1.4598 and 1.4595 µJy).
- H's RMS bound is **1.4887 µJy**. It was frozen before any candidate on H was scored
  (`H3/rms-bound.json`).

**D, GeMClean.** RMS bound 1.4753 µJy; offset clause ≤ +8.0 µJy.

| arm | A1 failures | worst ratio | median point ΔS (µJy) | inner RMS (µJy) | wall (s) |
| --- | --- | ---: | ---: | ---: | ---: |
| gc-multiscale | p23 | 1.03 | +16.0 | 1.4447 | 316 |
| gc-hogbom | – | 0.53 | −4.2 | 1.6041 | 47 |
| gc-b065 | – | 0.93 | +16.4 | 1.5418 | 223 |
| gc-b070 | – | 0.98 | +17.5 | 1.5919 | 191 |
| gc-b075 | – | 0.79 | +15.8 | 1.5323 | 121 |
| gc-b080 | – | 0.50 | −2.5 | 1.4862 | 115 |
| gc-ref1 | – | 0.49 | +3.1 | 1.5794 | 145 |
| gc-reff | – | 0.49 | −3.8 | 1.5843 | 80 |
| gc-cap | – | 0.57 | +3.7 | 1.6144 | 198 |
| gc-gauss | p23 | 1.15 | +13.9 | 1.4313 | 328 |
| gc-s48 | p32 (A2: p23) | 1.04 | +16.7 | 1.7100 | 336 |
| gc-sauto | – | 0.82 | +11.0 | **1.3760** | 384 |
| gc-noneg | 39 sources | 48 | +602 | 171 | 1934 |

So far, on D:

- **No arm passes** all five clauses.
- **The offset fixes cost RMS.** Every arm that removes the offset (ref1, reff, cap, b080) has an
  inner RMS of 1.486-1.614 µJy, above the bound.
- **sauto comes closest.** It fails only the offset clause (+11.0 against ≤ +8.0) and has the
  lowest RMS of all arms.
- **gc-noneg diverged.** The 192 px scale took +0.41 Jy, and Q/Q0 is 0.0998 against 0.0176.
  ws-noneg will show whether WSClean `-no-negative` does the same; a GeMClean bug has not been
  ruled out.
- **A post hoc correction.** The theoretic beam is 2.4403 px, not the 2.47 px given in section 2.

**WSClean on D.**

| arm | A1 failures | worst ratio | median point ΔS (µJy) | inner RMS (µJy) |
| --- | --- | ---: | ---: | ---: |
| ws-b065 | p26 | 1.02 | +16.7 | 1.5595 |
| ws-b070 | – | 0.96 | +17.7 | 1.5797 |

The remaining H gc arms and the WSClean arms on D and H were still running at this point.
`decide.py` writes the final archive.

### 8.1 Outcome under section 6: null

Archive [results/multiscale-flux-fix.json](results/multiscale-flux-fix.json): `decide.py`'s
output plus the three held-out seed pairs. Run root `D:\rang\outputs\msfix-20261116-01`.
GeMClean binary sha256 `3907730f…ea21`, from `7de8911`. WSClean 3.7 in `rang-o-casa:6.7.6.14`.

**No arm passes on both fields. The result is null.**

- **Which H.** H is the third seed pair (20261118 / 5118), labelled **"held-out field shows no
  miss"**, because the default passes A1 on all three pairs (8.0). On H the decision therefore
  rests on the RMS, margin and offset clauses.
- **Bounds.** RMS: D 1.4753 µJy, H 1.4887 µJy. H's is the frozen `H3/rms-bound.json`, and
  `decide.py` gives the same value. Offset: D ≤ +8.003 µJy (half of +16.006), H ≤ +9.072 µJy
  (half of +18.145).
- **gc-sauto** passes on H and fails on D, on clause 5 only (+11.00 against ≤ +8.00).
  - Section 6 needs both fields, so it is not a fix.
  - Its H pass is by 0.02 µJy (+9.053 against +9.072). That is inside the baseline's own scatter:
    WSClean's two H repeats differ by 1.8 µJy in the median (+18.59 and +16.77).
  - ws-sauto fails on H (+11.30).
- **Every other arm** fails on both fields.

Failing clauses for GeMClean: `1` A1, `2` A2, `3` RMS, `4` margin, `5` offset.

| arm | D: fails | D worst | D median ΔS | D RMS | H: fails | H worst | H median ΔS | H RMS |
| --- | --- | ---: | ---: | ---: | --- | ---: | ---: | ---: |
| gc-multiscale (default) | 1 4 5 | 1.03 (p23) | +16.0 | 1.4447 | 5 | 0.71 | +18.1 | 1.4681 |
| gc-hogbom | 3 | 0.53 | −4.2 | 1.6041 | 3 | 0.43 | −3.9 | 1.5608 |
| gc-b065 | 3 4 5 | 0.93 | +16.4 | 1.5418 | 3 5 | 0.79 | +19.3 | 1.5806 |
| gc-b070 | 3 4 5 | 0.98 | +17.5 | 1.5919 | 3 5 | 0.80 | +22.9 | 1.6119 |
| gc-b075 | 3 5 | 0.79 | +15.8 | 1.5323 | 3 5 | 0.70 | +24.0 | 1.5743 |
| gc-b080 | 3 | 0.50 | −2.5 | 1.4862 | 3 | 0.56 | +7.9 | 1.5390 |
| gc-ref1 | 3 | 0.49 | +3.1 | 1.5794 | 3 | 0.40 | +4.8 | 1.6198 |
| gc-reff | 3 | 0.49 | −3.8 | 1.5843 | 3 | 0.44 | −3.1 | 1.5723 |
| gc-cap | 3 | 0.57 | +3.7 | 1.6144 | 3 | 0.70 | +3.0 | 1.5863 |
| gc-gauss | 1 4 5 | 1.15 (p23) | +13.9 | 1.4313 | 5 | 0.74 | +15.2 | 1.4741 |
| gc-s48 | 1 2 3 4 5 | 1.04 (p32) | +16.7 | 1.7100 | 3 5 | 0.66 | +15.6 | 1.7973 |
| gc-sauto | 5 | 0.82 | +11.0 | **1.3760** | – | 0.67 | +9.05 | **1.4091** |
| gc-noneg | all | 48 | +602 | 171 | all | 57 | +809 | 197 |

WSClean 3.7 with the same settings. No WSClean arm passes on either field.

| arm | D: fails | D worst | D median ΔS | D RMS | H: fails | H worst | H median ΔS | H RMS |
| --- | --- | ---: | ---: | ---: | --- | ---: | ---: | ---: |
| ws-multiscale r1 | 1 4 5 | 1.04 (p16, p23, p26) | +15.4 | 1.4463 | 5 | 0.70 | +18.6 | 1.4598 |
| ws-multiscale r2 | 1 4 5 | 1.04 | +15.9 | 1.4513 | 5 | 0.70 | +16.8 | 1.4595 |
| ws-hogbom | not rerun (DF5-O) | | | | 3 | 0.43 | −3.9 | 1.5652 |
| ws-b065 | 1 3 4 5 | 1.02 (p26) | +16.7 | 1.5595 | 3 5 | 0.77 | +18.7 | 1.5750 |
| ws-b070 | 3 4 5 | 0.96 | +17.7 | 1.5797 | 3 5 | 0.77 | +22.3 | 1.6133 |
| ws-b075 | 3 5 | 0.80 | +15.3 | 1.5167 | 3 5 | 0.72 | +25.1 | 1.5741 |
| ws-b080 | 3 | 0.50 | −2.5 | 1.4883 | 3 | 0.56 | +7.9 | 1.5410 |
| ws-gauss | 1 4 5 | 1.10 (p23) | +12.5 | 1.4359 | 5 | 0.73 | +15.4 | 1.4772 |
| ws-s48 | 1 2 3 4 5 | 1.16 (p32) | +18.6 | 1.7133 | 3 5 | 0.65 | +15.8 | 1.8061 |
| ws-sauto | 5 | 0.83 | +11.6 | 1.3758 | 5 | 0.72 | +11.3 | 1.4092 |
| ws-noneg | all | 135 | +1513 | 212 | all | 188 | +1811 | 233 |

- **Columns.** Median ΔS is in µJy, over the points ≥ 20σ_ap (34 on D, 32 on H). RMS is the
  core-recomputed inner RMS, in µJy.
- **The two tools agree arm by arm.** On b080 they agree to 0.002 µJy in RMS and 0.01 µJy in the
  median, on both fields.

**The documented limit for v0.3.0 (section 6, null clause).**

- **Arms within H's RMS bound:** default, gauss and sauto, in both tools.
- **Smallest worst A1 ratio on H among them:** **gc-sauto, 0.675**, against 0.698 for
  ws-multiscale and 0.725 for ws-sauto.

| field | arm | worst A1 ratio | median point ΔS (µJy) | inner RMS (µJy) |
| --- | --- | ---: | ---: | ---: |
| D | gc-sauto | 0.82 | +11.0 | 1.3760 |
| H | gc-sauto | 0.67 | +9.05 | 1.4091 |
| D | default | 1.03 (p23 fails) | +16.0 | 1.4447 |
| H | default | 0.71 | +18.1 | 1.4681 |

### 8.2 What limits the fix: the Högbom end, not bias 0.8 as such

Every arm that halves the offset does so by moving compact flux back to the delta scale, and pays
for it in residual RMS. The arms that keep the RMS within the bound keep the offset.

- **The offset-removing arms** (b080, ref1, reff, cap) fail only the RMS clause, on both fields.
  Their scale-0 share of the net model flux is 0.85-0.88 on D and 0.88-0.91 on H, against 0.78
  and 0.83 for the default.
- **Their RMS is close to Högbom's.**
  - On D: 1.4862-1.6144 µJy, against Högbom's 1.6041.
  - On H: 1.5390-1.6198, against Högbom's 1.5608. ref1, reff and cap are at or above Högbom;
    b080 is 0.022 µJy below it.
- **Bias 0.8 is the best of them, and it still fails.**
  - It exceeds the bound by 0.011 µJy (0.7 %) on D and 0.050 µJy (3.4 %) on H.
  - On H it also keeps +7.9 µJy of offset, with 30 of 32 points positive. On D the figures are
    −2.5 µJy and 9 of 34. +7.9 only just meets the half clause (≤ 9.07).
- **The arms within the bound** (default, gauss, sauto) all keep a median of at least +9 µJy.
- **The trade-off is not GeMClean's.** WSClean gives the same numbers arm by arm (8.1), so this
  is the algorithm's trade-off on this PSF, not an implementation effect.

So the limit is not a badly tuned bias. No measured setting meets both the offset clause and the
RMS bound. Removing the offset makes the result Högbom-like on compact flux, and then also
Högbom-like on residual RMS. sauto comes nearest to meeting both, from the other side: it has a
lower RMS than any arm, but it cuts the offset by only 31 % on D and 50 % on H.

### 8.3 Section 3's predictions against the measurements

| arm | prediction | measured (D / H) | reading |
| --- | --- | --- | --- |
| b065 | miss smaller; A1 may fail | offset +16.4 / +19.3 (default +16.0 / +18.1); RMS up | wrong on the offset |
| b070 | miss smaller; RMS below v3's | +17.5 / +22.9; RMS 1.59 / 1.61 | wrong |
| b075 | A1 passes; RMS near v3's | A1 passes; offset +15.8 / +24.0; RMS 1.53 / 1.57 | the offset stays at a 24 px product of 0.96 |
| b080 | A1 passes, RMS fails | as predicted on D; on H the RMS fails (1.5390), offset +7.9 | confirmed |
| ref1 | A1 passes; RMS below v3's, maybe within the bound | A1 passes; RMS 1.58 / 1.62 | wrong on the RMS |
| reff | near Högbom; RMS above the bound | −3.8 / −3.1; RMS 1.58 / 1.57 | confirmed |
| cap | A1 passes; RMS closest to the default | A1 passes; RMS 1.61 / 1.59, the worst of the bias arms on D | wrong on the RMS |
| noneg | no ring, offset smaller, RMS up | diverges in both tools (8.4) | not testable as posed |
| gauss | shares the miss | p23 fails on D; +13.9 / +15.2 | confirmed |
| s48 | shares the miss | on D, p32 fails A1 and p23 fails A2; RMS 1.71 / 1.80 | confirmed |
| sauto | miss smaller, outcome open | +11.0 / +9.05; lowest RMS | confirmed: smaller, but not halved on D |

**H0, read post hoc.**

- **The threshold is not at a product of 1.** Scale wins over the delta do drive the offset.
  But b075, with a 24 px product of 0.96, keeps the full offset. b080 (0.84) removes it on D and
  halves it on H.
- **The offset is not monotone in β.** b065-b075 raise it on H, to +19 to +25 against +18.
- The per-scale components and flux of every GeMClean arm are in the archive (`scale_lines`).

### 8.4 `-no-negative`: GeMClean against WSClean

Both tools diverge on both fields. The blow-up is therefore upstream behaviour on this field, not
a GeMClean bug.

- **WSClean.**
  - It logs `WARNING: Multiscale clean diverged.` on D and on H, after 4 major iterations.
  - On D it puts 1.84 Jy in the 192 px scale, 2.1 Jy in all: a total ratio of 21.0. On H the
    ratio is 20.4.
  - In the fourth minor loop the 192 px peak rises from 100 µJy to 4.96 mJy over 60,000
    components. That trips radler's guard (4 × the 339 µJy start peak), and cleaning stops.
- **GeMClean.**
  - It reports `end Normal` and stops at the threshold after 7 major cycles (6 on H).
  - It puts 0.41 Jy in the 192 px scale, 0.76 Jy in all: a total ratio of 7.66 (7.58 on H).
    Q/Q0 is 0.0998, against 0.0176 for the default.
  - The positive peak falls in every cycle (on D: 31.9, 6.23 and 1.24 mJy, then 257, 79, 23 and
    6.4 µJy). The guard compares the signed peak with 4 × the start peak, so it never trips.
  - The over-subtraction stays as a negative residual (|peak| 2.75 mJy), which `-no-negative`
    cannot clean.
- **Where the two tools split.**
  - The first three major cycles start at the same peaks in both tools: 31.9, 6.23 and 1.24 mJy
    on D; 32.4, 6.38 and 1.28 mJy on H.
  - The fourth starts at 257 µJy in GeMClean and 339 µJy in WSClean (271 and 391 on H). The
    trajectories split in the third minor loop.
  - Both tools fail A1 on the same sources: 39 on D, 37 on H.
- **Open.** The cause of the split in the third loop is not explained. It does not change the
  outcome: both tools fail every clause, by a factor of 50 or more.

### 8.5 Controls and checks

- **Defaults reproduced.**
  - gc-multiscale and gc-hogbom on D are bit-identical to step 1-3 (17 model FITS and the MFS
    residual each).
  - gc-b080 on D reproduces step 3's v3 (RMS 1.4862).
- **Scorer reproduction.** The reproduction of DF5-O's ws-multiscale r1 and r2 passed (8.0).
- **The scorer's A1 has no multiscale exemption.** `compare_df5o.py` applies `0.05 S + 3σ_ap` to
  every source ≥ 20σ_ap. The exemption lives only in DF5-O's verdict, so the scorer matches
  clause 1.
- **The field.** D was checked against `field.json` before the first run
  (`verify-d-before.json`) and after the last (`verify-d-after.json`, 10:55). Both are ok: the MS
  digest is `978e2720…b877`, over 59 files, with no mismatch.
- **Queue-script errors.**
  - `gc_queue.sh` was edited in the worktree while bash was reading it; the edit was committed in
    `d099e8d`.
  - The errors ("`and: command not found`" and a syntax error at line 36) follow the last arm in
    `D-gc-queue.log`, `H-gc-select.log` and `H2-gc-select.log`.
  - Every arm has its run, its measure file and a "done" line, so no run was lost.
- **WSClean runs.** Every WSClean run returned 0.
- **The WSL copy of H.** `verify-h-wsl.json` (01:47) reads "not ok". It was written by the script
  before the POSIX-name fix (`a02375f`, 01:51), and it lists every file under both separators.
  Every WSClean H run's `run.json` records the field MS digest as `7d876344…`, which equals H's
  `field.json` digest. The copy WSClean read was therefore the frozen field. The WSL scratch
  (`~/msfix-20261116`) has been removed; its two verify files are kept under the run root.
- **Clean-up after scoring.** The H and H2 selection FITS were deleted after the archive was
  written. The run root keeps the measures, the JSON and the logs.

### 8.6 Cost

GeMClean wall time is at `-j 4` with 4 lock slots on the Windows host, shared, at about 87 % CPU.
WSClean is at `-j 4` in docker on WSL, with inputs on ext4.

- **GeMClean, on D:**
  - Högbom 47 s; reff 80 s.
  - b075, b080 115-145 s; ref1 also falls in this range.
  - b065, cap, b070 190-223 s.
  - default 316 s; gauss and s48 328-336 s; sauto 384 s.
  - noneg 1,934 s.
- **Peak RSS:** about 3.5-3.9 GB for multiscale and 2.5 GB for Högbom.
- **WSClean:** 625-1,006 s per arm on D, ws-noneg 2,294 s, with a peak RSS of 0.85-1.06 GB.
- All rows are in `research/tool-timings.md`.

### 8.7 Issue comment draft (for the coordinator to post on #23)

> **Step 4 (multiscale compact-flux fix): null.** Full note:
> `research/multiscale-flux-fix.md` section 8; archive `research/results/multiscale-flux-fix.json`.
>
> **What was run.** 13 GeMClean arms and 10 WSClean 3.7 arms, on DF5-O's field (D) and on a
> held-out field (H).
> - The arms are bias 0.65-0.8, bias referenced to the first scale or to the fitted beam, a
>   point cap, `-no-negative`, Gaussian scales, no 24 px scale, and automatic scales.
> - H is the same instrument with sky seed 20261118 and noise seed 5118. The default passes A1 on
>   all three held-out seed pairs, so H shows no miss.
> - The decision rule was frozen before any run: A1 without the exemption, A2, residual RMS
>   within the WSClean repeats' bound, worst A1 ratio ≤ 0.9, and the median point offset halved.
>
> **Result: no arm passes on both fields.**
> - **The offset fixes cost residual RMS.** Bias 0.8, ref1, reff and the cap remove the offset:
>   on D, median ΔS goes from +16.0 to between −3.8 and +3.7 µJy. But they raise the inner RMS to
>   1.486-1.614 µJy on D (bound 1.475) and 1.539-1.620 on H (bound 1.489), which is Högbom's
>   level (1.604 and 1.561). Bias 0.8 is the closest, 0.7 % over on D and 3.4 % on H.
> - **Automatic scales come nearest.** With no `-multiscale-scales`, inner RMS is the lowest of
>   all arms (1.376 / 1.409). The median offset falls to +11.0 / +9.05 µJy: it passes on H by
>   0.02 µJy, but fails D's half-offset clause (≤ +8.0).
> - **WSClean behaves the same** with the same settings, arm by arm. On bias 0.8 the two tools
>   agree to 0.002 µJy in RMS.
> - **`-no-negative` diverges in both tools.** WSClean reports "Multiscale clean diverged". It is
>   not a GeMClean bug.
>
> **Documented limit for v0.3.0.** Under natural weighting with DF5-O's array, multiscale CLEAN
> leaves a median +9 to +18 µJy excess on compact sources ≥ 20σ_ap (WSClean and GeMClean alike).
> The best measured setting is automatic scales (D: worst A1 ratio 0.82, +11.0 µJy; H: 0.67,
> +9.05 µJy). For point-source flux, Högbom is unbiased (−4 µJy) at 7-11 % higher residual RMS;
> bias 0.8 gives −2.5 / +7.9 µJy at 3-5 % higher RMS.
>
> **No default changes.** The default is not changed. Whether to switch DF5-O's scale list to
> automatic scales is a separate decision.

### 8.8 Next steps (proposed, not started)

- **Automatic scales on DF5-O.** DF5-O's fitted-beam scale list costs residual RMS against
  radler's automatic scales on both fields (−4.9 % and −3.5 % of the ws-multiscale minimum). It
  is worth a coordinator decision, as an upstream setting, not a novelty.
- **The `-no-negative` split in the third minor loop.** Diagnosing it needs a per-iteration trace
  in both tools. It is low priority, because both diverge.
