# O-CASA: a CASA/CARACal cross-calibration oracle on the LUNO 1934−638 slice

Protocol frozen 2026-10-30 on branch `o-casa` (from origin/main `b87ba3c`),
before the image was built or any CASA task was run. Task O-CASA of
[big-plan.md](big-plan.md), section "Plan additions" of the
[ecosystem survey](ecosystem-survey.md) (oracles: section 5.4).
Status: **proposed** (this commit). Results are added below the protocol,
never edited into it.

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
