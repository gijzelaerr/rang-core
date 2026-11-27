# The UHF gate: frozen protocol (issue #11)

Branch `uhf-s-fetch` from main `18726ccc`, 2026-11-26. Follows
[uhf-scope.md](uhf-scope.md) (the scope and the frozen data rule; its section
numbers are cited as "scope 2.1" and so on), the unmerged branch `uhf-11`
(commit `860d2b81`: the 0408-65 flux model, band detection, a UHF MVF fixture,
port check P1 and the CARACal and CASA drafts, in `research/uhf-11.md` there)
and [uhf-s-fetch.md](uhf-s-fetch.md) (the data).

**Status: protocol, frozen 2026-11-26 before any UHF visibility, flag or weight
value was read by anyone in this project; the blocks were changed by
amendment 2 (the first ones are on tape), also before any read.** What was read before the freeze is
the four blocks' RDB metadata (telstate: scans, targets, tags, antennas, the
spectral window; uhf-s-fetch.md section 1), and the calibrator model files'
headers and component counts (section 3). None of the blocks' chunks is even on
the archive's object store yet (uhf-s-fetch.md 3.1). Changes after this commit
are dated amendments below section 10, labelled post hoc for anything they
could have seen. Nothing here is measured.

Coordinator decisions D2-D8 (2026-11-26) are recorded in uhf-scope.md; the ones
this protocol rests on are D3 (models), D4 (the CARACal arm) and D5 (the new
numbers), applied in sections 3, 6 and 5.

## 1. What the gate asks

Does `rang-core run` on native MeerKAT UHF data give the same flags, solutions,
corrected data and images as the pinned oracles, within A0's tolerances (A0 =
[a0-acceptance.md](a0-acceptance.md)), where the band does not change the
question; and within new tolerances, each with its reason, where it does
(scope section 3)? It is E2-N's protocol ([e2n-native.md](e2n-native.md)) moved
to UHF, with E2-N's lessons applied: the CASA arm's flag states
([e2n-followup.md](e2n-followup.md)) and matched channel averaging for 3c
([gate3c-rerun.md](gate3c-rerun.md)).

No result here is a novelty claim (AGENTS.md); the gate is parity with oracles.

## 2. Data, selection and the reserve (from the scan table only)

By uhf-scope.md section 5's order (both UHF blocks have 3C 286, both are
native; the smaller wins): **development D = 1740534088**, **held out H =
1737424638**, a different scheduling block (uhf-s-fetch.md section 2).

**D, 1740534088** (58 antennas, 4,096 channels, 544-1088 MHz), katdal track
scans:
- every calibrator scan: J1939-6342 (1934-638) 2 and 34; J1331+3030 (3C 286) 4;
  J1424-4913 (gain) 8, 12, 16, 20, 24, 28, 32;
- the middle three of the five full target scans of J1424-6126: 14, 18, 22
  (250 dumps each, 1.67 h); each is bracketed by gain-calibrator scans and by
  unused target scans;
- **reserve** (fetched with the block, never read unless a fix is tested on the
  target rows): target scans 26 and 30;
- **untouched:** target scan 10 and J1446-4701's scan 6.

**H, 1737424638** (60 antennas), katdal track scans:
- every calibrator scan: J0408-6545 0; J1939-6342 20 and 37; J1331+3030 18;
  J1150-0023 (gain) 2, 6, 10, 14, 22, 23, 27, 31, 35;
- target NGC4472, the middle three of seven: 12, 16, 25;
- **reserve:** 29, 33; **untouched:** 4, 8.

**MS numbering (replaced by amendment 1).** mvftoms numbers the written track scans 1 to N in time order.
The frozen configurations' `data.scans` are that prediction: D
`[1, 2, 4, 6, 7, 8, 9, 10, 11, 12, 14, 16, 17]`, H
`[1, 2, 4, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 17, 19, 20]`. After conversion
the MS map (`ms-map.json`, SCAN_NUMBER to FIELD) is read; if it differs, the
list is rewritten mechanically from the katdal lists above and the rewrite is
recorded before the run. That read is metadata, as E2-N's.

**The whole blocks are converted** (uhf-s-fetch.md section 3); the selection is
made by `data.scans`, so the reserve needs no second fetch. (Replaced by
amendment 1: the gate MS holds the selection only.)

**Order of reading.** D's run and its post chain run once, and every gated row
of D is read and recorded. H is then read **once**: with the configuration
frozen here, or with a fix frozen by a dated amendment after D's read and before
H's run. H's rows decide the gate. A fix tested on H is not tested again on H.

## 3. Calibrator models (D3)

No CC BY-NC material ships in the package or the repository (coordinator,
2026-11-17). Field models are read at run time from nash.

| Source | Role | Model in every arm | Reason |
| --- | --- | --- | --- |
| PKS 1934-638 | fcal and bpcal on D and H | **the DOI UHF field model**, Hugo (2021), DOI 10.48479/hhhy-4r55, `fitted.PKS1934.UBand.wsclean.cat.txt`, SHA-256 `376179423b04…aeec5`, 7,779 point components, ordinary polynomial spectra (`LogarithmicSI` false), read from `~/rang-data/uhf/reference/hhhy-4r55/` | a point model biases UHF bandpass by up to 40 % (scope 2.1); the DOI release is the published, versioned one; rang's `formats.sky.load_any` reads it (checked 2026-11-26: 7,779 components, PRIM 15.089 Jy at 1283.79 MHz) |
| 3C 286 | xcal | `NRAO_XCAL` (rang's `polcal.model: {source: nrao, name: 3C286}`; CASA `setjy` manual with the same polindex, polangle, `rotmeas` 0) | the same model in both arms. It is flat in p and χ from 1.47 GHz, so at UHF it is an extrapolation (scope 2.1: SILENT). It sets the frame the parity rows compare in, not a claim about 3C 286 at UHF |
| PKS 0408-65 | H only: a check source in no solve | none in the solve. Its corrected Stokes I is compared with two models, reported: CARACal 8f7bb363's 2016 cubic (rang `fluxstd` source `0408-65` on branch `uhf-11`; valid from 843 MHz) and the DOI 0407-65 field model's central component (Hugo, DOI 10.48479/ez63-vx81, SHA-256 `bcd806d4…0bf55`) | neither model is validated at UHF below 843 MHz (scope 2.1). Read before the freeze from the files alone: the DOI central component is within 2.6 % of the cubic over 544-1088 MHz (+1.7 % at 544, +0.5 % at 816, −2.6 % at 1088 MHz); the field adds more flux. A check source in no solve keeps the solve independent of either |

Also fixed now:
- **MODEL_DATA for 1934-638** is written by rang (`calmodels.set_model` with
  the catalogue, the call rang's calibrate makes) and used by the CASA arm too:
  A0 rule 3, the same model column for every arm. CASA has no route from a
  WSClean component list to `setjy`.
- **Model row** (gated, section 5): that MODEL_DATA against an independent
  float64 direct Fourier sum of the same 7,779 components and spectra (numpy,
  a script committed before it reads a UHF MS) on 2,000 rows taken at a fixed
  stride from D's first 1934-638 scan, every channel and correlation.
- **CARACal's own UHF catalogue** (`1934-collapsed-uhf-cat.txt`, SHA-256
  `30e4b6ff…b32e`, 7,830 components) is what CARACal's crystalball step uses in
  the CARACal arm (section 6). Its central component differs from the DOI's by
  up to 2 % (scope 2.1). E3 reports the difference; it is not gated.
- **CARACal's 0407 catalogue does not parse in rang** (`load_any`: "WSClean
  line 2 has 12 fields, expected 11"; checked 2026-11-26). Nothing in this
  protocol needs it.
- **Cost risk, named now:** the full 7,779-component predict over two 75-dump
  scans at 4,096 channels is about 8e12 complex exponentials. If rang's
  calibrate stage has not finished its model step in 12 hours, the run is
  stopped and an amendment decides (for example a flux cut), before any
  solution is read.

## 4. Configuration (frozen)

Files in [results/uhf-gate/](results/uhf-gate/):
[uhf-dev.yaml](results/uhf-gate/uhf-dev.yaml) (D),
[uhf-heldout.yaml](results/uhf-gate/uhf-heldout.yaml) (H),
[uhf-dev-3c.yaml](results/uhf-gate/uhf-dev-3c.yaml) and
[uhf-heldout-3c.yaml](results/uhf-gate/uhf-heldout-3c.yaml) (gate 3c and the
target rows), [caracal-uhf.yml](results/uhf-gate/caracal-uhf.yml) (CARACal).
`rang-core config check` (rang-core 0.4.0, nash, 2026-11-26, without an MS): D
and H "valid for flag, calibrate, apply, image, selfcal"; both 3c files "valid
for image". The check against each MS's fields runs after conversion and must
give the same verdict (section 8).

They are E2-N's `e2n.yaml` with these changes only:

| Key | UHF gate | E2-N | Reason |
| --- | --- | --- | --- |
| roles | D: fcal = bpcal J1939-6342, gcal J1424-4913, xcal J1331+3030, target J1424-6126. H: gcal J1150-0023, target NGC4472, the rest as D | this track's | the blocks' calibrators |
| J0408-6545 (H) | corrected like the secondary (K, F, B, Kcross, Xf, Df); in no solve | the same on E2-N | the leakage and flux-transfer check source (section 5) |
| `data.scans` | section 2 (removed by amendment 1) | none | the frozen selection |
| `flag.strategy` | CARACal 8f7bb363 `firstpass_UHF.yaml` (SHA-256 `4c336933…9856`, copied into the run root and checked; not committed, GPL-2.0) | the L-band calibrator first pass | CARACal's UHF strategy is the flagging oracle's; the port is flag for flag with it on three L-band scans (uhf-11 P1: 0 of 1.18e9 cells) |
| `flag.static_masks` | `tricolour` (both of Tricolour 0.2.1's masks, as Tricolour loads them) | the same | uhf-11 section 2: choosing a mask per band would depart from the oracle |
| `calibrate.model` | `source: lsm`, the DOI 1934-638 catalogue (section 3) | `setjy`, SR2016 | section 3 |
| `image.size`, `scale` | 6,144², 3″ (5.12°) | 4,096², 3″ | D5: section 5 |
| `image.average_channels` | 4: 1,024 channels of 531 kHz | 2 (512 of 1.67 MHz) | Δν/ν 6.5e-4 at 816 MHz, half E2-N's 1.3e-3; the image-stage image is reported, and gate 3c uses the unaveraged file |
| 3c and target rows | the `*-3c.yaml` files: `run.stages: [image]` on CORRECTED_1GC with `average_channels: 1` | 3c on the averaged image | gate3c-rerun.md: unaveraged, GeMClean met dirty L∞ (1.13e-6 on E2-N) and its compact scatter fell from 2.41 % to 1.31 % |

Everything else is E2-N's: `weights: uniform`, `refant: auto`, `uvrange >150`,
`average_time`, `average_freq` and `casa_phase_weights` on, the full-Stokes
chain (K, G, B; Gsec, Asec, F; Gpol, KCROSS, Xf, Df with `extendflags`),
`feed_angle_rotation: −90`, `parang`, Briggs 0.5, 8 joined channels, 2-term
fit, mask 5σ, clean to 3σ, multiscale, two selfcal rounds (Sp, Sa at solint
120, `average_time`).

**Code.** A Linux wheel built on nash by `tools/wheel/build.py` from main at
the first merge that contains this note (with `uhf-11` if it is merged by then:
it changes no L-band behaviour and nothing in this chain but the band warning's
text). Its SHA-256 and commit go in the result. One venv, made fresh.

**`weights: as_is`:** not run (A0 rule 3 asks for it on E2-N only; E2-N's own
was deferred by the coordinator, 2026-11-18).

## 5. Gates and tolerances (frozen)

Rows read on D and on H alike unless marked. Every A0 tolerance is unchanged
(A0 rule 1: never loosened). New numbers (D5) carry their reason.

**Carried over unchanged** (A0 6.1-6.3, as E2-N section 6):

| Gate | Measure | Tolerance |
| --- | --- | --- |
| 1 | `rang-core run` exit 0; every stage in the receipt; no hand step | as A0 |
| 2a | FLAG and FLAG_ROW restored from `rang_original` equal the hashes taken after conversion | equal |
| 2b | casacore opens every table; CASA `listobs`, `flagmanager`; CASA `applycal` with rang's tables against rang's apply (in place); WSClean `-niter 0` on CORRECTED_DATA and MODEL_DATA; dask-ms reads the MS | exit 0; applycal class C |
| 2c | astropy WCS parses every FITS rang wrote | valid |
| 3a | Tricolour 0.2.1 with `firstpass_UHF.yaml`, `-fs polarisation -dc DATA -dpm`, native input flags, every field | 0 cells, or A0's chunk-edge rule |
| 3b | CASA 6.7.6.14 on the flag states of section 7: K, KCROSS, Xf, Df, Gpol by their limits; fcal K G B and gcal K F B composites class B | K median ≤ 0.01 ns, p95 ≤ 0.03 ns; KCROSS ≤ 0.02 ns; Xf median ≤ 0.5°, p95 ≤ 2°; Df median ≤ 1e-3, p95 ≤ 5e-3; Gpol median ≤ 0.1°; class B median 7e-4, p95 3e-3 |
| 3c | WSClean 3.7 on rang's CORRECTED_1GC against GeMClean's image of the same column, both unaveraged (`*-3c.yaml`), same argv: dirty and cleaned | dirty L∞ ≤ 1e-6 of the peak; compact sources median within 0.5 %, robust scatter ≤ 1 % |
| Secondary (J1424-4913 on D, J1150-0023 on H) | E2-B's 1830-211 row: I, p, χ against CASA after the full chain, per 100 MHz bin | I within 1 %, \|Δp\| ≤ 0.1 point, \|Δχ\| ≤ 1° |
| 3C 286 parity | p and χ per 100 MHz bin (section 5.1), visibility domain, sky frame, rang against CASA, bins with ≥ 10 % unflagged | \|Δp\| ≤ 0.1 point, \|Δχ\| ≤ 0.5° |
| Target, compact sources | ≥ 10σ isolated sources inside the field limit, GeMClean's unaveraged image (`*-3c.yaml`) against the oracle (CASA-corrected data imaged by WSClean 3.7, same argv) | median within 1 %, robust scatter ≤ 1.5 % |
| Target, noise and dynamic range | off-source rms; peak/rms; same pair of images | rms ≤ 1.2 × the oracle's; peak/rms ≥ 0.8 × |
| Self-calibration | rms after ≤ 1.02 × before (image 1 from CORRECTED_1GC against the final image); gains class B against QuartiCal 0.2.7 in E2-A 9.10's amended averaged form (labelled) | as A0 |

**New (D5), each with its reason:**

| Row | Measure | Tolerance | Reason |
| --- | --- | --- | --- |
| Model | rang's 1934-638 MODEL_DATA against the float64 direct sum (section 3) | per cell ≤ 1e-5 of the peak \|model visibility\| | A0 3c's MODEL_DATA bound; a direct sum is exact up to rang's complex64 cast |
| Image geometry | 6,144² × 3″ | – | 3″ is below the Nyquist pixel at the top of the band (max baseline about 7.7 km: 3.7″ at 1088 MHz), so WSClean drops no visibility (gate3c-rerun's finding); 5.12° is 3.2 primary-beam FWHM at 816 MHz and 2.1 at 544 MHz (scope 1). 4,096 × 4.5″ (scope 2.7's other proposal) is coarser than Nyquist and is not used |
| Field limit of the scorer | inner **1.0°** radius, every image row | – | the L-band 0.7° was the 512-channel smearing limit; unaveraged at UHF β < 0.1 at 1° (Δν/ν 2.4e-4 at 544 MHz, beam 15″), so the limit is set by the primary beam (FWHM 1.19° at 1088 MHz) |
| **H only:** J0408-6545 leakage | Df solved on 1934-638 and applied by the run's own apply to J0408-6545 (in no solve, unpolarised): peak of the Q, U and V MFS images over I, unit weights, inner 0.5°; both arms | each ≤ **0.5 %**; rang's each ≤ 1.2 × CASA's | L band's 0.3 % was four times the publisher's 0.08 %; at UHF Hugo (2021) finds second-order leakage at −30 to −40 dB next to strong sources (0.1-1 %), which a linearised Df does not model; 0.5 % (−33 dB) is inside that range. The 1.2 × is A0 3c's QUV bound |
| **H only:** J0408-6545 flux transfer | corrected Stokes I per 100 MHz bin (section 5.1), visibility domain, scan 0 (4 h before the scale is set on 1934-638's scans 20, 37), rang against CASA | within **1 %** in every bin with ≥ 10 % unflagged | the secondary row's 1 %: both arms use one model and one scale. Against either 0408-65 model: **reported, not gated** (section 3: the models are unvalidated below 843 MHz and differ by up to 2.6 %) |

**Reported, not gated:**
- **3C 286 transfer (p, χ).** Each block has one 3C 286 scan, so Xf and Df
  from another scan do not exist and the transfer would be circular (as E2-N
  section 6). There is no ionospheric RM correction: a 2 rad m⁻² change moves
  χ by 15.5° at 816 MHz and 34.8° at 544 MHz (scope 2.6). Reported: p and χ per
  bin, same scan, labelled "same-scan, not a transfer", beside the model's flat
  9.8 %, 33° and beside Perley and Butler (2013) where their table covers the
  bin.
- **1934-638's corrected Stokes I against its catalogue** per bin, on the
  second scan (D 34, H 37); not a transfer (B is solved over both scans).
- **Absolute flux** of the secondaries from `fluxscale`, both arms.
- **Native size** of K, KCROSS and Xf (E2-N's `e2n_native_size.py`), and the
  DATA-state probe of section 8.
- **Flag fractions** after each stage, and the image-stage (averaged) image
  against the unaveraged one.
- **E3 (gate 4)**, section 6.

### 5.1 Frequency bins

100 MHz bins: 544-644, 644-744, 744-844, 844-944, 944-1044 MHz (the last 44 MHz
of the band are not binned); a bin is scored when at least 10 % of its cells
are unflagged in both arms.

## 6. Oracles (A0 rule 8, pinned; on nash under apptainer, as E2-N amendment 2)

- **CASA 6.7.6.14** (`rang-o-casa_6.7.6.14.sif`): K, G, B, Gsec, F, fluxscale,
  Gpol, KCROSS, Xf, Df, `setjy` for 3C 286, `applycal`.
- **WSClean 3.7** (the KERN build inside `rang-o-casa_6.7.6.14.sif`; the native
  image does not run on nash's Xeon, E2-N amendment 2, build check 1.35e-7).
- **Tricolour 0.2.1** (`rang-tricolour_0.2.1-e1.sif`) with `firstpass_UHF.yaml`.
- **QuartiCal 0.2.7** (`rang-formats-oracle_20261030.sif`).
- **CARACal 8f7bb363** with [caracal-uhf.yml](results/uhf-gate/caracal-uhf.yml)
  (D4): `firstpass_UHF.yaml` in the calibrator flag worker;
  `meerkat_skymodel: false` with `meerkat_crystalball_skymodel: true` (so its
  UHF crystalball catalogue is used, not the L-band lsm); no L-band `chans`
  flag or mask; `refant: auto`; the shipped full-Stokes polcal section; selfcal
  off. Read with E3's frozen words ("comparable": every quality measure within
  20 % and flux within 2 %; speed within a factor of 1.5); no pass bar. If
  CARACal's Stimela cab images do not run on nash, its sequence is run by hand
  in CASA and labelled so (A0 6.4), or the arm is "not run" with the reason.

## 7. The CASA arm (E2-N's chain with e2n-followup's fix)

E2-N's `e2n_casa3b.py` calls (refants of rang's `auto` choice from the
receipt, `refantmode flex`, `minsnr` 3, `minblperant` 4, solints, combine,
uvrange) with:
- **e2n-followup's flag-state rule:** each CASA solve runs on the flag state in
  which rang solved the same term: K, G, B and Gsec on rang's FLAG after the
  flag stage; Gapp/F, fluxscale, Gpol, KCROSS, Xf, Df and the Df clip on rang's
  FLAG after calibrate (after `extendflags`); `applycal` on the latter. On E2-N
  this rule removed CASA's 19 lost antennas (e2n-followup.md 1.2).
- **Models:** 1934-638 from rang's MODEL_DATA (section 3), so CASA's first
  `setjy` is not called; 3C 286 by `setjy` manual with `NRAO_XCAL`'s numbers, as
  E2-N.
- Field names and scans from section 2; scripts adapted in names and paths
  only, each run once on E2-N's archived inputs or a development slice before it
  reads a UHF result (E2-N section 6's rule).

## 8. Smoke, order and stop rules

1. **After conversion, before anything reads a visibility:** the MS map and the
   `data.scans` check (section 2); `rang-core config check` of each file
   against its MS, the same verdicts as section 4; the token search.
2. **DATA-state probe** (A0 2.2's, E2-N section 2), on D's 1934-638 and
   3C 286 scans, channels 2,048-2,079 (816.0-820.1 MHz), the first 800 rows:
   reported first, read under E2-N's rule ("native, unphased" below 0.5
   coherence, "observatory-phased" at 0.9 or above). Every gate is read as
   frozen in each case.
3. **Dry run** (E2-N amendment 3's rule): `uhf-dev.yaml`'s shape on A1 small
   (fields mapped, 1,024², multiscale off, the DOI catalogue as the model), the
   full post chain on nash; every step rc 0. Its scores mean nothing and are
   not read. A failure is fixed on development data and recorded before D runs.
4. **D's run, once**, then D's post chain; then H's (section 2's order).
5. **Disk:** every command that writes to an MS runs inside
   `e2_diskguard.py` with a 2,000 GiB floor on nash's /home. **Bookings:** the
   rang arm one shared lock job of 16 slots and 128 GB (6,144² images; E2-N's
   4,096² peaked at 36.4 GB), `RAYON_NUM_THREADS=16`; each oracle step its own
   booking as E2-N's; `nice -n 19 ionice -c3`. Wall times are indicative on a
   shared host, not timing claims, and go to [tool-timings.md](tool-timings.md).

## 9. Decision rule

- Each gated row of section 5 is read met or not met against its tolerance.
  **#11's UHF gate is met only if every gated row on H is met**; D's rows are
  read and reported, and a miss on D allows one fix by amendment before H.
- "Not checked" (an oracle that cannot run, with the reason) is never read as
  met. Nothing is retuned against H and presented as a pass. A fix found on H
  is tested on H's reserve (target rows only) or labelled "seen".
- The release wording follows the result: "UHF validated" only if met; else
  the misses by row, as E2-N's.

## 10. Not checked before the freeze

- Whether CARACal's Stimela cab images run on nash.
- How long rang's 7,779-component predict takes at 4,096 channels (section 3's
  stop rule).
- 3C 286's and 3C 138's p and χ across 544-1088 MHz in Perley-Butler 2013 (the
  reported rows cite them where tabulated).
- Whether UHF static-mask coverage below 915 MHz is enough (reported through
  flag fractions; not a gate).
- katbeam or the holography beam: nothing in the chain applies a primary beam.

## Amendment 1 (2026-11-26, before any visibility, flag or weight was read; not post hoc)

Written after a review of the first freeze (commit `9cf2bbd3`), the same day; no
block was staged, so nothing had been or could have been read. Three changes:

1. **The gate MS holds only the selection** (E2-N's route). In the first freeze
   the whole block was converted and `data.scans` chose the scans. Only rang
   honours `data.scans`: Tricolour (3a), the flag hashes (2a), dask-ms and
   WSClean (2b), CASA's calls and the scorers would have read the reserve and
   the untouched scans too. Now each UHF block is converted by `mvftoms --scans`
   with section 2's katdal list (D `2,4,8,12,14,16,18,20,22,24,28,32,34`; H
   `0,2,6,10,12,14,16,18,20,22,23,25,27,31,35,37`), the four configurations
   have no `data.scans`, and the MS map is still read and recorded before the
   run. The MVF chunks of every track scan are fetched and kept, so the reserve
   is converted from them only if a fix is tested on it. The S-band blocks are
   converted whole (no selection is frozen for them).
2. **CARACal's roles are named** (`caracal-uhf.yml` obsconf: fcal and bpcal
   J1939-6342, xcal J1331+3030, gcal and target `all`). On H, J0408-6545 is also
   tagged `fluxcal` and `bpcal`, and CARACal's tag detection could have taken
   it as a primary with CARACal's own 0407 catalogue. E3 still reports that
   CARACal's 1934-638 catalogue is not the DOI file.
3. **Disclosed: calibrate's `average_time` and `average_freq` with a field
   model.** Both average the data and the model separately within each
   solution interval (the keys' documented behaviour, `core_config.py`; CASA's
   pre-averaging does the same), and `bandpass_model_divided` stays false as on
   E2-N. With a field model rather than a phase-centre point, the averaged model
   is no longer a point of constant amplitude, so this is CASA's approximation
   in both arms, not an exact solve. Both arms make it; it is not a gate
   change.

Unchanged: every tolerance, the split, the models and the decision rule.

## Amendment 2 (2026-11-26 10:15 UTC, before any visibility, flag or weight was read; not post hoc)

**The blocks change; the reason is the archive's storage, not their data.** The
first freeze's four blocks are on tape (lifecycle ARCHIVED; the archive offers
no restage of a single block; uhf-s-fetch.md 3.1). Their data were never
available, so nothing of them was read. The coordinator chose four public
blocks that are online (lifecycle AVAILABLE); their metadata only was read
(uhf-s-fetch.md amendment 2), and all four pass the frozen data rule.

**Development and held-out, by section 5 of uhf-scope.md as before.** Both UHF
blocks have 3C 286 and both are native, so the smaller is development:
**D = 1752418159** (SCI-20241101-MH-01, 63 antennas, 458.0 GB of cross
visibilities) and **H = 1726220298** (SCI-20230907-ZK-01, 60 antennas, 772.8 GB),
different scheduling blocks.

**Section 2 for the new blocks** (katdal track scans; dumps in brackets):
- **D, 1752418159.** J1939-6342: 1 (76), 39 (75). J1331+3030 as polarisation
  calibrator: 3 (38), 37 (37). Gain calibrator J1609+2641 (CTD93): 15, 19, 31,
  35. Target ILTJ153010: 17, 33 (225 each), each bracketed by CTD93.
  **Conversion selection** `1,3,15,17,19,31,33,35,37,39`. This block also uses
  3C 286 as the gain calibrator of two other targets (a second catalogue entry
  of J1331+3030 tagged `gaincal`: scans 5, 9, 13, 21, 25, 29; katdal warns of the
  duplicate name). Those scans and the targets ILTJ131904 and ILTJ132848 (7, 11,
  23, 27) are **untouched**, so J1331+3030 has one role. D has **no reserve**
  (its only CTD93-bracketed target scans are both used); a fix found on D is
  tested on H, as section 2's order says.
- **H, 1726220298.** J0408-6545: 0 (77, the check source, in no solve).
  J1939-6342: 32 (74), 60 (75). J1331+3030: 2, 30 (37 each). Gain calibrator
  J1605-1734 (1602-174): every one of its 15 scans. Target HD 142184 (HD142184
  in the MS), 12 scans of 224-225 dumps: the middle three **22, 26, 36**;
  **reserve 40, 44**; untouched 6, 10, 14, 18, 48, 52, 56. **Conversion
  selection** `0,2,4,8,12,16,20,22,24,26,28,30,32,34,36,38,42,46,50,54,58,60`;
  **fetched** that plus the reserve.
- Fetch: the UHF blocks fetch their selection (and H's reserve) only, as E2-N
  did; the S-band blocks every track scan.

**Configurations.** The four rang files keep their names and change only the
roles: D gain calibrator J1609+2641, target ILTJ153010; H gain calibrator
J1605-1734, target HD142184 (with the secondary's gainfield). The CARACal file
becomes two, `caracal-uhf-dev.yml` and `caracal-uhf-heldout.yml`, with the gain
calibrator and target named (D's 3C 286 is also tagged `gaincal`).

**Consequences named now.**
- Both blocks now have **two 3C 286 scans** (D 3 and 37, 3.6 h apart; H 2 and
  30). Xf is still solved with `combine: scan` over both, so the 3C 286
  transfer stays circular and is reported only, as frozen.
- D has two 1934-638 scans and no 0408-65; H has 0408-65 (scan 0) and two
  1934-638 scans, so H's 0408-65 rows of section 5 stand as frozen.
- Everything else is unchanged: tolerances, models, the CASA rule, the decision
  rule.

## Amendment 3 (2026-11-27 09:22 SAST; post hoc: after D attempt 1's flag stage, before any solution, corrected value or image of D was read)

**The model step's cost.** Section 3 named the risk and gave a 12 h stop rule.
D attempt 1 measured it (run log below): rang's `core.predict_components` is
single-threaded, 29.6 ns per row × channel × component on nash, so one predict
of the DOI 1934-638 catalogue takes about 77 h on D and about 69 h on H, and
the chain makes two per block (calibrate and `casa-model`).

**Coordinator decision, option (a).** The predict is parallelised over rows on
main by a separate task (`predict-par`), gated by bit-identity against the
current single-threaded path. Section 4's Code clause changes only in this:
the wheel is built from main at the merge of `predict-par` (its commit and
SHA-256 go in the result), and its predict is bit-identical to the frozen
wheel's. Models, selection, tolerances, the CASA rule and the decision rule are
as frozen. Smoke 8.3 is run again on the new wheel before D.

**D attempt 1 stopped.** `rang-core run` (pid 3773031) was sent SIGTERM at
09:22:29 SAST on the coordinator's word (the chain logged rc 241); the 12 h
watchdog was disarmed first. At the stop calibrate read "running" and
`rang-run/calibrate/` held no entry: no solution, corrected value or image of D
had been written or read. What attempt 1 showed is its flag stage (the flag
fractions in the run log) and the model step's IO. Its result directory is kept
as `D/R-attempt1/`; D's MS is copied again from the fetched one and checked
against its receipt before attempt 2, and the flag stage runs again as frozen.
The CARACal arm on D is independent of rang's run and continues.

## Run log

### Smoke 8.3 (2026-11-26/27, nash, A1 small; scores not read)

Run root `~/rang-data/outputs/uhf-gate-20261126/smoke/` (R/ holds every step's
output), wheel at c31551f1 (SHA-256 `ece91edb…5dcc`), scripts
`research/results/uhf-gate/scripts/` (`ug.py`, `ug_chain.sh`, `ug_dryrun.py`).
`rang-core run` passed first time (111 s, every stage of `run.stages`). Four
steps of the post chain failed and were fixed on this development data before D;
none is a protocol change (no tolerance, selection or rule moved):

1. **model-row, the pool** (`d795cbcf`): Python 3.14 starts pool workers by
   forkserver, so they did not see the catalogue; the pool is now forked
   explicitly.
2. **model-row, the sign** (`c3822d6d`): the direct sum used
   `exp(−2πi ν(ul+vm+w(n−1))/c)`; rang's MODEL_DATA equalled its complex
   conjugate to 4.5e-8 of the peak (720 rows × 64 channels), and against it
   differed by up to 2.0 × the peak. The MS convention is the positive phase:
   rang's `predict.rs` (ported from codex-africanus, validated in
   core-phase3c-a.md) and gemclean.md 2.7 state it, and g6-predict.md found
   `predict_components` equal to WSClean's predict without conjugation. The
   script now sums with `exp(+2πi …)`; it stays independent of rang (numpy,
   its own catalogue parser). The `exp(−2πi …)` of `wgridder.rs`'s
   `dirty2vis` is ducc0's adjoint in that gridder's own frame (`flip_w`), not
   the MS's sign. On A1 the row now reads 4.5e-8 (tolerance 1e-5); the number
   means nothing for the gate.
3. **score3c and later scorers, the extension** (`399aaf2e`): `e1_run.py` puts
   the worktree's `python/` first, which has no `_core`; the chain links the
   frozen wheel's `_core.abi3.so` there (the worktree's `python/` is the
   wheel's source: `git diff c31551f1 -- python core src` is empty).
4. **leakage, the PSF name** (`cbe56436`): with `-join-polarizations` WSClean
   writes one `-MFS-psf.fits`, not one per polarisation.

Then all 51 steps returned 0 (gate 1 met, gate 2a's hashes restored, CASA's 14
tasks without error). Wall times: tricolour 316 s, qc-selfcal 186 s, every other
step under 45 s. The CARACal arm's driver is `scripts/ug_caracal.sh` (its own
copy of the fetched MS; tricolour 1.5.0's Stimela image was pulled from
`quay.io/stimela/tricolour:1.5.0` on 2026-11-27, recorded in nash's
`stimela-sif/pull-list.txt`; every other cab image was already there).

### D attempt 1 (2026-11-27, nash; measured; nothing of D's solutions read)

- **Launch.** Scripts at `793c08df`, wheel `ece91edb…5dcc` (c31551f1), configs as
  committed (`D/R/launch.txt` holds the hashes). Section 8.1's check against the
  MS gave section 4's verdicts: `uhf-dev.yaml` "valid for flag, calibrate, apply,
  image, selfcal", `uhf-dev-3c.yaml` "valid for image" (with the band warning).
  `rang-core run` started 06:50 SAST in one shared booking of 16 slots and 128 GB.
- **Flag stage:** done in 6,216.6 s; flagged 14.8 % before, 31.3 % after
  (`state.json`; a flag fraction, reported in section 5, not a gate).
- **Calibrate** started 08:33:47 SAST. The model step allocated the 188 GB
  MODEL_DATA column (about 11 min of IO), then ran on one thread.
- **The section 3 cost risk is real.** rang's `core.predict_components`
  (`core/src/predict.rs`) is a single-threaded scalar loop over components, rows
  and channels. Benchmarked on nash with the frozen wheel
  (`scripts/bench_predict.py`, 1 slot, 20 rows × 4,096 channels × 7,779
  components): **29.6 ns per element, 0.944 s per row.** D's 1934-638 rows are
  294,903 (scans 1 and 10 of the MS, 148,428 + 146,475; no autocorrelations),
  so **one predict takes about 77 h**. The chain needs it twice per block
  (calibrate, and `casa-model` for the CASA arm, the same call). H's 1934-638
  rows are about 263,700 (149 dumps × 1,770 baselines), about 69 h each: about
  290 h of predict for the gate as frozen.
- **The stop rule is armed, not yet applied.** `stop_rule.sh` (detached on
  nash; log `D/R/stop-rule.log`) sends SIGTERM to the `rang-core run` process
  alone at **20:33:47 SAST on 2026-11-27** (12 h after calibrate started), only if
  calibrate still reads "running" and `rang-run/calibrate/` holds no solution.
  `model_watch.sh` logs the process IO every 10 min (`D/R/model-watch.log`).
  The amendment that follows is the coordinator's (section 3).
- **CARACal arm on D** (reported only): started 07:28 on its own copy of the
  fetched MS (`cp -a` 837 s, `sha256sum -c` against the receipt 1,303 s, equal).
  It runs `run.yml`: the frozen `caracal-uhf-dev.yml` with two mechanical edits,
  recorded in `D/caracal/run.yml.diff`: `getdata.dataid` set to `1752418159` (the
  frozen file leaves it empty), and `flag_mask.mask: ''` (CARACal's schema
  requires the key even with the worker disabled, and rejected the frozen file;
  a command-line override is not validated). Its Tricolour cab ignored
  `OMP_NUM_THREADS` and took all 36 cores; the CARACal process tree was pinned to
  cores 20-35 (its 16 booked slots) at 07:53, and `ug_caracal.sh` now pins it from
  the start. transform, prep and flag done; crosscal's crystalball predict was
  running at 09:00.
- **CARACal arm on D: failed in crosscal (gate 4: not checked).** It ended rc 1
  at 17:30:50 after 36,129 s wall (peak RSS 110 GB). Crystalball's 1934-638
  predict took about 7 h; the primary's K, G, B, A, K, G, B solves ran; the
  secondary's first solve (`delay_cal-1gc1-0-0-secondary`, CASA `gaincal` K on
  J1609+2641) stopped on "TSM: no array in row 222642 of column MODEL_DATA" of
  `1752418159-cal.ms`: crystalball creates MODEL_DATA and fills only the
  fcal's rows, and nothing in this configuration sets the other fields' model
  (the L-band path's `setjy` would). Not repaired: a hand step in the oracle's
  sequence would have to be labelled as such (section 6), and the arm has no pass
  bar. Kept on nash: `D/caracal/msdir/1752418159-cal.ms` (209 GB, the split, flags
  and primary tables as CARACal left them), `D/caracal/output/` (caltables, logs);
  the raw-MS copy was deleted. Whether to rerun with the secondary's model set
  (labelled), or to read E3 from the primary's tables alone, is the coordinator's.

### Smoke 8.3 again, on amendment 3's wheel (2026-11-27, nash; scores not read)

Wheel built on nash by `tools/wheel/build.py` from main `8474b790` (the
`predict-par` merge `60e68d16` plus STATE), SHA-256 `5ea3a37d…f093`, in a fresh
venv with the frozen venv's other seven packages at the same versions. Spot check
before use (`scripts/bitcheck.py`): 40 rows × 4,096 channels × 7,779 components,
the new wheel at 8 threads against the frozen wheel at 1, **bit-identical**. The
nash worktree is uhf-gate `c8ef4097` (main merged; `python/`, `core/` and `src/`
equal to `8474b790`), its `_core` linked to the new wheel. Smoke root
`smoke2/`: all 51 steps rc 0 on the first try (run 85 s); the model row read
4.4968e-8, the same as on the frozen wheel.

### D attempt 2 (2026-11-27, nash)

Fresh MS copy equal to its receipt. Section 8.1's check gave section 4's
verdicts again. The chain started 17:43:17 SAST with the run in one booking of
32 slots and 128 GB (`RUN_SLOTS=32`, so `RAYON_NUM_THREADS=32` for the
pipeline process, which runs the model step); `D/R/launch.txt` holds the
commits and hashes.

## For the coordinator

- Frozen: this note and the files in `results/uhf-gate/`. After amendment 2,
  D = 1752418159 and H = 1726220298 by the frozen rule (the first blocks are on
  tape).
- Merge `uhf-11` first or with this branch: the 0408-65 cubic for H's reported
  row lives there. Both branches append to uhf-scope.md.
- New gate numbers (D5): J0408-6545 leakage 0.5 % (H), J0408-6545 flux
  transfer rang against CASA 1 % (H), the model row 1e-5, geometry 6,144 × 3″,
  field limit 1.0°. The 3C 286 transfer is reported only.
