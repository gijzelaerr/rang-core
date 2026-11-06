# G6: GeMClean writes MODEL_DATA, and a predict mode

Task G6 of [finish-plan.md](finish-plan.md): GeMClean writes `MODEL_DATA` from its clean components after
imaging, as WSClean does unless it is run with `-no-update-model-required`, and gains WSClean's
`-predict` mode, which writes `MODEL_DATA` from given model images. `rang-core image` writes it through
W1's `WriteBack` ([w1-writeback.md](w1-writeback.md)), for self-calibration (C5). Branch `fp-g6-predict`
from main `d97b3f5`.

Status: **protocol frozen (this commit), nothing compared yet.**

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
