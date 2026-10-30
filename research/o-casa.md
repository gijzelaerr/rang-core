# O-CASA: a CASA/CARACal cross-calibration oracle on the LUNO 1934−638 slice

Protocol frozen 2026-10-30 on branch `o-casa` (from origin/main `b87ba3c`),
before the image was built or any CASA task was run. Task O-CASA of
[big-plan.md](big-plan.md), section "Plan additions" of the
[ecosystem survey](ecosystem-survey.md) (oracles: section 5.4).
Status: **implemented; measured (provisional under the open LUNO
licence).** CARACal's crosscal defaults do not calibrate a four-station
core set: the automatic reference antenna is empty and K stops. The
smallest deviation that solves needs three changes: `refant` set by hand,
`minblperant=3`, and no `uvrange` cut. With those, CASA's K·G·B
calibration reproduces in hash over two runs. Its applied gains agree with
the core's QuartiCal port to 0.4 % in amplitude and 0.33° in phase (median,
stored model). On held-out cells its MSE is 10 % higher on the parallel
hands and 58 % higher on the cross hands, because K·G·B has no
off-diagonal term. See "Measured result". Results are added below the
protocol, never edited into it; this status line is the only edit above
the amendment.

## Why

Three real-data campaigns of gain-TV-guided flagging on the public LUNO
calibrator stores returned null, and the novelty rule in AGENTS.md needs a
matched state-of-the-art baseline. The survey found that CARACal's
cross-calibration is CASA (`crosscal_worker.py` issues `casa_setjy`,
`casa_gaincal`, `casa_bandpass`, `casa_fluxscale`, `casa_applycal`), not
QuartiCal. Until now rang's comparator was QuartiCal at the campaign
settings and the core's port of it. This task measures what CARACal's own
CASA sequence does on the same four-station slice.

**This is a baseline measurement, not a hypothesis test.** No outcome
counts as better or worse for rang; the numbers are inputs for L4 (the
verdict), FS1 (flux standards) and DF1/DF2 (a reference image).

## Licence and provenance

- **The image is a tool.** Nothing from it is copied into rang, which stays
  GPL-3.0-or-later. Only numbers, hashes and small summaries enter the
  repository.
- **Image contents and licences:**
  - Base `ubuntu:24.04@sha256:fe81560990fae86dc4743202b2cb4d3df98d0bcf949173cecef15ce1127ef852`
    (Noble), with `ppa:kernsuite/kern-10` debs:
    - `wsclean=3.7-1kern1` (GPL-3.0);
    - `aoflagger=3.5.0-1kern1` (GPL-3.0);
    - `python3-casacore=3.7.1-1kern2` and its casacore 3.7.1 libraries
      (LGPL-2.0-or-later / LGPL-3);
  - from Ubuntu: `casacore-data=20250826-160001-5` (the measures tables:
    geodetic, ephemerides, Observatories; public-domain/IERS data, Debian
    copyright file), `python3-numpy=1:1.26.4+ds-6ubuntu1`,
    `python3-numcodecs=0.12.1+ds-1build2`, `python3-scipy=1.11.4-6build1`;
  - in a Python 3.12 venv at `/opt/casa`, from public PyPI:
    `casatools==6.7.6.14` (wheel sha256
    `9dac2c1be31ce393440786b48814db24309832a2fea4c84221e7c47068af1dea`)
    and `casatasks==6.7.6.14` (wheel sha256
    `f99ca8c781e286bebc4a7fe1e2b4dd8fe2d1ef184d8bc4737849c9338630ea3d`),
    `casaconfig==1.5.2` and their closure in
    `tools/oracles/casa/requirements.lock`. CASA's licence metadata is
    contradictory (the survey: the wheel METADATA says GPLv2; the source
    headers say LGPL-2.0-or-later); either way it is used as a separate
    program and not linked into or copied into rang.
- `casaconfig` is pointed at the Ubuntu measures data
  (`measurespath=/usr/share/casacore/data`, auto-updates off) through a
  `casasiteconfig.py` in the venv. No `casarundata` is fetched from NRAO:
  sources are public PyPI, the KERN PPA and Ubuntu only. If a task needs
  data that `casacore-data` lacks, the failure is recorded, and the
  `casalite` deb of KERN-10 is examined as the next source, labelled.
- The image records `dpkg-query` and `pip freeze` lists at
  `/opt/image-{debs,pip}.txt`; both are copied into each run directory.
- **Data.** The LUNO stores carry no licence text; results are provisional
  as for every LUNO campaign (observer permission in chat 2026-10-29,
  SARAO's written confirmation pending). No visibilities are committed.

## Conventions (as `history/tools/flagging/`)

Every container run: `--user $(id -u):$(id -g)`, `--network none`,
`--tmpfs /tmp -e HOME=/tmp`, `OMP_NUM_THREADS=4`, inputs mounted
read-only, one fresh writable run directory
`outputs/o-casa-20261030-NN` mounted at the same container path
(`/run`) in every run (caltable keywords embed the MS path). Every tool
run is timed (date, tool, input, wall, peak RSS) with `/usr/bin/time -v`.
`receipt.py` writes `receipt.json` per run: SHA256 of every input file,
of the code files, of every output, the image ID and digest, the
`dpkg`/`pip` lists and the settings.

## Inputs

1. **Hash check.** Every file listed in
   `outputs/luno-support-20261029-01/slice/receipt.txt` (122 lines) and
   `outputs/luno-solve-20261029-02/inputs/receipt.txt` (2,625 lines;
   archive `receipt_sha256` 98e51a06…cc8e in
   `results/meerkat-luno-solved.json`) must have the recorded size and
   SHA256. A mismatch stops the run.
2. **MS rebuild.** `examples/build_luno_ms.py` (sha256 c73e76e9…91f2, as
   recorded in `results/meerkat-luno-solved.json`), unedited, run with the
   image's system `python3` (python-casacore 3.7.1 from KERN, not the
   3.8.1 of the gone `rang-flagging:local` image; recorded as a deviation)
   from the archived slice and inputs into `/run/work.ms`.
3. **Equality gate.** The archived `outputs/luno-solve-20261029-02/work.ms`
   is copied (never opened in place) and compared column by column with the
   rebuild: every MAIN column (DATA, MODEL_DATA, FLAG, FLAG_ROW,
   WEIGHT_SPECTRUM, SIGMA_SPECTRUM, UVW, TIME, ANTENNA1/2, …) and every
   subtable column must have identical array bytes (SHA256 of the
   contiguous array). A difference stops the run; table-file bytes are not
   compared (they depend on the casacore version).
4. **Models.** The stored MODEL_DATA (1934−638, no logged origin; the
   model all core campaigns used) is copied to a column `MODEL_STORED`
   before `setjy` overwrites MODEL_DATA. Both are summarised: Stokes I per
   channel (XX+YY)/2 on unflagged cells, its value at 1.4 GHz by
   interpolation, and a log-log spectral index fit over the 2048 channels.

## The CARACal sequence, as `crosscal_worker.py` issues it

Source: caracal-pipeline/caracal master `8f7bb363876f5f0daecbf2167c36bb597c7e5160`
(2026-09-14; the commit of `outputs/caracal-strategy-inputs-8f7bb363`),
files `caracal/workers/crosscal_worker.py`, `caracal/schema/crosscal_schema.yml`,
`caracal/schema/obsconf_schema.yml`, `caracal/dispatch_crew/{utils,catalog_parser,config_parser}.py`,
`caracal/data/{southern_calibrators.txt,casa_calibrators.yml}`,
`caracal/workers/utils/manage_antennas.py`. CARACal's defaults are the
schema `example` values (`config_parser.py` lines 309 and 318). For a set
whose only calibrator is 1934−638 (fcal = bpcal = gcal), the worker takes
the `no_secondary` branch.

1. **`setjy`.** Not Stevens-Reynolds 2016. `set_model` asks CARACal's own
   database first: `southern_calibrators.txt` has
   `PKS1934-63 epoch=1994 a=-30.7667 b=26.4908 c=-7.0977 d=0.605334`
   (Reynolds 1994, log10 S in Jy against log10 ν in MHz). With the
   defaults `meerkat_skymodel: False` and `meerkat_crystalball_skymodel:
   False`, `find_in_native_calibrators(mode="mod")` returns the point
   model, so CARACal issues
   `setjy(vis, field=<1934>, standard='manual', fluxdensity=S, reffreq='1.400000GHz', spix=[a', b', c', d'], scalebychan=True, usescratch=True)`.
   `S` and `spix` come from `catalog_parser.convert_pb_to_casaspi`: the
   coefficients are moved to GHz (`k = log10 1000`), and
   `S·(ν/ν0)^(a'+b' log10(ν/ν0)+c' log10²+d' log10³)` is fitted by
   `scipy.optimize.curve_fit` to the polynomial on 10,000 points over
   0.8–1.8 GHz, ν0 = 1.4 GHz. `crosscal.py` reimplements that conversion
   (not copied) and records the five numbers; computed on the host before
   freezing: S = 14.907688923 Jy, spix = [−0.1947373, −1.3843252,
   0.6053344, 1.4e−6]. Only if CARACal's database did not match would the
   CASA fallback apply, and it takes the *first* listed standard for
   1934−638 (`standards: 1,3,4,5,6,8`), which is **Perley-Butler 2010**,
   not SR2016. Measured check: CARACal fits `spix` with log10, while the
   CASA convention for `spix` is to be read off the setjy MODEL_DATA. The
   setjy Stokes I per channel is compared with both the log10 and the
   natural-log reading of the same coefficients; a mismatch with the
   reading CARACal assumed (up to 6 % at 1.07 GHz on this band) is an
   upstream observation, not a failure.
2. **`refant`.** Obsconf default `refant: auto`, `maxdist: 1000`,
   `minbase: 150`: `manage_antennas.get_refant` keeps antennas within
   1000 m of the array centre whose baselines are all ≥ 150 m and returns
   up to three, sorted by flagged fraction. `crosscal.py` applies the same
   rule to the four stations (centre: the MeerKAT array reference position
   -30.71106°, 21.44389°, 1086.6 m; baselines among the MS's antennas;
   flagged fraction from FLAG) and records the result. An empty result is
   what CARACal then passes (`refant=''`, after logging an error), so it
   is used as is.
3. **`gaincal` K** (`delay_cal`): `gaintype='K'`, `solint='120s'`,
   `combine=''`, `field`, `refant`, `spw=''`, `scan=''`; no `uvrange`, no
   on-the-fly tables.
4. **`gaincal` G** (`gain_cal`): `gaintype='G'`, `calmode='ap'`,
   `solint='120s'`, `combine=''`, `uvrange='>50'`, `spw=''`, `scan=''`,
   `gaintable=[K]`, `interp=['linear']`, `gainfield=[<1934>]`.
5. **`bandpass`** (`bp_cal`): `bandtype='B'`, `solint='inf'`,
   `combine='scan'`, `solnorm=False`, `fillgaps=70`, `uvrange='>50'`,
   `scan=''`, `gaintable=[K, G]`, `interp=['linear','linear']`,
   `gainfield=[<1934>, <1934>]`. `b_smoothwindow: 1`, so no smoothing.
6. **`fluxscale`: not issued.** The `no_secondary` branch logs "Secondary
   calibrator is the same as the primary. Skipping fluxscale"; the flux
   scale is the one `setjy` set. It is not run as part of the oracle.
7. **`applycal`** (`apply_cal.applyto` default `bpcal, gcal, target`; with
   one field, once): `applymode='calflag'`, `gaintable=[K, G, B]`,
   `interp=['linear']*3`, `gainfield=['nearest']`, `calwt=[False]`,
   `parang=False`, `flagbackup=False`.
8. **`polcal`: not run.** `polcal_worker` needs a polarised calibrator
   (`xcal`) and parallactic-angle coverage; the slice is one 248 s scan of
   unpolarised 1934−638. Recorded as not run.

Parameters not listed take CASA 6.7.6 defaults, as they do under the
Stimela cabs (which pass only the parameters given). Two of them matter
here and are recorded before running:

- **`minblperant` (default 4).** With four stations each antenna has
  three baselines, so CASA is expected to reject every solution. Arms:
  - **A `caracal`**: exactly as above. Expected: K/G/B fully flagged or an
    error. Whatever happens is the frozen outcome of CARACal's defaults on
    a four-station set.
  - **B `caracal-mb3`**: identical, with `minblperant=3` in K, G and B.
    A labelled deviation, the only change, and the arm that yields
    numbers. All comparisons use B unless A yields valid solutions.
- **`minsnr` (default 3)** is left at the default in both arms.
- `uvrange='>50'` (metres): the six baseline lengths are recorded; a
  baseline shorter than 50 m would be excluded, as in CARACal.

## Arms and outputs

Each run directory holds, under `/run`:

| Arm | MS copy | Model | Flags while solving | Purpose |
| --- | --- | --- | --- | --- |
| A `caracal` | `a.ms` | setjy (CARACal manual) | original | the faithful oracle |
| B `caracal-mb3` | `b.ms` | setjy (CARACal manual) | original | the baseline; WSClean input |
| BH `caracal-mb3-holdout` | `bh.ms` | setjy (CARACal manual) | original ∪ seed-7 validation ∪ test | matched held-out MSE |
| SH `stored-mb3-holdout` | `sh.ms` | stored MODEL_DATA (no setjy) | original ∪ seed-7 validation ∪ test | matched to the core's model; gain comparison |

Holdout arms: the seed-7 split is computed on the host with
`rangtoy.core_campaign.build_state` (read-only use; the frozen rule:
eligible cells, 10 % validation, 10 % test, groups gain bin × baseline)
from the arrays of `examples/prototype_section6.ingest`, written as
`split.npz`. Gate: ANTENNA1, ANTENNA2 and TIME of the MS equal those
arrays row for row. The container flags validation ∪ test in FLAG (all
correlations), solves K, G, B, restores FLAG byte for byte (checked), then
runs `applycal`, so CORRECTED_DATA exists on every cell CASA's solutions
cover.

Per caltable (K, G, B of each arm): type, shape of CPARAM/FPARAM, flagged
fraction, per antenna and correlation the amplitude median/min/max and
phase median/std (degrees; K: delay in ns), SNR median; SHA256 per column
(CPARAM or FPARAM, FLAG, SNR, PARAMERR, TIME, ANTENNA1, SPECTRAL_WINDOW_ID)
and the SHA256 of the table directory tree (sorted POSIX relative paths
with each file's SHA256, excluding `table.lock`). CORRECTED_DATA: SHA256
of the array, flagged fraction after `applycal`, Stokes I mean per
channel summary and RMS. `setjy`: Stokes I at 1.4 GHz from MODEL_DATA and
the fitted log-log index, beside the stored model's.

Exports for the host comparison (in the run directory, not committed):
`b.npz`, `bh.npz`, `sh.npz` with DATA, CORRECTED_DATA, FLAG after
`applycal`, MODEL_DATA (and MODEL_STORED), WEIGHT_SPECTRUM, ANTENNA1/2,
TIME.

## Comparisons to rang (host, `tools/oracles/casa/compare.py`)

- **Applied products.** Per cell and diagonal correlation, CASA's applied
  baseline product is `P = DATA / CORRECTED_DATA` (exact for diagonal
  Jones, which K, G and B are), valid where CORRECTED is unflagged and
  DATA ≠ 0. This uses CASA's own interpolation; no table is re-evaluated.
- **Gauge-free gain comparison.** SH's `P` against the core's
  `g_p g_q*` (diagonal terms) from the archived
  `outputs/core-k-20261030-01/gains/original.npz` (the core's QuartiCal
  port at the K settings: 2 integrations × 32 channels, 50 iterations,
  stored model, held-out cells excluded), per cell where both are valid:
  median and 95th percentile of `|P_casa/P_core − 1|` and of the phase
  difference in degrees, per baseline and overall. CASA's chain is K·G·B
  with G at 120 s and B per channel; the core's is one complex 2×2 per
  bin, whose off-diagonal (median 0.006) CASA does not model. The same is
  reported for B against the core.
- **Held-out MSE.** For BH and SH, `r = DATA − P·M` per diagonal and
  off-diagonal correlation (off-diagonals with `P_XY = DATA_XY /
  CORRECTED_XY`), with `M` the arm's model; the metric is the frozen
  definition of `core-k-luno-campaign.md`: mean over cells of the
  correlation-mean `w|r|²` on the seed-7 validation and test cells. Cells
  whose CASA prediction is flagged are counted as unavailable and the
  coverage is reported; they are not dropped silently. The core's
  `original` arm values (MSE_val 0.2752889, MSE_test 0.2760093) are
  recomputed by the same numpy function from the archived core gains on
  all cells and on CASA's covered subset; the full-set value must match the
  archive to 1e-6 relative, or the comparison is not reported.

## Second flagging baseline (for L4) and reference image (for DF1/DF2)

- **`flagdata` tfcrop** on a copy of `work.ms`, CARACal's flag-worker
  call with the schema defaults: `mode='tfcrop'`, `datacolumn='data'`
  (`flag_rfi.col: DATA`), `usewindowstats='std'`, `combinescans=False`,
  `flagdimension='freqtime'`, `timecutoff=4.0`, `freqcutoff=3.0`,
  `correlation=''`, `flagbackup=False`. Reported: flag fraction before and
  after, new flags as cells and as a fraction of unflagged cells.
- **`flagdata` rflag**, labelled: CARACal ships no `rflag` settings, so
  CASA's defaults (`mode='rflag'`, `datacolumn='data'`, everything else
  default, `flagbackup=False`) on a separate copy. Flag fractions only.
- **WSClean 3.7** on B's CORRECTED_DATA (`b.ms` after the oracle):
  `wsclean -gridder wgridder -data-column CORRECTED_DATA -size 512 512
  -scale 8asec -weight briggs 0.5 -pol I -niter 0 -make-psf -name
  /run/wsclean/b -j 4`, the core campaign's image geometry and weighting
  (512 × 512 at 8″, Briggs 0.5). Archived: SHA256 of dirty and PSF FITS,
  peak in the central 9 × 9, RMS outside the central 64 × 64, PSF largest
  value outside the central 9 × 9, and the point-source residual RMS
  (`dirty − peak × PSF` over the image), as the core campaign defines
  them. The FITS stay in the run directory.

## Acceptance

1. Every CASA task call of arms B, BH, SH and the two `flagdata` runs
   returns without exception and every WSClean and builder run exits 0.
   Arm A may fail or flag everything; that is its frozen outcome and is
   recorded with the CASA log lines.
2. Every caltable and MS opens with python-casacore (the KERN
   `python3-casacore`, system `python3`, a separate process from CASA)
   and its columns are read.
3. Receipts complete: `receipt.json` has input, code and output hashes,
   image ID and digest, package lists, settings and the timing log.
4. **Reproducible.** Run `-02` repeats `-01` from scratch. The per-column
   content hashes of every caltable and the CORRECTED_DATA, FLAG and
   MODEL_DATA hashes of every arm, the flagdata flag hashes, and the
   WSClean pixel arrays must be identical. Raw tree hashes are reported
   beside them, not gated (they may embed time stamps).
5. `bash tools/check-all.sh` passes on the branch.

A failure is recorded here with its numbers. A labelled environment smoke
`outputs/o-casa-20261030-00-smoke` may precede `-01`; anything it changes
in the scripts is listed as post-hoc with the reason.

## Expected outcome, stated before running

Arm A will most likely produce no usable solutions because of
`minblperant=4`; that is itself a finding for anyone running CARACal on a
sub-array. Arm B should solve: 1934−638 is about 15 Jy and the slice is
70 % flagged but has about 117,000 eligible cells. With the stored model
(SH), CASA's applied products should agree with the core's gains to a few
percent in amplitude and a few degrees in phase where both are valid,
differing mainly through the solution intervals (120 s × whole band for
G, per channel for B, against 2 integrations × 32 channels) and the
missing off-diagonal term. The held-out MSE of SH should be close to the
core's 0.276, slightly higher or lower depending on whether CASA's finer
bandpass or the core's finer time grid fits better; neither direction is
a claim. The setjy flux at 1.4 GHz should be 14.91 Jy against a stored
model near 14.9 Jy.

## Files

`tools/oracles/casa/`: `Dockerfile`, `requirements.lock`, `build.sh`,
`run.sh`, `crosscal.py` (CASA venv), `inspect_tables.py` (system python3,
python-casacore), `receipt.py`, `compare.py` (host, rangtoy);
`research/o-casa.md`; `research/results/o-casa-crosscal.json`;
`tests/test_o_casa_optional.py` (skips without docker or the image).
No shared file is edited.

## Amendment after the labelled smoke (post-hoc, before run `-01`)

Written after the image build and six smoke attempts
(`outputs/o-casa-20261030-00-smoke`, `-smoke-b` … `-smoke-f`), committed
before run `-01`. The frozen text above is unchanged; these changes are
post-hoc and labelled.

1. **Image (environment).** The casatools 6.7.6.14 `manylinux_2_34` wheel,
   which pip selects on Noble, does not import: it bundles `libssl` 3.2 and
   `libldap` built against a `libcrypto` ≥ 3.2 (symbol versions
   `OPENSSL_3.0.1`/`OPENSSL_3.2.0`, `EVP_md2`) that Ubuntu 24.04's OpenSSL
   3.0.13 lacks; preloading the system `libssl` fails on `EVP_md2`. The
   same release's `manylinux_2_28` wheel (sha256
   `f6db5ec590fb988799a614a0143391d4987d2c0650235b56fbedbdac33295e18`,
   public PyPI URL in `requirements.lock`) imports and runs. casatools
   still reports 6.7.6-14. casaconfig logs SEVERE notices that
   `measurespath` is not casarundata and that the Ubuntu `TAI_UTC` table
   (2025-08) "seems out-of-date"; every task used here runs.
2. **Checker bugs (no data touched).** python-casacore 3.7.1 has no
   `nolock` lock option; the first column hash of string-array columns
   hashed object pointers, so FEED `POLARIZATION_TYPE` and OBSERVATION
   `LOG`/`SCHEDULE` looked different although their values are equal.
   Non-numeric columns are now hashed canonically from `getvarcol`. With
   that, the rebuilt MS equals the archived `work.ms` in all 13 tables and
   122 columns.
3. **Field selection (script bug).** FIELD is copied whole (3 rows:
   J1331+3030, J1939−6342, J1833−2103); MAIN uses FIELD_ID 1. The first
   script took row 0 and `setjy` selected no rows. CASA calls now use the
   name of MAIN's FIELD_ID (J1939−6342, as CARACal's `fcal` would), and
   WSClean gets `-field 1` (its default is field 0, which gridded nothing).
4. **CARACal's defaults on four core stations (measured in the smoke).**
   - `refant: auto` returns no antenna: the four stations are 171–226 m
     from the array centre but their baselines are 29–74 m, all below
     `minbase` 150 m. CARACal then passes `refant=''`, and `gaincal` K
     raises "Please specify a good reference antenna (refant) explicitly".
     Arms A and B therefore stop at K, before `minblperant` matters.
   - Mean projected baseline lengths: m000–m001 36.7 m, m000–m002 29.3 m,
     m000–m003 58.5 m, m001–m002 62.1 m, m001–m003 74.2 m, m002–m003
     40.8 m. `uvrange='>50'` leaves three baselines, at most two per
     antenna.
5. **Arms, as run from `-01`.** A and B unchanged (frozen; both expected to
   stop at K). Added:
   - **D `caracal-refant`** (diagnostic): CARACal's defaults with
     `refant='m000'` set by hand, as a user would after the auto rule
     fails; CASA's `minblperant` 4 and `uvrange='>50'` kept.
   - **C `caracal-mb3-uv0-refant`**: `refant='m000'` (antenna 0, the core
     campaign's reference antenna), `minblperant=3`, and no `uvrange`
     cut for G and B. Everything else as CARACal issues it. This replaces
     B as the baseline arm, and WSClean images C.
   - The holdout arms keep their design with C's settings: **CH**
     (setjy model, replacing BH) and **SH** (stored model).
6. **Host comparison.** `compare.py` passes the MS channel frequencies to
   `build_state` (the core's TV needs increasing coordinates; the gains do
   not depend on them), `solve_arm` takes per-cell additions, and `run.sh`
   puts `~/.cargo/bin` on `PATH` for the on-demand TV kernel. The core's
   gains then hash to the core-k archive (`4ed2aa89…`) and its losses equal
   the archive; the numpy MSE reproduces them (validation to 2e-15
   relative). Also reported, added before `-01`: the test MSE split into
   parallel (XX, YY) and cross (XY, YX) hands, for CASA, the core, and the
   core with its off-diagonal gain terms zeroed.

The smoke numbers are not results; `-01` and `-02` are.

## Measured result (2026-10-30, provisional)

Runs `outputs/o-casa-20261030-01` and `-02` used `run.sh` at commit
`7162468`, image `rang-o-casa:6.7.6.14`. The image ID
`sha256:24822b4038c5e9c969073168dc904eb5b531fd184acadc53435638e99af169e8`
is its content digest; the image is local and has no registry digest. It
is 1,413,632,658 bytes and built in 56.1 s. Each run took 47.4 s and 44.9 s
wall in all, with a peak RSS of 521 MB. Archive:
[results/o-casa-crosscal.json](results/o-casa-crosscal.json) (135 KB).
It holds numbers and hashes only; no visibilities.

### Inputs

- **Receipts.** All 122 + 2,625 receipt lines match in size and SHA256.
- **MS rebuild.** The builder rebuilt the MS in 4.1 s. It equals the
  archived `work.ms` in all 13 tables and 122 columns.
- **Split.** The seed-7 split is 94,047 / 11,742 / 11,767 cells, equal to
  core K, and the row gate passes. The 23,509 held-out cells carry no
  original flag.

### The model (`setjy`)

**CARACal's manual model.** CARACal issues
`fluxdensity=14.907688923 Jy` at `1.400000GHz` with
`spix=[-0.19473727, -1.38432520, 0.60533435, 1.43e-06]` (fit standard
errors ≤ 1.6e-9). `setjy` writes:

| | 1070.0 MHz | 1284.0 MHz | 1400 MHz | 1497.8 MHz |
| --- | ---: | ---: | ---: | ---: |
| Stokes I (Jy) | 15.0077 | 15.0918 | 14.9077 | 14.6732 |

The log-log slope over the band is −0.0731.

**Which `spix` convention CASA uses.** CASA's model equals the *log10*
reading of `spix` to 2.6e-6 relative; the natural-log reading would be
6.8 % off. So CASA's `spix` convention is log10, as CARACal assumes.

**The stored MODEL_DATA**, the model the core campaigns used, is
different. It is 14.9028 Jy at 1.4 GHz, 14.855 at 1070 MHz and 14.708 at
1497.8 MHz, with a slope of −0.0405. That is 1.0 % below CASA's model at
the bottom of the band and 0.2 % above it at the top. It is also not a
pure point at the phase centre: its Stokes I varies by up to 0.48 Jy
between rows and has an imaginary part up to 0.50 Jy. That fits a model
with structure or an offset; its origin is still unlogged.

**FS1 side outputs.** `standard='Stevens-Reynolds 2016'` and
`'Perley-Butler 2010'` write bit-identical MODEL_DATA. `setjy` returns
`fluxd` 15.0077077 Jy for both. Per channel, both equal the Reynolds 1994
polynomial (CARACal's `southern_calibrators.txt` coefficients) to 2.7e-6
relative, and CARACal's manual fit to 4.8e-6. The per-channel arrays are
`fs-{sr2016,pb2010}-stokes-i.npy` with `chan-freq.npy` in the run
directory.

**Not run.**
- `fluxscale`: CARACal does not issue it here (`no_secondary` branch).
- `polcal`: there is no polarised calibrator and no parallactic-angle
  coverage.

### The arms

| Arm | Settings | Outcome |
| --- | --- | --- |
| A (frozen) | CARACal defaults | `setjy` ok. `gaincal` K raises "Please specify a good reference antenna (refant) explicitly". The auto rule returns no antenna: the four stations are 171–226 m from the centre, but their baselines are 29–74 m, all under `minbase` 150 m. No tables, no `applycal`. |
| B (frozen) | + `minblperant=3` | Identical to A: it stops at K. |
| D (post-hoc) | CARACal defaults + `refant='m000'` | K solves: 3/3 intervals per antenna pass even at `minblperant` 4. G finds 0/3 intervals above `minblperant` with `uvrange='>50'`. `gaincal` returns normally but writes no table. `bandpass` then logs SEVERE "Table d.G0 does not exist" and also returns normally. |
| E (post-hoc, `-04-arm-e`) | D without the `uvrange` cut | G again 0/3 above `minblperant` 4; no G table. |
| F (post-hoc, `-05-arm-f`) | D with `minblperant=3` | G 0/3 (with `uvrange='>50'`, at most two baselines per antenna); no G table. |
| **C** | `refant='m000'`, `minblperant=3`, no `uvrange` | All tasks succeed (table below). |
| CH | C, solved with the seed-7 held-out cells flagged | All succeed; FLAG restored byte for byte before `applycal`. |
| SH | CH on the stored MODEL_DATA (no `setjy`) | All succeed. |

So the frozen expectation was wrong on the mechanism. Arm A fails at
`refant` before `minblperant` matters. `minblperant` 4 stops G but not K.
`uvrange='>50'` stops G on its own. C's three changes are each necessary
(D, E, F).

**Arm C's tables** (refant m000):

- **K.** 3 intervals × 4 antennas × 2 polarisations, none flagged. Delays
  are within ±0.011 ns of m000; the processed data are already
  delay-calibrated. The K SNR column is 0.
- **G.** Shape (12, 1, 2), none flagged, SNR median 132. Median amplitude
  per antenna for X / Y:

  | | m000 | m001 | m002 | m003 |
  | --- | ---: | ---: | ---: | ---: |
  | X | 0.776 | 0.789 | 0.795 | 0.794 |
  | Y | 0.770 | 0.790 | 0.791 | 0.793 |

  Phases relative to m000 are +3.8°/+3.9° (m001), −1.7°/−1.6° (m002) and
  −3.2°/−3.2° (m003). The spread over the three 120 s intervals is
  ≤ 0.45°. The core reports a median diagonal amplitude of 0.788.
- **B.** (4, 2048, 2), 75.8 % flagged, SNR median 105. Amplitudes are
  0.965–1.017 with medians 0.999–1.001; phase std ≤ 0.51°.
- **CORRECTED_DATA.** `calflag` adds no flags; 29.9 % of cells are
  unflagged. Stokes I mean is 14.957 Jy (1.0003 × model), Stokes I real
  std 0.213 Jy, imaginary std 0.259 Jy. The mean cross-hand |V| is
  0.380 Jy.
- **SH's G.** Medians 0.784–0.790. Phases +3.4°/+3.5°, −2.4°/−2.3° and
  −4.1°/−4.1°.

### Comparison with the core

**Gauge-free gain products.** Applied products `P = DATA/CORRECTED`
against the core's `g_p g_q*`, over all 117,556 eligible cells. The core's
gains are the core-k `original` arm: hash `4ed2aa89…`, equal to the
archive.

| CASA arm | Hand | Amplitude rel. diff., median / p95 | Phase diff., median / p95 |
| --- | --- | ---: | ---: |
| SH (stored model, held-out) | XX | 0.40 % / 1.19 % | 0.33° / 1.05° |
| SH (stored model, held-out) | YY | 0.39 % / 1.25 % | 0.32° / 1.05° |
| C (setjy model) | XX | 1.00 % / 2.30 % | 0.72° / 1.79° |
| C (setjy model) | YY | 1.04 % / 2.42 % | 0.70° / 1.76° |

Per baseline (SH) the medians are 0.34–0.46 % and 0.25–0.44°. The C
numbers include the model's spectral difference, which the bandpass
absorbs.

**Held-out MSE.** The frozen metric on the seed-7 cells. Every CASA
prediction is available (0 unavailable cells).

| | MSE_val | MSE_test | test, parallel hands | test, cross hands |
| --- | ---: | ---: | ---: | ---: |
| core `original` (archive; recomputed by numpy to 2e-15) | 0.275289 | 0.276009 | 0.229422 | 0.322596 |
| core with off-diagonal gains zeroed | – | 0.369746 | 0.229442 | 0.510050 |
| **SH** CASA, stored model, held out | 0.378808 | **0.381487** (×1.382) | 0.252925 (×1.102) | 0.510050 |
| CH CASA, setjy model, held out | 0.393731 | 0.397161 (×1.439) | 0.284272 | 0.510050 |
| C CASA, setjy model, solved on all cells (in-sample) | 0.389008 | 0.392471 | 0.274892 | 0.510050 |

**Reading.** CARACal's K·G·B chain has no off-diagonal term. On the cross
hands it therefore predicts the same as the core with its off-diagonal
gains zeroed: 0.51005, identical to six digits. The core's complex 2×2
solve has an off-diagonal median of 0.006, which absorbs a leakage-like
cross-hand signal and lowers the cross-hand MSE by 37 %. CARACal would
solve leakage only in its separate `polcal` worker, which needs a
polarised calibrator.

On the parallel hands, with the same model, cells and weights, CASA's
chain is 10.2 % worse than the core. Its G and K are per 120 s across the
whole band; the core solves per 2 integrations × 32 channels.

The `setjy` model costs CASA a further 12 % on the parallel hands. It
differs from the stored model in spectrum by 1 % and has no row structure,
which suggests the stored model is closer to the data.

This is a measurement for L4, not a claim. It is a four-station slice with
processed weights and flags, and the model has no logged origin.

### Second flagging baseline (for L4)

`flagdata` on a copy of `work.ms` (70.10 % flagged before), flags only:

| Mode | New flags | New cells | Fraction of unflagged | Flagged after |
| --- | ---: | ---: | ---: | ---: |
| tfcrop, CARACal flag-worker defaults on DATA | 7,024 | 1,756 | 1.49 % | 70.55 % |
| rflag, CASA defaults (labelled; CARACal ships none) | 680 | 170 | 0.14 % | 70.15 % |

Both modes flag uniformly over the four correlations and keep the original
flags. For reference, core K's Tricolour first-pass port added 128
training cells (0.14 %).

### WSClean 3.7 reference image (for DF1/DF2)

Arm C's CORRECTED_DATA, imaged with `-gridder wgridder -field 1 -size 512
512 -scale 8asec -weight briggs 0.5 -pol I -niter 0 -make-psf -j 4`.
117,556 visibilities gridded, 1.1 s.

| Metric | Value |
| --- | ---: |
| Dirty peak | 14.9723 Jy/beam |
| Peak pixel (y, x) | (254, 259) |
| PSF at the centre pixel / PSF maximum | 1.0 / 1.0016 at the dirty-peak pixel (1.0014 outside the central 9 × 9) |
| Off-source RMS | 3.846 Jy/beam |
| Point-source residual RMS | 0.02857 Jy/beam |

- **Where the peak is.** With 29–74 m baselines the main lobe is nearly
  flat over the inner pixels, so WSClean's PSF maximum is not at its
  centre pixel (CRPIX 257).
- **Files.** The FITS stay in `outputs/o-casa-20261030-01/wsclean/`. Pixel
  hashes: dirty `2288e159…`, PSF `839977ec…`.
- **Not bit-reproducible.** With `-j 4` the two runs' pixels differ by up
  to 3.1e-5 Jy (2.0e-6 relative).
- **Post-hoc, labelled.** `outputs/o-casa-20261030-03-wsclean-j1` ran the
  same command with `-j 1` twice on a copy of `-01`'s `c.ms`. The two runs
  are bit-identical: dirty FITS sha256 `84ad3396…`, PSF `6710c1ff…`, peak
  14.97230, residual RMS 0.028570. They differ from `-j 4` by 2.3e-5
  relative. **DF1/DF2 should use the `-j 1` FITS (`r1-*.fits`) as the
  reference.**
- **Not comparable with core K.** Core K's own imager on the core's gains
  gave a peak of 14.9246 and a residual RMS of 0.0712. That is a different
  imager on different gains; matching them is DF1's job.

### Acceptance

| Criterion | Result |
| --- | --- |
| 1 task exits | **Fails as frozen for B.** B stops at K, as A does. It **passes for the amended baseline C/CH/SH**: every CASA call returns without exception, and both `flagdata` runs, the builder and WSClean exit 0. The no-table returns of D/E/F are recorded. |
| 2 readable by python-casacore | Pass: every caltable and MS is read by KERN python-casacore 3.7.1 in `summarize`. |
| 3 receipts | Pass: `receipt.json` has the input check, code and output hashes, image, timings and settings. `image-{debs,pip}.txt` are copied into each run. |
| 4 reproducible | **CASA: pass.** All 119 gated hashes match except the two WSClean pixel arrays: every caltable column, CORRECTED_DATA, FLAG and MODEL_DATA of every arm, flagdata, flux standards, MS columns and the split. **WSClean `-j 4`: fail** (2e-6 relative); `-j 1` is deterministic (post-hoc). Raw tree hashes differ for c.K/G/B and ch.K/G; they are not gated. |
| 5 check-all | Pass: `bash tools/check-all.sh` once before the final commit, overall PASS (pytest 645 passed, 4 skipped). |

### Timings (every tool run of this task)

| When | Tool run | Wall | Peak RSS | Note |
| --- | --- | ---: | ---: | --- |
| 2026-10-30 | `uv venv` + `uv pip install -e '.[pointing,beam,test,imaging]' ruff maturin` (worktree venv) | 28.7 s | 638 MB | |
| 2026-10-30 | KERN-10 probes in `ubuntu:24.04` (package versions, PyPI closure, casalite deb listing), scratch | ~1–3 min each | – | three probes |
| 2026-10-30 | `build.sh` first image (casatools `manylinux_2_34`) | 170.7 s | 53 MB (client) | built; casatools does not import (OpenSSL); image deleted |
| 2026-10-30 | `build.sh` final image (`manylinux_2_28`), apt layer cached | 56.1 s | – | 1.41 GB, ID `24822b40…` |
| 2026-10-30 | labelled smoke `-00-smoke` … `-00-smoke-f` (six attempts) | 5–90 s each | ≤ 521 MB | fixes listed in the amendment; directories deleted |
| 2026-10-30 | **run `-01`** (`run.sh` under `/usr/bin/time -v`) | 47.4 s | 521 MB | |
| 2026-10-30 | **run `-02`** | 44.9 s | 521 MB | identical CASA hashes |
| 2026-10-30 | post-hoc WSClean `-j 1` ×2 (`-03-wsclean-j1`) | 0.91 s, 0.92 s | 77 MB | bit-identical |
| 2026-10-30 | post-hoc arms E, F (`-04-arm-e`, `-05-arm-f`), solve + apply | 1.8 + 1.1 s each | 320 MB | |
| 2026-10-30 | `archive.py` | < 1 s | – | 135 KB archive |
| 2026-10-30 | `bash tools/check-all.sh`, once before the final commit (`outputs/o-casa-20261030-01.check-all.log`) | 404.7 s (pytest 645 passed, 4 skipped in 120.3 s) | 1.53 GB | overall PASS; the wall includes the first maturin and cargo builds of this worktree |

Steps inside run `-01` (wall in s / peak RSS in MB, in-container `/usr/bin/time`):

| Step | Wall / RSS | Step | Wall / RSS |
| --- | ---: | --- | ---: |
| inputs (host hash check, 2,747 files) | 3.4 / 21 | solve-c (setjy, K, G, B) | 2.2 / 317 |
| split (host, `build_state`) | 1.2 / 93 | apply-c | 1.4 / 299 |
| build (`build_luno_ms.py`) | 4.1 / 466 | solve-ch / restore / apply | 2.3 / 0.1 / 1.5 |
| equal (13 tables) | 0.2 / 97 | solve-sh / restore / apply | 2.1 / 0.1 / 1.6 |
| prepare (10 copies) | 0.5 / 87 | flagdata tfcrop / rflag | 2.2 / 1.9 (293) |
| solve-a / apply-a | 1.3 / 1.1 | setjy SR2016 / PB2010 | 1.8 / 1.5 (305) |
| solve-b / apply-b | 1.3 / 1.1 | WSClean (`-j 4`) | 1.1 / 76 |
| solve-d / apply-d | 1.7 / 1.1 | summarize / compare (host) | 0.5 / 2.3 (509) |

The CASA tasks themselves take 0.2–0.34 s each (`casa/*.json`); about 1 s
per step is Python start-up and CASA import inside the container.

## For the coordinator

- **Shared files: none edited.** Added: `tools/oracles/casa/`
  (`Dockerfile`, `requirements.lock`, `build.sh`, `run.sh`, `crosscal.py`,
  `inspect_tables.py`, `compare.py`, `receipt.py`, `archive.py`), this
  report, `research/results/o-casa-crosscal.json` and
  `tests/test_o_casa_optional.py`.
- **`STATE.md`, new top entry.** "O-CASA, 2026-10-30 (implemented;
  measured; provisional). A CASA oracle image (`rang-o-casa:6.7.6.14`:
  Ubuntu 24.04 + KERN-10 WSClean 3.7, AOFlagger 3.5, python-casacore
  3.7.1; casatools/casatasks 6.7.6.14 from PyPI, the manylinux_2_28 wheel
  because the 2_34 wheel does not import on Noble) runs CARACal's crosscal
  sequence by hand on the LUNO 1934−638 four-station slice.
  - CARACal's defaults stop at K: the automatic reference antenna is
    empty, because all baselines are under 150 m. Solving needs
    `refant`, `minblperant=3` and no `uvrange` cut (arms D/E/F show each
    is necessary).
  - With those, CASA's K·G·B reproduces in hash over two runs (119 gated
    hashes; only WSClean `-j 4` pixels differ, at 2e-6).
  - Against the core's QuartiCal port: applied gains agree to 0.4 % and
    0.33° (median, stored model). Held-out test MSE is 0.3815 against
    0.2760: ×1.10 on the parallel hands, and ×1.58 on the cross hands,
    because K·G·B has no off-diagonal term.
  - Flagging baselines: tfcrop with CARACal's defaults adds 1.49 % of
    unflagged cells; rflag 0.14 %.
  - `setjy` SR2016 and PB2010 equal the Reynolds 1994 polynomial (and
    CARACal's manual model) to 3e-6.

  Archive `results/o-casa-crosscal.json` (`o-casa.md`)."
- **`tool-timings.md`.** The rows of the timings table above.
- **`big-plan.md`.** O-CASA done (measured). FS1 and L4 are unblocked;
  DF0 can share the base (`ubuntu:24.04` digest and the KERN pins in
  `tools/oracles/casa/Dockerfile`).
- **FS1 can use** the per-channel SR2016/PB2010 Stokes I arrays
  (`outputs/o-casa-20261030-01/fs-*-stokes-i.npy`, `chan-freq.npy`). Its
  acceptance: the core's SR2016 and PB2010 for 1934−638 should match
  them to the float32 storage of MODEL_DATA. Two cautions:
  - CASA's two standards are bit-identical here and equal Reynolds 1994
    to 2.7e-6, so a port must reproduce that residual, not a tighter one.
  - `setjy` `spix` is log10.
- **L4 can use** these matched baseline numbers on the same cells:
  - CASA/CARACal crosscal (arm SH) held-out MSE_test 0.381487 against the
    core's 0.276009, 0.252925 against 0.229422 on the parallel hands;
  - tfcrop +1.49 %, rflag +0.14 %, Tricolour first pass +0.14 %.

  All arms are in the archive. The CARACal baseline as CARACal ships it
  does not run on four core stations; L4 should say so and cite arm C as
  the minimal deviation.
- **Upstream observations** (observed, not raised):
  - caracal-pipeline:
    1. `refant: auto` uses `minbase` as "all baselines ≥ 150 m". On a core
       sub-array, and for any antenna with a close neighbour, that returns
       no antenna. The worker then logs an error and passes `refant=''`,
       which `gaincal` K rejects.
    2. The default `uvrange: '>50'` plus CASA's `minblperant` 4 leaves G
       with no solutions on short-baseline sets. `gaincal` and `bandpass`
       return normally without writing tables, so the failure only
       surfaces at `applycal`.
    3. The CASA-fallback standard is "the first listed" (`standards:
       1,3,…` → Perley-Butler 2010 for 1934−638). `casa_calibrators.yml`
       is still labelled "CASA 4.7.1", although SR2016 exists.
    4. `get_last_gain` iterates a `set` of single-letter terms, so the
       `gaintable` order passed to `applycal` depends on string hashing.
       This is harmless for diagonal Jones terms.
  - Non-RATT, CASA:
    1. The casatools 6.7.6.14 `manylinux_2_34` wheel bundles `libssl` 3.2
       and `libldap` but relies on a system `libcrypto` ≥ 3.2 with MD2.
       It does not import on Ubuntu 24.04; the `manylinux_2_28` wheel
       does.
    2. `gaincal` K passes `minblperant` 4 with three baselines per antenna
       where G does not.
    3. Tasks that write no table return without an exception.
    4. With `casaconfig`'s auto-updates off, an Ubuntu `casacore-data`
       works, but CASA logs SEVERE notices on every start.
  - WSClean: wgridder with `-j 4` is not bit-reproducible (2e-6 relative);
    with `-j 1` it is.
- **Evidence to keep.**
  - Image `rang-o-casa:6.7.6.14` (ID `sha256:24822b4038c5…`).
  - `outputs/o-casa-20261030-01` and `-02` (654 MB each: MS copies and
    exports).
  - `-03-wsclean-j1` (67 MB, the reference FITS).
  - `-04-arm-e` and `-05-arm-f` (37 MB each).
  - `-00-build` and `-00-build2` (build logs).
  - `-02` may be reduced to `summary.json`, `receipt.json` and the logs
    once the archive is accepted.
- **Deleted scratch.**
  - The six smoke directories (2.5 GB); their `.log` files are kept.
  - The failed first image (`31cf5410…`).
  - The probe scripts in the session scratchpad.
- **Open.**
  - The LUNO licence.
  - Whether CARACal's `polcal` (Df on 1934−638) would close the
    cross-hand gap. That needs a polarised calibrator scan, which this
    slice lacks.
  - An L4 decision on whether the matched baseline is arm SH or a
    CARACal run with leakage.
