<!-- SPDX-License-Identifier: MIT -->
# Rang: SDm03 as rang-core's imaging default for MeerKAT L-band continuum? (issue #13)

Status, 2026-11-18: **measured; outcome "not yet" (section 7, rule 2): GeMClean's shippable SDm03 fails the
WSClean oracle on scan 4. The default does not change.** Without the oracle clause the outcome would be "null":
on scan 4 every SDm03 form is worse than the shipped default, and on scan 14 every form is better. Protocol frozen
in `aef6c48c` before any run. Amendments 1-4 came before any reserve visibility or fresh sky was read. Status at
freeze: proposed; nothing run. Branch `sdm03-default` from main `b0388c0c`. Results go
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

**4, 2026-11-18 09:00 SAST, before any reserve visibility was fetched (scheduling only).**

- The first main run had started scan 10's seen pair (A0 with SDa) at 08:53. That pair held all 16 of the
  driver's slots for an estimated 1.5 h, ahead of the reserve. The driver was stopped after 3 min.
- Scan 10's seen arms now run after the reserve tracks, the fresh skies and the summary (`scripts/drive3.sh`
  is `drive.sh` at this commit).
- The restart then took the wrong candidates. The first run's workers had already popped MAIN_1 and MAIN_6
  from the candidate list, so the restarted workers took MAIN_2 and MAIN_3. For both scans, the group
  metadata, the TIME column and section 3.1's `meta` check were run, and `gains` had started on the
  publisher's gain metadata. No visibility, flag, weight or gain value was fetched: their `DATA` folders hold
  `.zarray` and `.zattrs` only. That is within a0-acceptance's allowance for held-out data (row columns,
  `.zarray` and `.zattrs`). The driver was stopped and the list reset to MAIN_1, MAIN_6, MAIN_2, MAIN_3.
  MAIN_2 and MAIN_3 stay unread unless a candidate before them fails.

## Measured result

Run 2026-11-18, 07:14-16:34 SAST, on nash (shared; every job `nice -n 19 ionice -c3` under the heavy lock, at most
16 slots booked by this task). Code: the extension `959aae39…` was built from `aef6c48c`, which is main `b0388c0c`
plus this note, and the Sp rounds used it too. The driver Python was at `c3d6bf72` for the main run. SciPy 1.18.1
and Astropy 8.0.3 were added (amendment 2). WSClean was nash's `/usr/bin/wsclean` 3.7 (2026-02-16). Run root:
`nash:~/rang-data/outputs/sdm03-default-20261118` (213 GB). Archive:
[results/sdm03-default/](results/sdm03-default/). It holds `summary-summary.json` (the final table),
`summary-main.json` (the as-run table, written before X4's W-Sa, the reserve W-Sa scores and the pilot's restored
state), `provenance.json`, `timing.tsv`, every arm's `image-arm.json` (argv and config keys), GeMClean reports and
imager logs, the state and build gates, the fetch and gain manifests, the scores, the driver logs, and the scripts
as run. Every D below was recomputed by hand from the per-arm JSONs and agrees with the summary to three decimals.

### Verdict by section 7: **not yet** (rule 2)

- **Reserve.** Candidates MAIN_1 (scan 4) and MAIN_6 (scan 14) both met section 3.1's conditions. Each has one
  field, PHASE_DIR separation 0.0″, 3,582 s and 3,590 s on target, and GKB-net groups 1 and 6 with a row gap of
  0.0 s. Every gate passes on both:
  - GH: `verify` identical, gain frequencies within 1 Hz, `gaincheck` correct;
  - GS1: converged 1.0 and 0.993, 1.64 % flagged on both;
  - HB: rel 0;
  - GT: T / F_A0 0.181 and 0.142.

  No later candidate was needed.
- **Shipped form: SDa.** Sa would be shipped only if Sa met every switch condition, and it does not (scan 4).
  **SDa fails O1 on scan 4.** P_gem / P_wsc is 1.359 (bound 1.25) and D_gem − D_wsc is −0.444 (bound 0.05). That
  is rule 2, "not yet", and it takes precedence.
- **Without O1 the outcome is null** (rule 5). SDm03 literal has D −0.354 on scan 4, below 0.10. Rule 2's second
  clause does not hold either, since the literal form also fails on scan 4. The default stays under either
  reading, and there is no code commit.

### Reserve scans (the benefit; F on the subset, D against A0, D_ref against p1's 3 mJy image)

| arm | scan 4 F (µJy) | D | D_ref | scan 14 F (µJy) | D | D_ref | wall s4 / s14 (s) | peak RSS (GiB) | components s4 / s14 | cycles s4 / s14 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| **A0** (shipped default) | 241.71 | 0 | 0.532 | 303.32 | 0 | 0.417 | 494 / 529 | 9.2 | 406,454 / 287,222 | 9 / 11 |
| **SDa** (shippable) | 311.18 | **−0.680** | 0.213 | 236.81 | **0.398** | 0.649 | 5,961 / 4,744 | 18.1 | 281,339 / 309,017 | 5 / 5 |
| Sa (control) | 314.34 | −0.715 | 0.197 | 237.02 | 0.397 | 0.649 | 1,601 / 1,992 | 18.1 | 94,508 / 151,710 | 4 / 5 |
| **SDm03** (literal) | 280.02 | **−0.354** | 0.366 | 263.95 | **0.248** | 0.561 | 2,387 / 1,700 | 18.1 | 161,257 / 126,026 | 6 / 5 |
| Sm (control) | 271.49 | −0.270 | 0.405 | 258.28 | 0.281 | 0.581 | 2,817 / 2,343 | 18.1 | 213,312 / 172,802 | 6 / 8 |
| W-SDa (WSClean) | 267.85 | −0.236 | 0.421 | 239.58 | 0.384 | 0.641 | 1,188 / 1,227 | 2.2 | – | 6 / 6 |
| W-Sa (WSClean) | 269.48 | −0.251 | 0.414 | 239.85 | 0.382 | 0.640 | 911 / 1,004 | 2.2 | – | – |

T is 43.78 µJy (scan 4) and 43.02 µJy (scan 14). P_A0 is 5.65e-8 and 9.01e-8 Jy². Every GeMClean arm stopped on
Threshold.

- **The lever does not transfer.** On scan 14 every SDm03 form beats the default: SDa 0.398, literal 0.248. On
  scan 4 every form is worse than the default: SDa −0.680, literal −0.354, and WSClean's SDa −0.236. On the seen
  pilot, SDa is −0.408 (below). So two of three scans go against SDm03.
- **The shipped default is far deeper than floor-6's baseline.** A0 (auto-threshold 3σ, unmasked, Briggs 0, 1e-4)
  already removes 0.42-0.53 of P_ref, the excess left by p1's 3 mJy image. floor-6's 0.717 was measured against
  that 3 mJy baseline, not against rang-core's default.
- **The deeper threshold adds little.** D(SDa) − D(Sa) is 0.035 and 0.001. D(SDm03) − D(Sm) is −0.084 and −0.033:
  the literal 0.3 mJy is slightly worse than 3σ in set A's mask.
- **Cost (nash, shared).** A0 was paired with SDa. SDa took 12.1 × and 9.0 × A0's wall (5,961 s and 4,744 s),
  so it fails C1 on both counts. RSS was 1.96 × (C2 passes). Sa's wall comes from its pair with Sm, not with A0:
  3.2 × and 3.8 × (passes). SDa is far over C1, not within 20 % of it; the summary's `near_bound` flag is set
  because it counts "at or above 80 % of the bound". So no exclusive pair was due under section 5, and none ran.
- **O1 on scan 4 is a GeMClean-WSClean difference in the auto-mask stage** (post hoc, from the logs). GeMClean
  declares the auto-mask threshold reached in major cycle 3, at σ 175 µJy (mask level 1.05 mJy). It then
  continues inside that mask at gain 0.026 down to 0.5σ. WSClean reaches its mask level at about 0.65 mJy and
  builds a larger mask. On scan 14, GeMClean reaches the mask in cycle 4 (0.44 mJy) and agrees with WSClean (P
  ratio 0.976). The pilot shows the same early-cycle-3 pattern as scan 4.

### Fresh skies X1-X4 (no harm and oracle; all pass)

| sky | T (µJy) | F A0 / SDa / Sa / W-SDa / W-Sa (µJy) | D SDa / Sa | false flux A0 / SDa / Sa (Jy) | recovery median, \|r − 1\| median: A0 → SDa |
| --- | ---: | --- | --- | --- | --- |
| X1 | 23.34 | 97.33 / 33.31 / 33.29 / 33.36 / 33.33 | 0.937 / 0.937 | 1.013 / 0.036 / 0.036 | 1.016, 0.026 → 1.001, 0.015 |
| X2 | 23.47 | 114.84 / 36.56 / 36.54 / 36.62 / 36.60 | 0.938 / 0.938 | 1.048 / 0.061 / 0.061 | 1.010, 0.022 → 1.002, 0.011 |
| X3 | 23.50 | 54.36 / 28.56 / 28.56 / 28.58 / 28.58 | 0.890 / 0.890 | 0.320 / 0.0002 / 0.0002 | 0.995, 0.023 → 0.995, 0.016 |
| X4 | 23.44 | 86.67 / 32.17 / 32.18 / 32.22 / 32.22 | 0.930 / 0.930 | 0.561 / 0.019 / 0.019 | 1.012, 0.023 → 1.002, 0.015 |

- N1-N3 pass for SDa and Sa on every sky.
- O1 passes on every sky (P ratio 0.992-0.996).
- These skies have no gain errors and steep, curved spectra over 900-1670 MHz, so a one-plane MFS model leaves
  most of the excess. They show that joined channels do no harm and match WSClean. They do not show the
  ESO137 behaviour.
- Cost on 2048²: A0 29-35 s; SDa and Sa 101-139 s, 4.5 GiB; WSClean 89-111 s, 0.6 GiB.

### Seen data (section 3.3; reported, not in the verdict)

- **Pilot** (floor-5's `g1/P/pilot.ms`, floor-6's pilot state):
  - A0: F 278.86 µJy, D_ref 0.466, 341,244 components, 10 cycles, 531 s, 9.2 GiB.
  - SDa: F 329.68 µJy, **D −0.408**, 5,512 s, 18.0 GiB.
  - Sa, Sm, SDm03 and W-SDa: not run (amendment 3).
  - floor-6's outputs on nash, the pilot state's `pilot.json` included, were removed from nash during this run
    (not by this task). The pilot readings use the archived `research/results/floor-6/pilot/pilot.json`
    (T 44.09 µJy, P_ref), which is identical to the one scored against.
- **Scan 10**: not run. floor-6's `ho/P/pilot.ms` was gone when the arm started (`table.dat: No such file`).
- **D1**: SDa D 0.938, O1 P ratio 0.995, N1-N3 pass.

### Post hoc check: does A0's own-scan advantage transfer? (not gating)

A0 cleans unmasked to 3σ. It puts 0.52 and 1.09 Jy into 129,024 and 104,808 pixels outside set A's mask on scans
4 and 14, against 0.106 / 0.652 Jy (SDa) and 0 (SDm03, Sm). F is scored outside that mask on the same
visibilities, so A0 may lower F by modelling noise and artefacts in the scored region. To test this, each scan's
models were scored on the other scan's state (`scripts/cross.sh`). D is against the transferred A0:

| models from → scored on | A0 F (µJy) | SDa D | Sa D | SDm03 D | Sm D | W-SDa D |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| scan 4 → scan 14 | 425.40 | 0.333 | 0.345 | 0.345 | 0.305 | 0.319 |
| scan 14 → scan 4 | 391.66 | −0.237 | −0.245 | −0.024 | 0.018 | −0.280 |

- Scan 4's A0 transfers worst of its own arms: 425 µJy on scan 14, against scan 14's own A0 at 303 µJy. So part of
  A0's own-scan lead on scan 4 is fitted to that scan.
- Scan 14's SDa transfers worse than its A0. Models from another hour angle also carry that scan's
  direction-dependent errors, so this check bounds the confound but does not remove it.
- **The frozen D against A0 is not a clean measure of sky-model quality.** The claim "the default already holds
  the lever" is therefore not made. What is measured is that, under the frozen metric, no SDm03 form beats the
  shipped default consistently on fresh scans.

### Not run, and disclosures

- The reserve is spent as follows:
  - scans 4 and 14: used;
  - scans 6 and 8: metadata, TIME and gain metadata only (amendment 4);
  - scan 12 (E2-A's retry reserve): untouched.

  The coordinator's brief was taken as the release of a0-acceptance's imaging-only reserve.
- X4's MS was written twice: the first write was killed by the restart (amendment 4), and X4 was then simulated
  again from its seeds. X1-X3's prep was rerun after the restart left partial folders. No score existed before
  either.
- The pilot's Sa, Sm, SDm03 and W-SDa, and scan 10's arms, were not run.

## For the coordinator

- **Outcome "not yet"; the default does not change.** GeMClean's SDa fails the WSClean oracle on scan 4 (P ratio
  1.36). Without that clause the outcome is null: the literal SDm03 has D −0.35 on scan 4 against the shipped
  default and +0.25 on scan 14. No code commit.
- **floor-6's 0.717 was against p1's 3 mJy image, not the shipped default.** rang-core's bare `image` section
  (auto-threshold 3σ, unmasked) already removes 0.42-0.53 of that excess on scans 4 and 14 (pilot 0.47).
  Against it, every SDm03 form is scan-dependent: +0.25 to +0.40 on scan 14, −0.24 to −0.72 on scan 4 and the
  pilot. Part of A0's lead is fitted noise in the scored region (post hoc cross-scan check). Read the frozen D
  as "no consistent gain", not as "the default is better".
- **Possible GeMClean defect (not posted):** with `-auto-mask 6 -mgain 0.9 -join-channels`, GeMClean sets its
  mask one major cycle earlier than WSClean on scan 4 and the pilot, at 1.05 mJy against about 0.65 mJy, and its
  model is then worse (P 1.36 × WSClean's). On scan 14 the two agree. This is worth a G4-masks follow-up.
- **Cost:** SDa takes 9-12 × A0's wall (79-99 min at `-j 8`, shared). Sa takes 3.2-3.8 × (paired with Sm). Both
  use 18.1 GiB against 9.2 GiB. GeMClean's joined-channel masked runs take 4-5 × WSClean's wall at 8 × its memory.
- **Reserve:** ESO137 scans 4 and 14 are spent. Scans 6 and 8 remain, with only metadata read. Scan 12 is
  untouched. The brief was taken as the release; the owner may want to confirm that.
- **nash:** the run root `~/rang-data/outputs/sdm03-default-20261118` holds 213 GB: the reserve builds and Sp
  MSs about 60 GB per scan, the fetched tiles 36 GB, and the images. It can be deleted; the compact readings are
  archived. floor-6's run root was already gone from nash during this run, removed by someone else.
- **Check:** `python tools/check_all.py --quick` on Windows, before the hand-back. The full check is left to the
  merge check. The branch adds only research files, the driver, and simulator recipes X1-X4 (no package code).

## Coordinator decision (2026-11-18)

- **The outcome stands at "not yet" under the frozen rule.** Without the oracle clause it would be null. Either way, rang-core's imaging default stays A0, and issue #13 closes with no switch.
- **Possible GeMClean auto-mask defect.** With `-auto-mask 6 -mgain 0.9 -join-channels`, GeMClean's mask is fixed one major cycle earlier than WSClean's (scan 4 and the pilot), and the residual excess is 1.36 × WSClean's. This is opened as its own issue for a G4-masks follow-up, not decided here.
- **Reserve.** Using a0-acceptance's imaging-only reserve was within the brief. Scans 4 and 14 are spent. Scans 6 and 8 had metadata read but no visibilities. Scan 12 is untouched.
- **floor-6 deletion.** The coordinator deleted floor-6's nash outputs on 2026-11-18 during cleanup. That was a coordinator error against the keep-until-v0.3.0 decision. The pilot was scored from the archived `pilot.json`.
- **Cleanup.** The nash run root `~/rang-data/outputs/sdm03-default-20261118` (213 GB) is deleted after the merge, and the compact results stay in `research/results/sdm03-default/`.
