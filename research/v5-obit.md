# ra-ng: Obit MFImage as a second imaging oracle (task V5)

Status, 2026-11-12: **protocol frozen** (sections 1-6, at the commit that adds section 8's
plumbing record; no timed or CLEAN comparison run existed then). Timing runs queue behind E2. Task V5 of [vision.md](vision.md): Obit (W. D.
Cotton, NRAO), whose wideband imager MFImage is used for MeerKAT, next to WSClean 3.7 as an
oracle for GeMClean. No novelty claim is sought or will be made: this is an oracle comparison.

## 1. Obit: version, build, data path

- **Source.** `https://github.com/bill-cotton/Obit`, commit `dc2669429fdb5bfde2910f7f55e46e55df3ee204`
  (2026-10-09, "Bug fixes, ObitView enhancements"; MFImage.TDF copyright 2010-2025). Newer than the
  KERN-10 package (`obit 27JUL20a-1kern4`), which is not used.
- **Build.** [`tools/oracles/obit/Dockerfile`](../tools/oracles/obit/Dockerfile), image
  `rang-obit:dc26694`: Ubuntu 24.04, Ubuntu's cfitsio, FFTW3, GSL, GLib, zlib and xmlrpc-c;
  `ObitSystem/Obit` only (library, 100 tasks, Python module); no ObitView, ObitTalk, ObitSD,
  plplot or X. Built under the heavy lock (shared slots); nothing installed on the host. Log
  "Obit ver. 681"; MFImage binary 11,917,040 bytes; 455 compiler warnings; full build about 230 s.
  Deviations from Obit's own recipe, all in [`build.sh`](../tools/oracles/obit/build.sh) and
  [`build_py.sh`](../tools/oracles/obit/build_py.sh):
  - configure ignores `CFLAGS` and writes `-g -O3 -fPIC -msse` into every Makefile; `-msse` is
    replaced there by `-march=native` (as for `rang-wsclean-native:3.7`), keeping each Makefile's
    own flags (the tasks' `-DFASTOBITMEM`), which a `CFLAGS=` on the make line would drop;
  - the top-level make targets do not depend on each other, so they are run in order
    (`versionupdate cfitsioupdate xmlrpcupdate srcupdate libupdate taskupdate`), parallel inside each;
  - the bundled `six.py` 1.12.0 fails on Python 3.12 and is removed (Ubuntu's python3-six 1.16 is
    used); the Python module is built in place (`setup.py build_ext --inplace`);
  - python-casacore 3.7.1 and astropy 6.1.7 from PyPI, for the converter and the checks.
- **Data path.** Obit reads only its own UV FITS table form (an `AIPS UV` binary table with AIPS
  SU, FQ, AN tables), not random-groups UVFITS from CASA's `exportuvfits`, and AIPS is not
  installed. [`ms_to_obit.py`](results/v5-obit-scripts/ms_to_obit.py) writes one MS field in that
  form through Obit's own Python module, following Obit's MeerKAT writer
  (`python/MeerKATH5toAIPS.py`) and its `MKATTemplate.uvtab.gz`: rows of the field, cross
  correlations only (WSClean and GeMClean drop autocorrelations too), XX and YY only (Stokes I is
  all that is imaged), the MS's UVW and visibilities unchanged, u, v, w in wavelengths at the first
  channel, WEIGHT_SPECTRUM (else WEIGHT) with FLAG or FLAG_ROW as a negative weight (AIPS's flag).
  The conversion is timed and reported apart from imaging. Obit's Python `UV.Write(firstVis=k)`
  stores k − 1 in the descriptor and the FITS writer treats that as the 1-based row, and `Open`
  leaves the buffer count at 0: row r is written with `firstVis = r + 1, numVis = 1` (the first
  attempt wrote one row, caught by check (a)).
- **MFImage changes its input.** It opens the uvtab read-write (`ObitUVUtilWhichSources`) and its
  first run on each file grew it by 8,640 bytes (S1 and the pilot alike, before this protocol was
  frozen). Each run therefore works on a copy (section 2), and the sha256 of the `D:` copy and of the
  run's copy after the run are logged (`input-sha.txt`).
- **MFImage input files.** MFImage takes defaults from no TDF: a key missing from the `.inp` is
  absent (a missing `nx` segfaults in `BeamOne`, NULL pointer, gdb backtrace in the outputs). The
  `.inp` is therefore every parameter of [`MFImage.TDF`](results/v5-obit-scripts/MFImage.TDF) at
  its TDF default (0, F or blank where none) with the settings of section 3 over them, written with
  LF line ends (Obit reads a CR into the value).
- **Conversion check (plumbing, before the freeze).** (a) Rows written equal the MS rows of the
  field without autocorrelations; unflagged XX and YY visibilities and their weight sums equal the
  MS's to 1e-6 (float32). (b) A dirty image (MFImage `Niter 0`) of S1 puts the 10 sources of
  section 4 within 0.3 pixel of their true positions (a sign or conjugation error mirrors them).
  (c) MFImage's coarse frequency planes are counted and their centre frequencies read, to set
  `maxFBW` (section 3). The results are in section 8.

## 2. Data and the three imagers

| | S1 | pilot-512 |
| --- | --- | --- |
| MS | `D:\rang\outputs\20261102-gemclean\bench\data\s1.ms` | `D:\rang\outputs\20261103-gemclean-heldout\real\cal.ms` |
| content | simulated: 64 dishes, 2 h, 8 × 25 MHz (1312.5-1487.5 MHz), 50 points 10 mJy-1 Jy, flat spectra, no primary beam ([gemclean-benchmark.md](gemclean-benchmark.md)) | ESO 137-006, 512 channels, 989.6-1096.6 MHz, 823,500 rows, XX YY, 28 % flagged ([g7-defaults.md](g7-defaults.md)) |
| image | 2048² × 1.5″ | 4096² × 3″ |
| threshold | 100 µJy | 3 mJy |

- **GeMClean** `gemclean-sb-ed836ec.exe` (G8's source build of main `ed836ec`, sha256
  `9dad1c78…3ff`; no GeMClean code changed on main since, `git log ed836ec..c2fe7cc -- core/src`
  touches the flagger only), native Windows, its defaults (coarse gridding, G7).
- **WSClean 3.7** `4f395b2` in `rang-wsclean-native:3.7` (Docker in WSL), its defaults
  (`minres`, G7's WM arm).
- **MFImage** in `rang-obit:dc26694` (Docker in WSL), reading the converted file.

GeMClean and WSClean read the MS (`D:` natively and through 9p respectively; WSClean's
`-temp-dir` is on the WSL ext4 disk). MFImage reads its uvtab many times and writes its own
selected copy of the data (`out2File`) and scratch images; on `D:` through drvfs that made it I/O
bound (pilot `Niter 0` at 8 threads, before the freeze: 14,143 s wall, 7,982 s CPU; S1 904 s wall,
190 s CPU). Each MFImage run therefore copies the uvtab to the WSL ext4 disk
(`~/Build/tmp/20261111-v5-obit/<run>`), runs there, and copies its outputs back; the copies are
outside the timed command, the timed command is MFImage alone. On S1 `Niter 0` this gave 15.6 s
wall instead of 904 s, with bit-identical images (all 10 planes).

## 3. Settings, matched where they can be

Common to GeMClean and WSClean (S1 / pilot): `-size N N -scale C -weight briggs 0.5 -niter 1000000
-gain 0.1 -nmiter 1000 -abs-threshold T -data-column DATA -field 0 -channels-out 8 -join-channels
-fit-spectral-pol 2 -j J`; WSClean also `-gridder wgridder -pol I -mgain 0.8`, at `-j 1`
`-parallel-reordering 1` and `OMP_NUM_THREADS=1`. The 8 output channels give spectral indices
(G7's runs were single-channel). GeMClean uses its own major-cycle rule.

MFImage (full input in [`v5_run.py`](results/v5-obit-scripts/v5_run.py), `inp`):

| setting | MFImage | matches |
| --- | --- | --- |
| field | `FOV` = N·C/2 (0.4267°, 1.7067°), Obit's own facets on one tangent plane (`do3D F`), flattened (`doFull T`): 7 fly's-eye facets for S1, 215 for the pilot | the circle inscribed in the square field; Obit corrects w by faceting, GeMClean and WSClean by w-stacking (**not matched**) |
| cell | `xCells = yCells = C` | yes |
| weighting | `Robust 0.5`, `WtBox 0` | Briggs 0.5 on Obit's own uv grid (**not identical**: its grid follows the facet size) |
| frequency | `maxFBW` set so that MFImage makes 8 coarse planes of equal channel count. A bin is `maxFBW` × (lowest frequency) wide, breaks at the nearest channel (`ObitImageMF.c` 904-951). S1: 0.0195, 1.02 channels, one per channel. Pilot: 0.013521, 64.03 channels, 8 × 64 (0.0128 gave 9 planes, the last of 28 channels; section 8). Also `norder 1`, `doFit T`, `MFTaper -1` (no frequency-dependent taper), `doComRes F` | 8 joined channels, as WSClean's and GeMClean's `-channels-out 8`, spectral fit. MFImage fits a spectral index; WSClean and GeMClean fit a 2-term polynomial |
| target beam | `targBeam 1 1 0`. Any value > 0 skips `BeamOne`, an extra image of the first IF (49 min of the pilot `Niter 0` run). The target beam is read only when `MFTaper` > 0 (`ObitUVGridMF.c` 412-418). | S1 `Niter 0` images are bit-identical with and without it |
| CLEAN | `Niter 1000000`, `Gain 0.1`, `minFlux T`, `ccfLim 0.2` (= 1 − mgain), `autoWindow F`, `SDIGain 0`, `CCFilter 0 0`, `minPatch` and `maxPixel` at their defaults (100, 200000) | niter, gain, threshold, no mask; major-cycle depth as WSClean's `-mgain 0.8` |
| model | `Cmethod DFT` (MFImage's only wideband method) | GeMClean and WSClean degrid (**not matched**) |
| off | `maxPSCLoop 0`, `maxASCLoop 0`, `PeelFlux 1e20`, `autoCen 1e20`, `Catalog None`, `PBCor F`, `BLFact 1.0`, `nTaper 0`, `doCalib −1`, `doBand −1`, `flagVer −1` | no self-calibration, peeling, recentring, outliers, primary-beam correction or averaging |
| restoring beam | `Beam 0 0 0` (Obit fits its own) | each imager fits its own |
| threads | `nThreads` 16 and 1 | `-j 16`, `-j 1` |

TDF defaults left in force that act with these settings:
- `Reuse 10`: components above 10 σ are kept between cycles;
- `noNeg T`: negative summed components are excluded;
- `minPatch 100` and `maxPixel 200000`;
- `WtUV 0.01`, which has no effect without `UVRange`.

These are MFImage's normal behaviour and are not matched by the other two imagers. The rest act
only on features that are off here: self-calibration, outliers, peeling, polarisation and GPU.
There are 127 keys in all, listed in each run's `mfimage.inp`.

Not part of this comparison: MFImage's recommended MeerKAT settings (frequency taper, autoWindow,
self-calibration), multiscale, masks, polarisation.

## 4. Measures (frozen with the sources before any MFImage output existed)

[`select_sources.py`](results/v5-obit-scripts/select_sources.py) wrote
[`results/v5-obit-sources.json`](results/v5-obit-sources.json) from S1's truth and from G7's
WSClean pilot run (`g7-20261109-01/runs/WM-j16-r1`) only:

- **S1:** the 10 brightest truth points with no other source within 60″ (0.35-0.99 Jy).
- **pilot-512:** local maxima above 20 σ (σ = 1.4826 MAD of the inner residual) in the inner field,
  compact (restored peak over aperture flux 0.8-1.25) and isolated (no candidate above 10 % of its
  peak within 6 BMAJ): 6 of 58 candidates pass (20-167 mJy), so the pilot has 6, not 10.
- **Noise regions:** S1, the inner field (central 2N/3) farther than 72 px (10 beams) from every
  truth source (1.20 M px); pilot, the inner field outside the ≥ 5 σ pixels of that WSClean image
  dilated by 5 BMAJ (7.14 M px). Masks on the WSClean grids, placed by world coordinates.

All positions are in world coordinates; each image's own WCS places them. Per imager, from its
restored images:

1. **Flux (aperture):** S = Σ over a circle of radius 2 BMAJ of the restored image / beam area
   (π BMAJ BMIN / 4 ln 2, the image's own header beam), in each of the 8 sub-band images.
2. **Spectral index:** least-squares fit of ln S against ln ν over the 8 sub-bands (S > 0 only,
   equal weights), giving α and S(ν₀) at ν₀ = 1400 MHz (S1) and 1043 MHz (pilot). Reported too:
   MFImage's own α plane and WSClean's and GeMClean's fitted terms at the source peak (not used for
   the tolerances).
3. **rms:** 1.4826 MAD and the standard deviation over the noise region, on the MFS image
   (GeMClean, WSClean `-MFS-image`, MFImage plane 1), and the median over the 8 sub-band images.
4. **Restoring beam:** BMAJ, BMIN, BPA of the MFS image header (MFImage: its CLEAN beam).
5. **Time and memory:** wall time from process start to exit; GeMClean user + kernel time and peak
   working set (`GetProcessTimes`, `GetProcessMemoryInfo`), WSClean and MFImage GNU `time -v` in the
   container (wall, user, system, maximum RSS); CPU/wall; phase times from the logs. The conversion
   to Obit's format is timed apart.

## 5. Timing method

As G7 (section 5 there): one host (16 threads, Windows 11, WSL 2), every run under
`tools/heavy_lock.py`, a load probe before and after; a run is spoiled if a process other than the
probe's and the VM host's is above half a core before it; the driver waits up to 10 minutes for a
clean probe. Order: S1 at `-j 16`, two repeats, imagers interleaved (G, W, O; reversed on repeat 2),
then S1 at `-j 1` once each; then the pilot likewise (`p16`, `p1`). **Contingency (written now):**
if MFImage's first pilot run at `-j 16` takes more than 4 h or hits the cap, its second `-j 16`
repeat and its `-j 1` run are not made and are reported as not measured. Any MFImage run is
stopped at 8 h (`timeout`, rc 124) and reported as not finished, with its log's last phase and
the `Niter 0` figures of section 8. The driver applies both rules
([`v5_run.py`](results/v5-obit-scripts/v5_run.py), `plan`). For scale, the pilot's MFImage
`Niter 0` at 8 threads (shared slots, staged) took 1,340 s; CLEAN with the DFT model on 0.6 G
visibilities is the unknown part. Different OS
layers (GeMClean native, the others in a Linux VM through 9p) are mixed in the times, as in G7; no
same-OS figure is made here.

## 6. Tolerances (frozen)

These classify agreement; they are not gates on any code. "Pair" is MFImage against WSClean,
MFImage against GeMClean, and GeMClean against WSClean (the last as the reference scale: G3 found
median |ΔS/S| 0.2-0.4 % and |Δα| 0.011-0.017 between them).

| measure | agree if | also reported |
| --- | --- | --- |
| flux S(ν₀), pair | median \|ΔS/S\| ≤ 1 % and largest ≤ 3 % | per source |
| flux, S1 against truth | median \|S/S_true − 1\| ≤ 1 % | largest |
| α, pair | S1: median \|Δα\| ≤ 0.03, largest ≤ 0.1; pilot: \|Δα\| ≤ 0.1 for sources ≥ 50 mJy (3 sources; fainter ones reported only: their sub-band SNR is about 7) | MFImage's α plane |
| α, S1 against truth (0) | median \|α\| ≤ 0.03 | largest |
| rms (MAD), pair | ratio within 0.9-1.1 | standard deviation, sub-band median |
| restoring beam, against WSClean | BMAJ and BMIN within 5 %, BPA within 5° | |
| time, memory | reported as ratios, no tolerance | phases |

An outcome is reported whichever way it falls; a disagreement is described, not explained away,
and causes are labelled as established or not.

## 7. Where things go

Outputs `D:\rang\outputs\v5-20261111-01` (`uv/` converted data and conversion logs, `select/`,
`runs/<arm>-<ds>-j<j>-r<rep>/` with command, log, `time.txt` or Windows counters, load probes,
`timing.json`, `runs.tsv`). Scripts in [`results/v5-obit-scripts/`](results/v5-obit-scripts/);
compact archive `results/v5-obit.json`; timings in [tool-timings.md](tool-timings.md). Status
`C:\Users\gijsm\Github\rang\outputs\status\v5-obit.md`.

## 8. Freeze record

Plumbing runs before the freeze. All are untimed, in shared lock slots, with outputs under `uv/`
and `runs/*-niter0*`.

**Conversion**, timed apart from imaging:

| | S1 | pilot |
| --- | --- | --- |
| wall | 3 min 24 s | 1 h 48 min |
| peak RSS | 142 MB | 288 MB |
| uvtab | 392 MB | 10.1 GB |

**Check (a): passes on both.**

| | S1 | pilot |
| --- | --- | --- |
| rows, MS = uvtab | 1,814,400 | 823,500 |
| unflagged XX and YY, equal on both sides | 14,515,200 each | 302,978,293 each |

The relative differences of the weight, real and imaginary sums are at most 3e-14 for both
(limit 1e-6).

**Check (b): the written criterion fails; the cause is the estimator.**
- *MFImage dirty image of S1* (flux-weighted 5 × 5 centroid): offsets from the truth have median
  0.244 px and largest 0.500 px, and 3 of 10 sources are over 0.3 px.
- *WSClean dirty image of the same MS* (`W-S1-j8-r1-niter0`): median 0.237 px, largest 0.488 px.
- *MFImage minus WSClean*, per source: centroid median 0.008 px, largest 0.012 px; peaks within
  0.43 %.

So the conversion places the sources as WSClean does from the MS: no mirror, no shift. The 0.3 px
limit was too tight for a 5 × 5 centroid on a 1.5″ grid. This deviation from the written check is
recorded, not repaired by changing the limit.

**Check (c): passes.**

| | S1 | pilot |
| --- | --- | --- |
| cube | 2048² × 10 planes | 4096² × 10 planes |
| `NSPEC` | 8 | 8 |
| `NTERM` | 2 | 2 |
| sub-bands | the 8 channel frequencies | 8 × 13.375 MHz, 996.33-1089.96 MHz (`maxFBW` 0.013521) |

The first pilot run with `maxFBW` 0.0128 gave `NSPEC` 9, the last plane at 1093.82 MHz.

**MFImage `Niter 0`, 8 threads, untimed**

| run | layout | wall | CPU | peak RSS | facets |
| --- | --- | --- | --- | --- | --- |
| S1 | `D:` drvfs, BeamOne on | 904 s | 190 s | | 7 |
| S1 | ext4 staged, BeamOne off | 15.6 s | 39 s | 1.13 GB | 7 |
| pilot | `D:` drvfs, BeamOne on | 14,143 s | 7,982 s | 4.95 GB | 215 |
| pilot | ext4 staged, BeamOne off | 1,340 s | 7,167 s | 4.46 GB | 215 |

The two S1 images are bit-identical.

Phases of the first pilot run, from its log:

| phase | duration |
| --- | --- |
| scratch copy | 14 min |
| BeamOne | 49 min |
| data copy and facet set-up to weighting | 1 h 31 min |
| imaging | 29 min |
| flatten | 2 min |
| pixel spectra, single-threaded | 44 min |

In the staged run the pixel-spectrum fit took 36 s.

**Input bytes.** The staged pilot copy's sha256 changed during the run, at the same size, while
the S1 copy did not change. The `D:` copies have not been opened by MFImage since staging began.

Frozen at commit `426c431` (protocol sections 1-6 and this record).

## 9. After the freeze

**Changes to how the timing runs are scheduled** (2026-11-12, at the coordinator's request, to
keep the host busy and E2/E3 first):

- *One hold per plan.* G-S1-j16-r1 and W-S1-j16-r1 ran with one exclusive ticket each. All later
  timed runs run inside one exclusive hold per plan (`V5_PLAN_HELD=1`), and the lock status is
  logged before each run in `plan-<name>.log`.
- *Plans regrouped.* The S1 `-j1` runs moved from `s1` to `p1`, which waits for E2's and E3's
  timed runs.
- *s1 deferred (2026-11-12).* The queued `s1` hold was withdrawn on the coordinator's word: it
  sat first in the lock queue behind a shared E2 job, blocking seven shared jobs. `s1`, `p16`
  and `p1` all wait for the coordinator's go after E2's and E3's timed passes.

Neither change touches the measures, the settings or the tolerances.

**MFImage CLEAN crash, fixed (Obit bug).** The first timed CLEAN run, `O-S1-j16-r1` on
`rang-obit:dc26694`, died with SIGSEGV (rc 139) after 14.8 s, right after "SkyModel with 30
components". Under gdb (`debug-gdb/gdb-clean.txt`, the same `.inp`, ext4 staged) the same point
aborts instead: `g_malloc0` is asked for 18446744071959779253 bytes from `ObitInfoListAlwaysPut
("Stokes")` in `MFMakeResiduals`.

The cause is in `src/ObitDConCleanVisMF.c`, lines 1088 and 1115:
`dim[1] = dim[2] = dim[3] = dim[5];` reads past the end of `gint32 dim[MAXINFOELEMDIM]`
(`MAXINFOELEMDIM` is 5, `ObitInfoElem.h:46`), so the element count is stack garbage. That
code runs only when residuals are made, which is why the `Niter 0` runs never reached it.

The fix is in [`build.sh`](../tools/oracles/obit/build.sh): the trailing dimensions are set to 1, as
the array's initialiser `{4,1,1,1,1}` intends, with a count check before and after. The patched
image is `rang-obit:dc26694-p1`: MFImage 11,917,144 bytes, 453 warnings. The crashed run is kept as
`runs/O-S1-j16-r1-crash-dc26694`; the timed run is repeated on the patched image.

Patch note for the Obit maintainers (W. D. Cotton), not posted. File `ObitSystem/Obit/src/ObitDConCleanVisMF.c`
at commit `dc2669429fdb5bfde2910f7f55e46e55df3ee204`, function `MFMakeResiduals`, lines 1088
and 1115, each `dim[0] = 4; dim[1] = dim[2] = dim[3] = dim[5];`, where `dim` is
`gint32 dim[MAXINFOELEMDIM]` and `MAXINFOELEMDIM` is 5, so `dim[5]` is read past the end;
patched to `dim[1] = dim[2] = dim[3] = dim[4] = 1;`. Issue text:

> MFImage (dc26694) segfaults or aborts at the first residual of any CLEAN. In `MFMakeResiduals`,
> `src/ObitDConCleanVisMF.c` lines 1088 and 1115, `dim[1] = dim[2] = dim[3] = dim[5]` reads past
> `dim[MAXINFOELEMDIM]` (= 5); `g_malloc0` then gets a garbage size (gdb: 18446744071959779253
> bytes) via `ObitInfoListAlwaysPut(..., "Stokes", ...)`. `dim[4]` (or 1) was presumably meant.
> Ubuntu 24.04, GCC 13, -O3 -march=native.

**Untimed S1 CLEAN, patched image** (`O-S1-j8-r1-clean`, 8 threads, shared slots; not a timing
run): rc 0, 1,222 s wall, 8,173 s CPU, 1.13 GB RSS, 236,158 iterations. Against the frozen
tolerances of section 6:

| measure | MFImage | reference | tolerance | verdict |
| --- | --- | --- | --- | --- |
| flux against truth, \|S/S_true − 1\| | median 0.0001, largest 0.0002 | | ≤ 1 % | agrees |
| flux, pair \|ΔS/S\| | median 0.0001, largest 0.0003 (both against WSClean and against GeMClean) | | median ≤ 1 %, largest ≤ 3 % | agrees |
| α, pair \|Δα\| | against WSClean median 0.0029, largest 0.0071; against GeMClean 0.0030, 0.0077 | | median ≤ 0.03, largest ≤ 0.1 | agrees |
| α against truth (0) | median \|α\| 0.0039, largest 0.0068; α plane largest 0.006 | | median ≤ 0.03 | agrees |
| restoring beam | 14.28″ × 12.77″, −43.5° | WSClean 13.88″ × 8.35″, −29.8° (150.2°) | BMAJ, BMIN within 5 %, BPA within 5° | **does not agree**: BMAJ +2.9 %, BMIN +52.9 %, BPA 13.7° |
| rms (MAD), MFS | 43.6 µJy | WSClean 24.9, GeMClean 24.8 µJy | ratio 0.9-1.1 | **does not agree**: ratio 1.75 (standard deviation 46.1 against 24.9 µJy) |

GeMClean against WSClean on the same S1 runs (`-j 16`), the reference scale:

| measure | result |
| --- | --- |
| \|ΔS/S\| | median 1.6e-5, largest 4.5e-5 |
| \|Δα\| | median 0.0002, largest 0.0008 |
| beam | 13.88″ × 8.35″ for both |
| rms | 24.8 µJy and 24.9 µJy |

**Beam and rms: settings checked against section 3** (2026-11-12, at the coordinator's request,
after the result above). The two measured fails are kept as measured. Section 3 matches what
was run (`Robust 0.5`, `WtBox 0`, `UVTaper 0`, `MFTaper −1`), and its "not identical: its grid
follows the facet size" names the one known difference. Without `nuGrid`/`nvGrid`, Obit sizes
its weighting grid from `nx`, the facet (`ObitUVWeight.c` 451-476). `MFImage.c` accepts both keys
(line 1578), although the TDF does not list them.

Untimed `Niter 0` S1 runs (8 threads, shared slots): `niter0beamdef` with the frozen settings,
`niter0beam` with the weighting grid as large as the image, as WSClean's. MFImage's beam image
(`saveBeam T`) was fitted with the PSFs of WSClean and GeMClean by one estimator,
[`psf_halfpower.py`](results/v5-obit-scripts/psf_halfpower.py): a least-squares Gaussian with
peak 1 over the connected pixels ≥ 35 % of the peak.

| PSF | header (imager's own fit) | one estimator for all |
| --- | --- | --- |
| WSClean (`W-S1-j16-r1`) | 13.88″ × 8.34″, −29.8° | 10.18″ × 8.03″, −11.8° |
| GeMClean (`G-S1-j16-r1`) | 13.88″ × 8.35″, −29.8° | 10.18″ × 8.03″, −11.8° |
| MFImage, frozen weighting grid (facet) | 14.28″ × 12.77″, −43.5° | 10.85″ × 8.45″, −13.8° (+6.6 %, +5.2 %) |
| MFImage, weighting grid = N (`nuGrid` 2048) | 13.75″ × 12.46″, −30.8° | 10.91″ × 8.49″, −13.9° (+7.2 %, +5.7 %) |

The PSFs differ by 5-7 % and 2°. The weighting grid moves MFImage's PSF by under 1 %.

The 53 % BMIN difference of the restoring beams comes from Obit's own beam fitter, which is fitted
to a different part of the main lobe. The PSF is not the cause (established on S1). No deviation
is made and `nuGrid` stays unset: the setting is as the protocol intended, and setting it would
not change the PSF materially.

The rms ratio of 1.75 is not a restoring-beam effect. The noise of a restored image is the
residual's, and the expected Briggs 0.5 noise on S1 is 23.2 µJy
([gemclean-benchmark.md](gemclean-benchmark.md)). Obit reports its weighting raising the natural
noise (19.8 µJy) by 1.12, about 22 µJy. MFImage's final facet residuals peak at 0.69-1.17 mJy.
WSClean's MFS residual peaks at 0.167 mJy, with a MAD of 24.7 µJy, against a threshold of 0.1 mJy.

MFImage's CLEAN therefore stopped with residual flux left: 236,158 iterations of the 1,000,000
allowed, and peaks 7-12 times the threshold. Its log (`prtLv 1`) does not say why. Not
established: which stopping rule ended it. Candidates are `minPatch`, `maxPixel`, the major-cycle
rule with `ccfLim 0.2`, and the TDF defaults of section 3 (`Reuse`, `noNeg`).

## 10. Resume state (2026-11-13, stopped on the owner's order)

- Done and committed at 5b1e3f3:
  - Obit build, patched as `rang-obit:dc26694-p1`;
  - checks (a) to (c);
  - the untimed S1 CLEAN run at -j8 (section 9) and its beam and rms analysis;
  - the timed runs G-S1-j16-r1 and W-S1-j16-r1.
  The outputs are in `D:\rang\outputs\v5-20261111-01\runs`.
- Pending, in this order and each as one exclusive hold, after E2's and E3's timed passes:
  1. `s1`: the O-S1-j16-r1 run and the r2 repeats of G, W and O;
  2. `p16`;
  3. `p1`: S1 and the pilot at -j1, with the 4 h drop rule.
  Command, from `research/results/v5-obit-scripts`:
  `V5_PLAN_HELD=1 python tools/heavy_lock.py run -- python v5_run.py plan NAME`.
- After the timed runs:
  - score each run with `v5_measure.py`;
  - add the ratios to section 9;
  - add rows to `research/tool-timings.md`;
  - write `research/results/v5-obit.json`;
  - remove `~/Build/tmp/20261111-v5-wsctmp` and `~/Build/tmp/20261111-v5-obit`.
- No heavy_lock ticket is queued.
