# G6: GeMClean writes MODEL_DATA, and a predict mode

Task G6 of [finish-plan.md](finish-plan.md): GeMClean writes `MODEL_DATA` from its clean components after
imaging, as WSClean does unless it is run with `-no-update-model-required`, and gains WSClean's
`-predict` mode, which writes `MODEL_DATA` from given model images. `rang-core image` writes it through
W1's `WriteBack` ([w1-writeback.md](w1-writeback.md)), for self-calibration (C5). Branch `fp-g6-predict`
from main `d97b3f5`.

Status, 2026-11-07: **implemented and measured; every criterion met on every case run.** The protocol
was committed (`4398adc`) before the first comparison, and the freeze (`1f4aa76`, binary `b9a7dd9d`) was
recorded before any held-out case ran. gemclean `-predict` agrees with WSClean 3.7 `-predict` of the same
model images to a relative L2 of 0.7-4.2e-7 (bound 1e-5). Both agree with the exact Fourier sum to
2-4e-7. They change the same rows and channels, with XX = YY and zero cross hands. The after-clean column
equals gemclean's own `-predict` bit for bit, and the images are unchanged. `rang-core image` writes the
binary's bits through WriteBack. No novelty claim. Results in section 6; open owner decisions in section 5.

## 1. What WSClean 3.7 does

Read in the 3.6 source (`~/Github/rang/outputs/wsclean-3.6-1-source-20261029`, `msproviders/msprovider.cpp`,
`external/schaapcommon/.../msselection.h`), then **measured on 3.7** in a pre-freeze probe of WSClean alone
(no rang output compared): `/mnt/d/rang/outputs/g6-20261106-00-probe` (scripts in its `.code/`). The probe
copied A1's small MS (12,480 rows, 64 channels, 4 fields), flagged 50 whole rows, 10 rows in 4 channels and
set FLAG_ROW on 20 rows of field 3, cleaned field 3 (`-niter 300`, 512², 2″, Briggs 0, `-pol I`), then ran
`-predict` from the clean's `w-model.fits` into `-model-column MODEL_P`.

- **Rows.** The rows of the selected field and data description that are cross-correlations
  (`MSSelection::IsSelected`; autocorrelations are excluded by default). Flags play no part: the flagged
  rows, the flagged channels and the FLAG_ROW rows all received model values in the probe.
- **Correlations.** Under `-pol I` on linear feeds: `XX = YY = I`, `XY = YX = 0` (probe: equal bit for
  bit, cross hands exactly 0).
- **A new column.** Added as a variable-shape `StandardStMan` column (`MODEL_DATA_dm`) and set to zero in
  every row (`FillModelColumn`) before the predict; the rows of the other fields stayed 0 in the probe. An
  existing column whose row 0 is defined with DATA's shape is kept; otherwise it is reset to zero.
- **After a clean.** The clean's `MODEL_DATA` equalled `-predict` of its own `w-model.fits` bit for bit
  (probe). So the after-clean column is a prediction of the written model image.
- **Channels.** With `-channels-out n` each output channel's model image (`<name>-000k-model.fits`) is
  predicted at the frequencies of that channel's input channels. `-model-column` names the column.

## 2. Design (proposed in this commit)

One predictor in Rust, used by all three paths.

- `core/src/gemclean/predict.rs`:
  - reads the model images (`<name>-model.fits`, or `<name>-000k-model.fits` per output channel), from
    gemclean or WSClean (four axes, BITPIX −32 or −64), taking size, scale and centre from the header,
    and checks the centre against the field's PHASE_DIR (1e-9 rad);
  - maps each channel of the MS to its output channel as the imaging does (G3's `-channel-range`, then
    `-average-channels`, then the `-channels-out` groups; channels outside the range get no model);
  - predicts with the gridder's `dirty2vis` (the options of gemclean's measurement: `flip_v`, `flip_w`,
    `-wgridder-accuracy`, `-no-wgridding`, f64, or f32 with `-single`), with no weights and no mask, at
    the MS's own channel frequencies, over every selected row, in fixed blocks of selected rows (at most
    2^27 cells each), so that every path gives the same bits.
- **Selection.** As WSClean: field, data description 0, cross-correlations; flags ignored. (W6 adds scans.)
- **Cells.** `XX = YY = I`, `XY = YX = 0` (RR, LL likewise; a Stokes I column gets I). Channels outside
  `-channel-range` keep their values. Rows outside the selection keep theirs.
- **A new column** is added as W1's `ensure_column` adds it (TiledShapeStMan `TiledModel`, fixed shape,
  DATA's comment), but **initialised to zero, as WSClean does**, not to clearcal's unity (decision below).
- **The binary** (`gemclean`): after imaging it writes the model column unless `-no-update-model-required`
  is given (`-update-model-required` is the default, as in WSClean), predicting from the model FITS just
  written, after the clean's buffers are freed. `-predict` skips imaging and writes from existing model
  images. `-model-column NAME` (default MODEL_DATA). The binary writes through the core writer directly
  (`TableWriter`, the writer `WriteBack` drives), in row chunks with a flush per chunk, with no flag backup
  and no journal: it never writes FLAG.
- **`rang-core image`** runs gemclean with `-no-update-model-required` (read-only), then, with
  `image.update_model: true` (the default), predicts through the extension (`rang._core`) and writes the
  column through `WriteBack` (journal, lock, flag backup as W1).

## 3. Cases (frozen)

Model images are reused; no case is imaged for G6 except the after-clean cases.

| ID | MS (a fresh copy each time) | Model images | Role |
| --- | --- | --- | --- |
| A | A1's small MS, flags edited as in the probe; MODEL_DATA and MODEL_WSCLEAN pre-filled with the sentinel 7 + 7j in every cell | the probe's WSClean `w-model.fits` (512², 2″), field 3 | development |
| S1 | `20261102-gemclean/bench/data/s1.ms` | G2 `runs/c34/img/s1-def-model.fits` (gemclean); G2 `runs/wsclean/img/s1-nominres-model.fits` (WSClean) | development |
| D1 | G3 `data/D1.ms` (16 channels) | G3 `runs/dev1/D1-C1/g-000k-model.fits`, `-channels-out 8`; and their channels 0-2 as `-channel-range 2 14 -channels-out 3` | development |
| S1c | S1 | after a clean, G2's settings, default form | development |
| D1c | D1 | after a clean, G3's C1 (`-channels-out 8 -join-channels -fit-spectral-pol 4`) | development |
| S2, S3 | G2's bench `s2.ms`, `s3.ms` | G2 `c34` `s2-def-model.fits`, `s3-def-model.fits` | **held out** |
| H1, H2 | `20261103-gemclean-heldout/sim/data/h1.ms`, `h2.ms` | G2 `c34` `h1-def-model.fits`, `h2-def-model.fits` | **held out** |
| H1s | G3 `data/H1s.ms` | G3 `runs/freeze/H1s-C1/g-000k-model.fits`, `-channels-out 8` | **held out** |
| P | the pilot `20261103-gemclean-heldout/real/cal.ms` (512 channels) | after a clean at G2's settings, default form; WSClean `-predict` of the clean's model | **held out** |

The held-out cases run only after the freeze: a commit of `fp-g6-predict` and the SHA-256 of the
`gemclean` binary built from it (profile `gemclean`), both recorded here first. No change to the predictor
after the freeze without a post-hoc label, and then the held-out cases run again.

Settings: the imaging settings of the model's source run (G2's `-size 2048 2048 -scale 1.5asec`,
4096² and 3″ on the pilot; G3's for D1, H1s; 512² 2″ field 3 on A), `-wgridder-accuracy 1e-6` in both
imagers, WSClean 3.7 (`rang-wsclean-native:3.7`) with `-gridder wgridder -no-min-grid-resolution -pol I
-predict -model-column MODEL_WSCLEAN`, gemclean in its default form (f64). On every case gemclean writes
MODEL_DATA and WSClean writes MODEL_WSCLEAN into the same copy, so both are read in one pass.

## 4. Criteria (frozen)

`V_G` is gemclean's column, `V_W` WSClean's, over every cell of the selected rows (all channels of the
range); norms over all those cells, complex.

1. **Rows and cells.** The rows gemclean changes (A: from the sentinel; elsewhere: nonzero in a new column)
   are exactly the rows WSClean changes, and the channels likewise (D1 with `-channel-range`). In every
   changed row `XX = YY` bit for bit and `XY = YX = 0`. Every row and channel outside the selection is
   unchanged (A: still the sentinel; elsewhere: 0 in both).
2. **Predict parity**, every case: `‖V_G − V_W‖ / ‖V_W‖ ≤ 1e-5` and `max |V_G − V_W| ≤ 1e-4 · max |V_W|`.
3. **Exact sky (A, S1).** The direct Fourier sum of the model's nonzero pixels (`rang.core.predict_components`,
   points at the pixel offsets `l = (x − x₀)·CDELT1`, `m = (y − y₀)·CDELT2` of the SIN grid) on 400 selected
   rows drawn with seed 20261180, all channels: `‖V − V_exact‖ / ‖V_exact‖ ≤ 1e-5` for gemclean and for
   WSClean. This catches a flip, a transpose or a pixel-centre error in reading the FITS, which criterion 2
   could share only if WSClean made the same error.
4. **After a clean (S1c, D1c, P).** gemclean's column after the clean equals its own `-predict` of the
   model FITS it wrote, **bit for bit** (S1c, D1c; P is gated by 2 against WSClean's `-predict` of the
   same files). The FITS files equal, by SHA-256, those of the stored runs at the same settings, since
   G6 changes no imaging code: G2's `c34` `s1-def` (S1c) and `p512-def` (P) and G3's `dev1/D1-C1` (D1c,
   every channel and MFS file). If one differs, the same run with `-no-update-model-required` decides
   whether the write or something else changed it.
5. **The two paths agree.** On A, `rang-core image` with `image.update_model: true` writes a MODEL_DATA
   bit-identical to the binary's after-clean column at the same settings, into a copy with no MODEL_DATA.
6. **Read-back.** On A and S1: python-casacore 3.8.1 (`rang-ms-reader:local`) reads gemclean's column with
   the same SHA-256 as rang's own reader; the column description is TiledShapeStMan `TiledModel`, complex,
   shape [ncorr, nchan], DATA's comment; every column gemclean did not write has the SHA-256 it had before.
7. **Memory (P).** Peak RSS of the after-clean run (GNU `time -v`) ≤ 24 × 10⁹ bytes, with G2's swap rule
   (`-memory-report`; a run with swap at any phase is repeated). WSClean's `-predict` peak is reported.

Reported, not gated: gemclean's after-clean column against WSClean's after-clean column on S1 (different
models: the gap between the imagers), wall times (shared host; no timing claim).

A failure is reported as measured and not reworded.

## Freeze (recorded before any held-out case ran)

Frozen 2026-11-06 at commit `1f4aa76` of `fp-g6-predict`. `gemclean` built from it (profile `gemclean`, rustc
1.93, `nice`, without the heavy lock) has sha256
`b9a7dd9d875fcbc03410a79d8cb3cc4e2e7de9e6955cbf93cdfaabdc3a4417d7` (copy
`/mnt/d/rang/outputs/g6-20261106-02-held/bin/gemclean-freeze`). At the freeze only cases A and the
criterion-5 case had run (development, binary `gemclean-dev1`, release profile, one line of `read_model`
before a clippy fix that changes no value). S1, S1w, D1, D1r, S1c and D1c were still queued behind the
heavy lock with `gemclean-dev1`; they stay development runs.

## 5. Owner decisions (provisional, recorded here)

1. **Default on.** gemclean writes the model column by default, as WSClean. Every script that images a
   shared reference MS must now pass `-no-update-model-required`, or the MS is written. The scripts in
   this repository that run gemclean on shared data are changed to pass it.
2. **Zero, not unity,** for a column gemclean adds (WSClean's choice). When `rang-core calibrate` has added
   MODEL_DATA first (clearcal's unity and calibrator models), the image stage writes only the target's rows
   and keeps the rest.
3. **No reset.** An existing model column with an undefined row 0 or another shape is refused, where
   WSClean resets it to zero.
4. **`image.write_model` stays false by default** in `rang-core` (W2's key, unchanged default), so a
   plain `rang-core image` still leaves the MS unwritten. Setting it to true matches WSClean. Self-cal
   (C5) sets it. Open: whether the default should follow WSClean.
5. **A column name other than MODEL_DATA.** WriteBack copies DATA's column keywords (`UNIT`) onto it.
   The binary does not, so the two paths differ in that one keyword. They are equal for MODEL_DATA.

## 6. Results (measured)

Runs: development `/mnt/d/rang/outputs/g6-20261106-01-dev` (binary `gemclean-dev1`, release profile, the
freeze's source but for one line of `read_model` before a clippy fix that changes no value). Held out:
`/mnt/d/rang/outputs/g6-20261106-02-held` (the frozen binary `b9a7dd9d`, scripts as frozen in its
`tools/g6`). Pre-freeze WSClean probe: `/mnt/d/rang/outputs/g6-20261106-00-probe`. Each run directory has
`.code/` (commit, diff, binary hash), per-case `*-compare.json` (python-casacore), `*-dft.json`,
`*-rang-hash.json`, `*-summary.json`, GNU `time -v` files, logs and `*-load.txt`. The MS copies were
deleted after scoring.

**Harness fix (labelled; no criterion changed).** WSClean `-predict` with `-channels-out` writes
temporary files beside the model images (`g-model-0000-tmp.fits`). The stored G3 model directories are
mounted read-only, so WSClean failed on D1's first attempt. `case_predict.sh` now copies the model images
into the run directory, and both imagers read the copies. D1 and every later case ran after this fix. The
held-out copy of the scripts got the same three lines before any held-out case reached WSClean. A second
harness slip, D1r's model directory named as the case's own, was rerun from scratch.

| Case | Model | Rows (selected = gemclean = WSClean) | rel L2 vs WSClean | max \|Δ\| / max \|V_W\| | Exact sky, G / W | Read-back, others unchanged | gemclean peak GB |
| --- | --- | ---: | ---: | ---: | --- | --- | ---: |
| A (dev) | WSClean, 512² | 6,720 of 12,480 | 3.5e-7 | 4.9e-7 | 2.7e-7 / 2.6e-7 | yes, yes | – |
| S1 (dev) | gemclean `c34` | 1,814,400 | 3.9e-7 | 5.0e-7 | 3.2e-7 / 2.1e-7 | yes, yes | 2.20 |
| S1w (dev) | WSClean `nominres` | 1,814,400 | 3.9e-7 | 4.9e-7 | yes (≤ 1e-5) | yes, yes | 2.20 |
| D1 (dev) | 8 channels | 907,200 | 6.9e-8 | 1.6e-7 | – | yes, yes | 1.47 |
| D1r (dev) | `-channel-range 2 14 -channels-out 3` | 907,200; 12 of 16 channels in both | 7.0e-8 | 1.7e-7 | – | yes, yes | 1.34 |
| S1c (dev) | after a clean | 1,814,400 | 3.9e-7 | 5.0e-7 | – | yes, yes | 2.99 |
| D1c (dev) | after a joined clean, 8 channels | 907,200 | 6.9e-8 | 1.6e-7 | – | yes, yes | 7.03 |
| S2 (held) | gemclean `c34` | 1,814,400 | 3.9e-7 | 6.0e-7 | yes | yes, yes | 2.20 |
| S3 (held) | gemclean `c34` | 1,814,400 | 3.8e-7 | 7.1e-7 | yes | yes, yes | 2.20 |
| H1 (held) | gemclean `c34` | 1,814,400 | 4.2e-7 | 6.8e-7 | yes | yes, yes | 2.21 |
| H2 (held) | gemclean `c34` | 1,814,400 | 4.1e-7 | 6.6e-7 | yes | yes, yes | 2.21 |
| H1s (held) | 8 channels (G3 `freeze/H1s-C1`) | 907,200 | 1.4e-7 | 3.5e-7 | – | yes, yes | 1.47 |
| P (held) | the pilot at 512 channels, after a clean | 823,500 | 2.5e-7 | 6.8e-7 | – | yes, yes | **19.74** |

Bounds: rel L2 ≤ 1e-5, max ≤ 1e-4, exact sky ≤ 1e-5. "Yes" in the exact-sky column means both imagers are
within the bound (values in each `*-dft.json`); the sign convention of `predict_components` matched
WSClean's without conjugation on every case.

- **Criterion 1 (rows and cells): met on every case.** gemclean changed exactly the rows WSClean changed,
  and the same channels (D1r: the 12 channels of the range, the other 4 left at 0 by both). On A the
  other fields' rows kept the 7 + 7j sentinel, and the flagged rows, flagged channels and FLAG_ROW rows
  were predicted. XX = YY bit for bit and XY = YX = 0 in every changed row.
- **Criterion 2 (parity): met on every case**, at 1-4e-7, near float32 rounding of the stored values.
- **Criterion 3 (exact sky): met on A, S1, S1w and the held-out S2, S3, H1, H2.** S1w reads WSClean's own
  four-axis FITS, so the header, orientation and pixel centre are read as WSClean writes them.
- **Criterion 4 (after a clean): met.** On S1c (1 model image) and D1c (8 model images, joined, spectral
  fit) the after-clean column is bit-identical to gemclean `-predict` of the FITS the clean wrote. All
  FITS files are byte-identical to the stored runs: S1c's 5 to G2 `c34` `s1-def`, D1c's 45 (8 channels and
  MFS, 5 kinds) to G3 `dev1/D1-C1`. On the pilot (P, held out) the 5 FITS files are byte-identical to G2's `c34` `p512-def`, and the model column (4 blocks of 262,144 rows, 512 channels) is within criterion 2 of WSClean's `-predict` of the same images.
- **Criterion 5 (the two paths): met on A.** `rang-core image` with `write_model: true` and the binary
  with rang-core's own argv wrote MODEL_DATA with equal SHA-256. Their FITS were also identical
  (`a2/`).
- **Criterion 6 (read-back): met.** python-casacore 3.8.1 and rang's reader give the same SHA-256 of
  gemclean's column on every case. The column is TiledShapeStMan `TiledModel`, complex, shape
  `[ncorr, nchan]`, fixed (option 4), with DATA's comment (`data` on S1 and D1). Its tile is
  `[4, nchan, rows]`, about 1 MiB. Every column gemclean did not write has its earlier SHA-256.
- **Criterion 7 (memory): met.** The pilot's after-clean run peaked at 19.74 × 10⁹ bytes RSS (GNU `time -v`; `-memory-report` showed no swap at any phase). The peak is in the major cycles, as in G2. The model write held at most 8.44 GB of heap, after the clean's buffers were freed. WSClean's `-predict` of the same images peaked at 4.81 GB.**

Reported, not gated: gemclean's after-clean column against WSClean's after-clean column was not run
(WSClean did not clean S1 here). The probe showed on A that WSClean's after-clean column is its
`-predict` of its own model image, bit for bit. So the gap between the two after-clean columns is the
gap between the two imagers' model images, already reported by G1 to G3. Wall times are in the `time`
files and [tool-timings.md](tool-timings.md); the host was shared and no timing claim is made.

## 7. What was not checked

- Autocorrelation rows. They are excluded by the code, as in WSClean (`MSSelection`), but no case had any.
- Several data descriptions, fields other than the one imaged in a multi-field MS beyond case A, and
  circular feeds (RR, LL; the code path exists).
- `-single`, `-no-wgridding` and `-average-channels` with the model write (the code maps averaged
  channels back to the MS's channels; no oracle exists for averaging).
- Writing into an existing column that a shorter or variable-shape layout holds (refused by design);
  WSClean's reset of such a column is not copied.
- An interrupted binary write. The binary flushes per chunk but keeps no journal, unlike `WriteBack`.
- Shifted model images (refused) and model images of another size than `-size` (refused when `-size` is
  given; taken from the header otherwise).

## For the coordinator

- **research/README.md**, index line:
  `- [G6, MODEL_DATA and a predict mode](g6-predict.md): gemclean writes MODEL_DATA after imaging and has WSClean's -predict; equal to WSClean 3.7's -predict to 1-4e-7 on S1-S3, H1, H2, joined channels and the pilot; rang-core image.write_model writes it through WriteBack.`
- **research/STATE.md**, log, newest first:
  `G6, 2026-11-07 (implemented and measured; [g6-predict.md](g6-predict.md)). gemclean writes the model column after imaging, as WSClean does (-update-model-required by default, -no-update-model-required, -model-column), and has -predict. One Rust predictor (gemclean::predict) serves the binary and rang-core image (image.write_model: true, through W1's WriteBack). Under a rule written first, with held-out cases after a freeze: rows, channels and cells as WSClean 3.7 writes them (selected field, cross-correlations, flags ignored, XX = YY = I); relative L2 against WSClean's -predict of the same images 0.7-4.2e-7, both within 4e-7 of the exact Fourier sum; the after-clean column equals gemclean's own -predict bit for bit, with images byte-identical to G2's and G3's runs; python-casacore reads it bit for bit. Pilot at 512 channels: after-clean column within 2.5e-7 of WSClean's -predict, images byte-identical to G2's, 19.74 GB peak RSS (24 GB budget). No novelty claim.`
- **research/finish-plan.md**, row G6: `**Done 2026-11-07** ([g6-predict.md](g6-predict.md)).` C5 can use
  `image.write_model: true` or `rang.core_model.write_model_data`.
- **How `rang-core image` exposes it (proposed and implemented):** `image.write_model: true` (W2's key)
  writes MODEL_DATA for each imaged field after gemclean, through WriteBack, honouring `data.scans` (W6).
  gemclean always runs with `-no-update-model-required` under rang-core. A separate `rang-core predict`
  command is not added; C5 calls `rang.core_model.write_model_data` between its rounds.
- **Merge points** with parallel branches:
  - `core_pipeline.py`: `gemclean_arguments`, `write_model` and `_extra_flag` (new), and `stage_image`
    (the model write, and the `scans` and `unit` arguments added by W6).
  - `core_config.py`: the `write_model` refusal is removed, along with the selfcal "G6" refusal and the
    TASKS entry. E0 edits this file.
  - `core/py/src/lib.rs`: a mod line and three registrations at the end of the module init.
  - `docs/cli.md`: regenerated (selfcal help, write_model text).
- **Scripts changed to pass `-no-update-model-required`:** `examples/gemclean_bench_gemclean.sh`,
  `gemclean_compare.py`, `stale_floor_runs.py`, `gram_solver_jobs.sh` and `gridder_gram_jobs.sh`. The
  archived scripts under `research/results/` are unchanged; rerunning them with a G6 binary writes into
  their MSs.
- **Owner decisions:** section 5 (default on in the binary; zero initialisation; no reset;
  `write_model` default false in rang-core; the keyword difference).
