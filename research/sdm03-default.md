<!-- SPDX-License-Identifier: MIT -->
# Rang: SDm03 as rang-core's imaging default for MeerKAT L-band continuum? (issue #13)

Status at freeze, 2026-11-18: **proposed; nothing run.** Branch `sdm03-default` from main `b0388c0c`. Results go
under "Measured result"; nothing above it changes except by dated, labelled amendment. Route:
[docs/agents/propose-and-measure.md](../docs/agents/propose-and-measure.md). Previous note:
[floor-6.md](floor-6.md) (section 10.1, row SDm03; coordinator decision: SDm03 is a v0.4 candidate, no default
changes before v0.3.0). Host: **nash** ([nash-host.md](nash-host.md)), every job `nice -n 19 ionice -c3` through the
main checkout's `tools/heavy_lock.py run --slots N --mem G`, at most 16 slots booked by this task at any time.
Outputs: `nash:~/rang-data/outputs/sdm03-default-20261118`. Archive: `research/results/sdm03-default/`.
Driver: `examples/sdm03_default.py` (committed after this note).

## 1. Question and hypothesis

floor-6 measured, on held-out scan 10 of the ESO137 track, that SDm03 (`-channels-out 8 -join-channels
-fit-spectral-pol 2`, set A's FITS source mask, `-threshold 0.0003`) removes 0.717 of the post-Sp excess P_ref.
P_ref was taken against `research/results/floor-3/p1.yaml`'s final image (3 mJy, Briggs 0.5, accuracy 1e-6). That
is **not** rang-core's default. A bare `image` section (`python/rang/core_config.py`) passes GeMClean, through
`core_pipeline.gemclean_arguments`: `-weight briggs 0.0 -niter 1000000 -auto-threshold 3.0 -wgridder-accuracy
0.0001`, one output channel, no mask, GeMClean's measured major-cycle rule and `-nmiter` 20. The shipped
`-auto-threshold 3` may already reach part of the depth that SDm03's 0.3 mJy buys.

**Hypothesis.** Against the shipped default on data never used to pick SDm03, a form of SDm03 that rang-core can
ship removes at least a quarter of the default's excess residual floor. It does no harm to flux or false flux on
simulated skies with known truth, it stays within WSClean 3.7's result at matched settings, and it costs at most
the bounds of section 7.

**Not claimed.** No novelty (WSClean, radler and CARACal already do joined-channel, masked, deep CLEAN), no gain
over WSClean, and no exclusive speed figure unless section 7's exclusive pair runs. Not tested: another field or
telescope, the antenna-gain protocol, multiscale (refused with masks in floor-5/6), UHF and S-band, and fields
whose spectra differ from ESO137's.

## 2. What a default can express: the arms (frozen)

A FITS mask made on another image and an absolute 0.3 mJy are field-specific. A default can change only config
keys. So SDm03 is measured in two forms: **literal** (floor-6's, on the ESO137 field only, where set A's mask
applies) and **shippable** (rang-core config keys only). The shippable mask is radler's automatic mask, the route
rang already ships (`image.auto_mask`, selfcal `cleanmask_method: wsclean`). Its numbers are **CARACal's shipped
final-image values** (`cleanmask_thr` 6, `clean_cutoff` 0.5, `img_mgain` 0.9;
[c5b-selfcal-masks.md](c5b-selfcal-masks.md) section 1). They are not tuned here. `-auto-mask` needs an explicit
`mgain` (`gemclean::auto_mask_mgain`).

Every arm is built from a rang-core config: the defaults, plus `size` and `scale` (required), plus
`threads: 8`, plus the arm's keys. The argv is `core_pipeline.gemclean_arguments` on the resolved section, so A0
is exactly what a user gets. `-field 0`, the data column and `-no-update-model-required` are added as the
pipeline adds them. Base: ESO137 `size [4096, 4096]`, `scale 3asec`; simulated skies `[2048, 2048]`, `1.5asec`.

| arm | config keys beyond the base | role |
| --- | --- | --- |
| **A0** | none | the shipped default (the baseline of every D below) |
| **SDa** | `channels_out 8, join_channels true, fit_spectral_pol 2, auto_mask 6, auto_threshold 0.5, mgain 0.9` | **SDm03, shippable form: the candidate default** |
| **Sa** | as SDa with `auto_threshold 3` (the default's depth) | SDa without the deeper threshold (control) |
| **SDm03** | `channels_out 8, join_channels true, fit_spectral_pol 2, fits_mask` set A's, `auto_threshold null, threshold 0.0003` | SDm03 literal (ESO137 only) |
| **Sm** | as SDm03 with `threshold null, auto_threshold 3` | SDm03 without the deeper threshold (control; ESO137 only) |
| **W-SDa** | WSClean 3.7 at SDa's settings (section 6) | oracle |

If the verdict is a switch, the shipped form is the cheaper one that passes. **Sa** is shipped if Sa itself meets
every switch condition and D(SDa) − D(Sa) < 0.05 on every reserve scan; otherwise **SDa** is shipped. The keys
change in `image` (and so in selfcal's images, which take the `image` section). `threads` stays null.

## 3. Data (frozen)

### 3.1 Real reserve (the benefit)

[a0-acceptance.md](a0-acceptance.md) section 4 keeps ESO137 `ms1_target.zarr` **target scans 4, 6, 8 and 14
(MAIN_1, MAIN_2, MAIN_3, MAIN_6) unread, "a second reserve for an imaging and self-calibration-only check"**. That
is this check. The coordinator's brief of 2026-11-18 names this reserve's use. Scan 12 (MAIN_5) is E2-A's retry
reserve and is **not** used. Prior touch, disclosed: B1-2 read row chunk 0 of channel tile 20 (outside tiles
5-8, which are used here) of every group in a noise survey. Nothing else has read them: they are absent from
nash (`~/rang-data/e2-a/ESO137/ms1_target.zarr/MAIN` holds MAIN_4 only) and from `D:\rang`. Searched 2026-11-18.

**Choice, by a rule using metadata only.** Use **two** scans and keep two unread as a reserve for the next check.
Candidates in this order: **scan 4 (MAIN_1), scan 14 (MAIN_6)**, then scan 6 (MAIN_2), then scan 8 (MAIN_3). The
first two give the widest hour-angle spread around the pilot (scan 2) and scan 10. The first two that meet all
of the following are used:

- one field, PHASE_DIR equal to the pilot's to 0.01″ (so set A's mask and the scoring geometry apply);
- one publisher GKB-net group covers every row within 1 s, its `gain_freq` matching channels 640:1152 to 1 Hz;
- at least 15 min on target.

The conditions are checked from `.zattrs`, `.zarray`, the TIME row column, the FIELD subtable and the gain
metadata, before any visibility is fetched. A candidate that fails is reported, not used.

**Build, Sp and state: floor-6 sections 4 and 9, unchanged except for the group.** Fetch channel tiles 5-8 of
DATA, FLAG and WEIGHT_SPECTRUM, the row columns and the chosen GKB-net group's gains for those channels. Every
object's key, size and SHA-256 goes to a manifest; data CC BY 4.0, Ramatsoku et al. 2020. Then
`gemclean_heldout_real.py`'s convert, verify, gainload, gaincheck, calibrate and average (2×), floor-3's copy, and
`rang-core selfcal` with `research/results/floor-3/p1.yaml` (one Sp round at 300 s; this sets the data state,
S1, and is not an arm). Then floor-6's `state`: subset channels 4, 12, …, 252, Briggs 0.5 on the subset, 4096 ×
3″, F over the inner two-thirds outside set A's mask, T from `Data.noise(1301)`. floor-6's `floor6_tests.py` is
used with its `MAIN` pointed at the chosen group. **P_X = F(S1, model_X)² − T²**, and **D_X = (P_A0 − P_X) /
P_A0**. D against P_ref (p1's own final 3 mJy image, as floor-6) is reported beside it as the link.

**Gates per scan** (floor-6 section 6; a failure voids that scan and moves to the next candidate, never read as
a refutation): GH (verify 0 cells differ, gains within 1 s and 1 Hz, gaincheck's corrected convention the most
coherent), GS1 (Sp converged ≥ 0.9, ≤ 5 % solutions flagged), HB (numpy apply against CORRECTED_DATA within
1e-4), GT (T / F_A0 ≤ 0.3, so there is an excess to share; the excess is measured against A0 here).

### 3.2 Simulated skies (no-harm and oracle; truth known)

`examples/g3_spectral_simulate.py`: 64 MeerKAT dishes, 16 channels over 900-1670 MHz (L-band), 2 h at 16 s,
natural MFS noise 20 µJy, curved power-law spectra (ν0 1.2 GHz). There are no gain errors, so these skies test
the imaging change alone. calchain-floor's simulation-control rule (constant truth or `interp: nearest` for a
noise-free gain control) does not apply: no gains are simulated or solved. **Fresh skies X1-X4**, recipes added to
the simulator after this commit, at declinations no g3 sky used:

| sky | recipe | dec | sky seed | noise seed |
| --- | --- | ---: | ---: | ---: |
| X1 | D1 (`points`: 40 points 2-500 mJy, α −1.2 to 0.3, every third curved) | −45 | 20261841 | 20261851 |
| X2 | D1 | −75 | 20261842 | 20261852 |
| X3 | D2 (`extended`: 5 Gaussians 15-60″, 0.1-1 Jy, and 20 points) | −20 | 20261843 | 20261853 |
| X4 | D2 | −50 | 20261844 | 20261854 |

The seeds were searched in decimal and hex in `research/`, `examples/`, `tests/`, `python/` and `core/` on
2026-11-18: no match. Each sky is simulated once and read once.

**Scoring** (new, in the driver, on the benchmark's `gemclean_bench_compare.py prepare` arrays: Stokes I, Briggs
0.5, exact gridder at 1e-6). Each arm's model is predicted per output channel at that channel's frequencies; one
plane is predicted at all 16. Measures:

- e = V − model; the residual image is the exact gridder's Briggs 0.5 dirty image of e.
- **F** is the rms over the inner two-thirds outside the **truth mask**: pixels within 3 beams of a point, or
  within FWHM + 3 beams of a Gaussian. Scoring uses truth; no CLEAN mask does.
- **T** is the same F with the exact truth subtracted (noise only).
- P = F² − T², and D = (P_A0 − P) / P_A0.
- **Recovery**: for each point source with truth flux ≥ 50 × the noise image rms, the model flux within 6 pixels,
  per output channel, against the truth spectrum averaged over that channel's frequencies (one plane: over all
  16). The median and the median |ratio − 1| are reported.
- **False flux**: Σ |model| beyond 2 beams of every truth component, summed over planes weighted by each plane's
  Briggs weight sum (normalised to 1).

### 3.3 Seen data, the chain dry run (reported, never in the verdict)

Before X1-X4 are drawn and before any reserve visibility is fetched, the whole chain runs on seen data:

- floor-6's pilot state (`floor-6-20261117/pilot`, floor-5's `g1/P/pilot.ms`) and scan 10's held-out state
  (`floor-6-20261117/ho`), with every arm and W-SDa;
- g3's D1 sky (seeds 20261161 / 20261171), with A0, SDa, Sa and W-SDa;
- the scorers and the rule's evaluation on those numbers.

A defect found there is fixed before the reserve or the fresh skies are read, by a dated amendment.

## 4. Benefit and no-harm measures (frozen)

On each **reserve scan**: D(SDa), D(Sa), D(SDm03), D(Sm); the depth readings D(SDa) − D(Sa) and D(SDm03) −
D(Sm); and per arm the components, major cycles, stop reason, model flux, negative flux, residual MAD, wall and
peak RSS.

On each **fresh sky**, for SDa and for Sa, against A0:

- **N1** D ≥ −0.05 (not worse than the default's floor);
- **N2** false flux ≤ 1.1 × A0's + 0.1 mJy;
- **N3** median |ratio − 1| ≤ A0's + 0.005, and median ratio within 0.02 of 1.

## 5. Cost (frozen)

Paired shared readings: on each reserve scan A0 and the candidate run at the same time under the lock, 8 slots
each, `/usr/bin/time` wall and peak RSS. They are labelled "nash, shared".

- **C1** candidate wall ≤ 6 × A0's wall and ≤ 60 min;
- **C2** candidate peak RSS ≤ 3 × A0's and ≤ 48 GiB (it must run on a 63 GB workstation).

**Prior** (floor-6 at 1e-6, against R3, not A0): SDm03 1,714 s against 347 s (4.9 ×), about 22 against 11 GiB
(2 ×). The shipped 1e-4 single precision makes both cheaper per cycle, and A0's depth is unknown. So the prior
predicts C2 passes, and C1 may fail on the ratio. Why the bounds: the final image runs once per selfcal run, and
floor-6's Sp round on scan 10 took about 46 min. An image costing up to 6 × the default and an hour at 8 threads
stays the same order as the run it ends. 8 output planes need about 8 × the image-plane memory of one; 3 ×
leaves room for the plane-shared buffers.

If a shared C1 or C2 reading falls within 20 % of its bound, one exclusive pair (A0 then the candidate on the
first reserve scan) runs between 22:00 and 06:00 SAST, and that pair decides C1 and C2. No other exclusive or
timing run is made.

## 6. Oracle (frozen)

WSClean 3.7, nash's `/usr/bin/wsclean` ("WSClean version 3.7 (2026-02-16)"). The archived
`rang-wsclean-native_3.7.sif` stops with an illegal instruction on nash (stop28-default amendment 2). It runs at
SDa's settings: `-gridder wgridder -no-min-grid-resolution -wgridder-accuracy 1e-4 -size … -scale … -weight briggs
0 -niter 1000000 -mgain 0.9 -auto-threshold 0.5 -auto-mask 6 -nmiter 20 -channels-out 8 -join-channels
-fit-spectral-pol 2 -pol I -field 0 -j 8 -no-update-model-required`, with the same data column. If Sa is the
shipped form, W-Sa (the same with `-auto-threshold 3`) is run as well, under the same rule.

**O1** for the shipped form, on every reserve scan and every fresh sky: P_gem ≤ 1.25 × P_wsc, **or** |D_gem −
D_wsc| ≤ 0.05. Both are scored by the same scorer against the same A0. The tolerance is wider than g3's known
joined-channel miss (H1s, a shared aperture-estimator bias at dec −60; [g3-spectral.md](g3-spectral.md)).
GeMClean better than WSClean passes and is reported.

## 7. Decision rule (frozen)

Precedence: the first outcome whose condition holds.

1. **Incomplete**: fewer than two reserve scans pass every gate, or any arm the rule needs is unscored on a
   reserve scan or a fresh sky. Nothing is read as a failure; what ran is reported.
2. **Not yet**: the shippable form fails N1, N2 or N3 on any fresh sky, or fails O1 anywhere; **or** both
   shippable forms have D < 0.10 on some reserve scan while SDm03 literal has D ≥ 0.10 on every reserve scan. The
   lever is real, but rang's shippable mask route does not capture it.
3. **Switch**: the shipped form (section 2) has D ≥ **0.25** on every reserve scan, N1-N3 on every fresh sky,
   O1, C1 and C2.
4. **Keep opt-in**: SDa or Sa has D ≥ **0.10** on every reserve scan with N1-N3 and O1, but misses the switch bar
   or C1/C2. It is documented as a recipe; the default stays.
5. **Null**: otherwise, and in particular when SDm03 literal has D < 0.10 on some reserve scan. The default
   already holds what is left of the lever on fresh data; the default stays.

**A switch here is necessary, not sufficient.** floor-6's coordinator decision requires E2-A's and E2-N's gate
rows to be re-read with the new settings, under calchain-floor's simulation-control rule, before a default
changes. That is the coordinator's, after this note. No default changes before v0.3.0. On a switch, the code
change goes in a separate commit on this branch: config defaults, tests, `docs/cli.md`, CHANGELOG.

Also reported, not gating: the same readings on the seen data (section 3.3); D against P_ref (the link to
floor-6's 0.717); and SDm03 literal against SDa (how much the mask route loses).

## 8. Stages and stop rules

1. This note, committed and pushed.
2. The driver `examples/sdm03_default.py` and the X1-X4 recipes in the simulator; a nash worktree at the
   branch's commit, its venv and extension built there. The commit and SHA-256 go to `provenance.json`.
3. The dry run (section 3.3). Defects are fixed by amendment.
4. The reserve metadata (section 3.1's conditions); then the fetch, build, Sp, state and arms for the two scans
   chosen. In parallel, X1-X4 are simulated once, imaged and scored.
5. Scoring and the verdict by section 7. The exclusive pair runs only under section 5's 20 % clause.

A failed fetch, build, simulation or gate stops its own track and is reported. The driver runs unattended
(`setsid nohup`); its log `logs/driver.log` ends with `SDM03 DONE rc N`, and `timing.tsv` lists every locked job.

## Amendments

**1, 2026-11-18, before any run (implementation details the frozen text left open).**

- The truth mask's beam (section 3.2) is √(BMAJ × BMIN) of A0's restored image on the same sky. It is the same
  for every arm and is recorded in `truth.json`.
- Recovery takes points whose channel-weighted truth flux is ≥ 50 T.
- An output plane's channels are WSClean's contiguous equal split: 16 → 8 × 2 on the simulated skies, and
  floor-5's 256 → 8 × 32 on ESO137.
- The ESO137 arms run in pairs under the lock: A0 with SDa (the cost pair), Sa with Sm, SDm03 with W-SDa.
- The driver and its environment are `research/results/sdm03-default/scripts/{drive.sh,env.sh}`. Python is
  this branch's (`examples/sdm03_default.py`). GeMClean and the extension are built from this branch on nash,
  and so are the Sp round's.
- The two reserve tracks run side by side. Each takes the next candidate from the list when its own fails a
  condition or a gate, so "the first two that pass" means the first two to pass in that order of attempts.

**2, 2026-11-18, during the dry run on seen data (section 3.3), before any reserve visibility was fetched or
any fresh sky was drawn.**

- The nash venv (`uv pip install -e ".[test]"`) lacked SciPy and Astropy, which the benchmark scorer and
  `gemclean_heldout_real.py` import. D1's `simprep` failed at import. Fix: SciPy 1.18.1 and Astropy 8.0.3 from
  public PyPI, with NumPy 2.5.5 unchanged. D1's track was rerun (`drive.sh d1`). No number was read before the fix.
- The dry run's 16-slot cap let other jobs start between A0 and SDa, so the pair was not booked as one job.
  The main run books each ESO137 pair as one 16-slot job (`scripts/pair.sh`; each arm runs 8 threads and writes
  its own `/usr/bin/time` line). While a pair waits, smaller jobs of this driver are held back. The pilot's
  seen pairs keep the old schedule.

**3, 2026-11-18 08:50 SAST, before any reserve visibility was fetched or any fresh sky was drawn. It was
written after the seen pilot's A0 and SDa scores were read.**

- The dry run is cut short. Every stage of the chain has run on seen data. D1 ran in full: simulate, prep,
  four arms (W-SDa included) and scoring. On the pilot, A0 and SDa were imaged and scored by floor-6's scorer
  (`score-pilot-early`), and the summary's real readings, D, D_ref and cost were evaluated on those scores.
- The pilot's Sa, Sm, SDm03 and W-SDa had not finished, and they were stopped. The pilot's SDa took 5,512 s,
  so the other four would have held 16 slots for about three more hours of seen data. They are reported as
  not run. Scan 10's seen arms still run in the main run.
- Disclosed: the seen pilot readings were known before the reserve was read. A0 gives F 278.9 µJy (D_ref
  0.466) and SDa 329.7 µJy (D −0.41 against A0). SDa took 5,512 s and 18.0 GiB, against A0's 531 s and
  9.2 GiB. The rule, the arms and the bars are unchanged.

## Measured result

(not yet run)
