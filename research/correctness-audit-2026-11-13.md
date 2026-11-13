# Correctness audit before v0.2.0 (2026-11-13)

Branch `claude/correctness-audit-35f2b0`, from main 2a02470, rebased onto 30d9412. The audit maps each user-facing stage to
its tests, oracle gates, written tolerances and GPU twins (AGENTS.md: every GPU path has a CPU path
with the same result within a written tolerance). It also looks for untested public functions, missing
bad-input handling and cross-platform problems, and closes the cheap gaps with tests. The audit is a
read of the code and the notes. The only thing run is the new tests. No oracle was rerun, and no shipped
default changed its numbers.

## 1. Stage map

"Oracle in pytest" means a test compares against an oracle archive. The archives are not in CI, so in CI
these tests skip, and the full local check (`python -m rang.check`) is the gate.

| Stage | Tests | Oracle | Oracle in pytest | Tolerance written | GPU / CPU twin |
|---|---|---|---|---|---|
| Flagging, SumThreshold rows (`core_flag`, `sumthreshold.rs`) | `test_core_flag` (10), `test_p3_flags`, `test_w3_chunking`; 11 Rust | AOFlagger 3.5; CARACal strategies inspected | yes, `test_aflag.py:128-172` (skips without `outputs/core-d-oracle-*`) | `a-flag-aoflagger.md:352`, 1e-5 relative | none |
| Flag extension (`flag_extend`) | `test_e0_refant_extend.py:75-130` | CASA `flagdata` loops, written out in the test | yes (in-test reference) | `e0-refant-extend.md:168`, bit-identical | none |
| F2/F3 learnt flaggers | `test_f2_cnnflag`, `test_f3_flag` | JAX reference nets | yes | `f2-flagger.md:111`, `f3-flagger.md:103` | JAX ↔ Rust logits, 1e-3 / 1e-4 quantile (written only in the tests) |
| Gain G (`cal_gain`, kernel `cal/diag.rs`; `solve.rs` is the general Jones solver) | `test_cal_gain` (8); 5 Rust in `cal/diag.rs` (15 in `solve.rs`); `tools/gain_hash_gate.py` | QuartiCal 0.2.7, CASA `gaincal` | no. Solver runs are offline (`c2a-gain.md:171,188`); the hash gate compares against archived QuartiCal flags | `c2a-gain.md:69` | none |
| Bandpass B | `test_cal_bandpass` (6); 3 Rust | QuartiCal `diag_complex`, CASA `bandpass` | no (offline, `c2c-bandpass.md:372`) | `c2c-bandpass.md:116` | none |
| Delay K | `test_cal_delay` (9); 13 Rust | QuartiCal `delay`, CASA K | no (`c2b-delay.md:178`) | `c2b-delay.md:82` | none |
| Fluxscale | `test_cal_fluxscale` (5); 4 Rust | CASA `fluxscale` | no (`c2d-fluxscale.md:108`) | `c2d-fluxscale.md:10-23` | none |
| Flux standards (`fluxstd`) | `test_fluxstd` (17); 8 Rust | CASA `setjy` | yes, archived JSON receipts | in `results/fs1-*.json`, `fs2-*.json` | none |
| Apply (`cal_apply`, `applycal`) | `test_cal_apply` (9), `test_c4b_applycal` (6), `test_o_casa_optional` | CASA `applycal` | yes, `results/o-casa-crosscal.json` | `c4a-apply.md:63`; c4b "reported, not gated" (`c4b`:233) | none |
| Self-cal | `test_c5_selfcal`, `test_c5b_selfcal_masks` | QuartiCal | no (`c5-selfcal.md:99`) | `c5-selfcal.md:175` | none |
| Polarisation (`cal_pol`) | `test_cal_pol` (10), `test_c6w_polwire` | CASA | no (`c6w-polwire.md:129`) | `c6w-polwire.md:102` | none |
| Imaging weights | `test_core_weights` (6); 8 Rust | WSClean 3.6-1 archive | yes (skips without archive) | `core_imaging.py:49`, 1e-9 weight sums | none |
| W-stack gridder | `test_core_grid` (4), `test_p2_gridder`; 6 Rust | WSClean 3.6-1 | yes (skips) | `core_imaging.py:44-51`: dirty 8.8e-6 of peak, PSF 2.8e-6 | **wgpu**: f64 1e-12, f32 1e-4 of peak (`test_x2_gpu.py:79`, `gpu/tests.rs:206`); the note freezes ≤1e-10 with exact counters (`x2-wgpu.md:228`) |
| Exact gridder (wgrid) | `test_core_wgridder` (DFT 1e-8, ducc0 1e-9), `test_df2b_wgrid` | ducc0, DFT | yes (in-test DFT) | `g4-masks.md:171`, 1e-5 of peak | none (**was a silent CPU fallback**, fixed, §3) |
| FFT | `grid.rs` naive DFT | — | — | — | **wgpu** FFT vs rustfft: f64 1e-12, f32 1e-5 (`gpu/tests.rs:127-135`, `x2-wgpu.md:383`) |
| Clean minor/major, GeMClean | `clean*.rs`, `gemclean.rs` (14), `multiscale.rs` (6), `test_core_clean` (3), `test_g8_gemclean` | DF5 A1-A4 against WSClean (`df5o-deconv-oracles.md:329`) | yes, `test_df5o.py` (skips) | `df5o-deconv-oracles.md` | none. **No CASA `tclean` gate exists**; tclean appears only in survey notes |
| Restore and beam fit | `gemclean.rs` beam-fit test | WSClean | no | `g4-masks.md:173` BMAJ/BMIN 1e-3, "not met on any cleaned run" (:379) | none |
| Predict | `gemclean/predict.rs` (3), `predict.rs` (3), `test_g6_model` (2) | WSClean `-predict` | via `tools/oracles/g6/compare.py` | `g6-predict.md:103`: L2 1e-5, max 1e-4 | none |
| FITS read/write | one round-trip Rust test; `test_core_grid.py:85` | astropy reads in tests | — | — | — |
| Pointing (JAX) | `test_pointing.py:37`, `test_b1_pointing_selfcal` | Rust pointing simulation | yes | vis 2e-9, Jacobian 1e-10/1e-7, **only in the test** | JAX ↔ Rust (owner's request) |
| MS reader (`core_ms`, `ms.rs`) | `test_core_ms` (3, all skip without `outputs/core-e-oracle-*`), `test_t1_casacure_oracle` (11); 7 Rust | python-casacore dump; casacure | yes (skips) | byte-identical (`test_core_ms.py:57`) | none |
| MS writer (`core_ms_write`, `ms_write.rs`, ...) | `test_core_ms_write` (7), `test_e4/e5/e6_*`; Rust tests except `ms_schema.rs` (0) | casacore trees (E3-E6) | yes (skip without results) | byte-identical trees | none |
| Formats (`formats/*`) | `test_dfio_formats` (16) | `tools/formats-oracle` container, `results/dfio-formats.json` | archived verdicts; `test_archived_verdicts` accepts the recorded "fail" rows | `check_formats.py:419,681` 1e-6 | none |
| MS inspection (`core_pipeline.inspect_ms`, `check_data`) | `test_w4_unsupported` (windows, DDIDs, empty selections, zero rows, missing weights, 1/2/circular correlations), `test_e5_prereview` | none | — | n/a | none. `test_ms_inspection.py` tests the example script, not `inspect_ms` |
| listobs (`rang.tasks.listobs`, merged 6b731e1 after this audit started) | `test_v8a_listobs` (record keys, selections refused, listfile, CLI refusals, no visibility column read) | CASA 6.7.6.14 `listobs` | yes, `test_fixture_matches_casa_archive` (skips without the fixture MSs) | 0 differences on 8 MSs + ESO137 (V8a note) | none. Not audited further here |
| Config | `test_e5_prereview.py:58` fuzz (no crash), `test_w2_commands` (unknown keys) | — | — | — | — |
| CLI, gemclean CLI | `test_core_cli` (29), `test_g8_gemclean`; 4+1 Rust | — | — | — | — |

### GPU rule (AGENTS.md)

The only GPU code is the wgpu FFT and the w-stack inversion. Both have CPU twins and parity tests with
written tolerances. Three gaps remain:

- **Silent pass.** Without an adapter the parity tests print "skipped" and pass (`gpu/tests.rs:15-31`).
  CI and the WSL host have no adapter, so parity runs only on a Windows host with a GPU. The full
  check's `core-test-gpu` step shows a pass either way. This is a follow-up (§4).
- **Tolerance mismatch.** The test's f64 bound (1e-12) is tighter than the note's frozen 1e-10. The test
  leaves `psf_normalization` out of exact counter equality, which the note records as "fails as frozen"
  (`x2-wgpu.md:380`). The f32 path is exposed at 1e-4, but the note says it cannot replace the CPU path
  (`:37`, `:156`). That limit should go on `docs/limits.md`.
- **wgrid requests ran on the CPU.** `gridder="wgrid"` with `device="gpu"` (or
  `RANG_GRIDDER_DEVICE=gpu`) ran on the CPU silently. This is fixed (§3).

The JAX nets (F2/F3) and JAX pointing have their tolerances written only in the tests. A line each in
their notes would make the rule hold in writing.

## 2. Gaps found

Each row is marked F (fixed here, with a test), T (test added, no code change) or open (§4). The F and
T rows were reproduced by a test that failed or would have failed before the fix. The open rows were
read from the code by the audit and not reproduced, so some are candidates only: the Rust panic
candidates, the padding overflow and the NaN gridding behaviour.

| # | Gap | Where | State |
|---|---|---|---|
| 1 | `core_grid.invert(gridder="wgrid", device="gpu")` ran on the CPU silently, against the module's "never falls back" promise | `core_grid.py:221` | F |
| 2 | A non-ASCII byte in a FITS header card made the reader panic: a lossy UTF-8 decode, then `text[..8]` / `text[8..10]` on a character boundary. Reachable through `-predict` model images and `-fits-mask` | `gemclean/fits.rs:136`, `mask.rs:353` | F |
| 3 | `read_fits_mask` had no direct test (size mismatch, empty mask, truncated data) | `mask.rs:345` | T |
| 4 | Gain solve with zero rows died in numpy (`zero-size array ... maximum`) | `cal_gain.py:274` | F |
| 5 | Gain solve silently truncated per-row arrays (`antenna1` longer than `nrow`); negative bins gave a cryptic error | `cal_gain.py:265-277` | F |
| 6 | **NaN poisoned the gain, bandpass and delay solves.** `cal/diag.rs` and the delay kernels have no non-finite guard, and nothing in the Python calibration path flags non-finite data. One NaN visibility in 5 % of cells made every gain (48/48) or delay NaN, with its flag clear. Only the array API was run. On an MS, a flag stage whose strategy has `flag_nans_zeros` (CARACal's does) flags such cells in the flagged column first. A run without it, or NaN in the corrected column or the model, would have reached the solver; the MS route was not run. `solve.rs` skips such cells. No test fed NaN or an all-flagged set to a solver. Found by the new test | `cal_gain._kernel`, `cal_delay` | F: `cal_gain.finite_cells` flags and zeroes non-finite data, model and weight cells. The result is now bit-identical to flagging the same cells (gain ap/p, QuartiCal referencing, delay, delay+offset; gains, delays, offsets, SNR, errors, flags). Finite inputs are unchanged. All flagged → every solution flagged (T) |
| 7 | Write-back layout: a negative `POLARIZATION_ID` / `SPECTRAL_WINDOW_ID` picked the last subtable row, and a large one raised a bare `IndexError` | `core_writeback.py:156` | F |
| 8 | Flag-version names: only `/` refused. A `\` nested directories on Windows, and `: * ? " < > \|` failed there | `flagversions.py:135` | F (refused on every OS) |
| 9 | `fluxstd.manual` gave a quiet NaN or inf for a frequency ≤ 0, where `model()` raises | `fluxstd.py:331` | F |
| 10 | `gemclean -threshold nan` never ended the minor cycle; negative and infinite thresholds were accepted. The rule is the one rang's `-auto-mask` already uses, `non_negative`; WSClean's own parsing of `-threshold` was not checked | `gemclean/cli.rs:410` | F (`-threshold`, `-abs-threshold`, `-auto-threshold`) |
| 11 | `ffi_flag::decode_steps` had no test | `ffi_flag.rs:90` | T |
| 12 | Pipeline commands (`rang-core flag` etc.) show an `OSError` traceback for a missing subtable or column; `config check` exits 2 cleanly | `core_cli.py:1342-1350` | open |
| 13 | Config numbers are not range-checked: `image.niter=-1`, `gain=-0.5`, `mgain=2`, `threads=-1`, `robust=-9`, term `max_iterations=-1`, `stop_fraction=5`, `G.minblperant=-2` are all accepted. `niter -1` fails late in gemclean ("cannot read") | `core_config.py` | open |
| 14 | gemclean `-mgain`, `-gain` are not range-checked at parse time. `-gain` is checked when the run starts (`gemclean.rs:1474`) | `cli.rs:384` | open (WSClean's own ranges to be read first) |
| 15 | An explicit `image.column: CORRECTED_DATA` on an MS without that column is refused at stage time (exit 1), not in preflight | `core_pipeline.py:2143` | open |
| 16 | `WEIGHT_SPECTRUM` is checked on row 0 only; a wrong-shape cell there makes the column count as absent | `core_pipeline.py:164` | open |
| 17 | NaN `uvw`, frequency or pixel scale is not rejected by the gridders: NaN `uvw` lands at the DC cell (`grid.rs:415`) or propagates (`wgridder.rs:560`). `bucket` checks no pixel size | `grid.rs`, `wgridder.rs`, `weights.rs:83` | open |
| 18 | `certified_clean` does not range-check `gain` (gemclean does) | `clean_certified.rs:468` | open |
| 19 | `cal_selfcal.freq_bins([])`, `flag_extend.extend_flags` with 2-D flags and `cal_bandpass.fill_gaps` ndim give cryptic errors; `bandpass.rs:25,93` `assert_eq!` would panic through FFI (caught by `catch_unwind`) | various | open |
| 20 | `MsTable` (pyo3) has no `catch_unwind`. A panic would surface as `PanicException`, a `BaseException` that `except (OSError, ValueError)` does not catch. `ms_write.rs` has about 30 map-lookup `unwrap()`s and `be_i32` unchecked indexing on file buffers (`:47`) | `core/py/src/lib.rs:1758` | open |
| 21 | Flag versions differing only in case collide on Windows/macOS | `flagversions.py:166` | open |
| 22 | `sky.load` reads `utf-8`, not `utf-8-sig`; a BOM breaks `#format:` detection | `sky.py:229` | open |
| 23 | The solver oracles (QuartiCal, CASA) are offline runs recorded in notes, not pytest gates. Only archived JSON/npz receipts are read in the suite | `research/c2*.md` | open (by design; v0.2.0 rests on E2/E3) |
| 24 | MS-reader oracle and error tests skip unless `outputs/core-e-oracle-*` is present, so in CI and fresh worktrees they never run | `test_core_ms.py` | open (cheap: rerun the error assertions on `core_ms_write.default_ms`) |
| 25 | Untested public functions: `caltable.jones_terms`, `h5parm.diagonal_gains`/`summary`, `killms.normalise_to_antenna0`, `quartical_store.read_term`, `sky.direction_cosines`/`save_any`, `measures.feed_angle`/`location`, `core_ms.reader_slice`, `core_policy.axis_weights`, `cal_refant.is_auto`, `tvflag_adjoint.tv_value`, `applycal.separation`, about 35 helpers in `f2flag`/`f3flag` (research flaggers, not shipped) | — | open |
| 27 | **NaN in the polarisation solves.** Df's leakages were all NaN (52 of 56 values) with their flags clear from NaN in 5 % of cells. KCROSS stayed finite but differed from the flagged solve. Xf was already exact | `cal_pol._flat` (Df, KCROSS, Xf) | F: `_flat` calls `cal_gain.finite_cells`; all three are now bit-identical to the flagged solve. Gpol goes through `cal_gain`. `cal_fluxscale` works on gain tables, not visibilities, and was not probed |
| 26 | `df5o-deconv-oracles.md:34` cites `core/src/deconv.rs`, which does not exist | note | open (doc fix) |

## 3. What changed

None of the fixes changes a result on the inputs the shipped defaults were measured on. On finite
data every solver returns exactly what it did. Two kinds of change are not errors:

- **NaN input now gives a result.** Non-finite visibility, model or weight cells are flagged and
  zeroed before the gain, bandpass, delay, KCROSS, Xf and Df kernels. A result that was all NaN with its
  flags clear is now the solution of the same cells flagged.
- **A FITS header with a stray non-ASCII byte is read.** The reader used to panic on it. Every valid
  FITS header is ASCII, so such files read exactly as before.

Every other fix turns an input that used to run wrong, or fail obscurely, into a clear error.

- `core_grid.invert`: `gridder="wgrid"` with a GPU device, by argument or environment, raises
  `RuntimeError`.
- `gemclean/fits.rs`, `gemclean/mask.rs`: header bytes outside ASCII read as `?`, so a card is always
  80 one-byte characters.
- `cal_gain.finite_cells`, called by `cal_gain._kernel`, `cal_delay.solve` and `cal_pol._flat`, flags and zeroes every
  non-finite data, model or weight cell. Finite inputs return unchanged, so a solve on finite data is
  unchanged bit for bit. On the chunked route with `calibrate.average_freq`, a NaN channel makes the
  averaged cell NaN, and that row's averaged cell is flagged. Averaging over the finite channels instead
  would be a further change; it is not made here.
- `cal_gain._kernel`, which also serves bandpass and the chunked `gaincal` route: refuses zero rows or
  channels, per-row arrays of the wrong length, a `freq_bin` shorter than the channels (a longer one
  stays allowed, since a frequency-averaged chunk keeps the full map), and negative bins.
- `core_writeback.layout`: refuses out-of-range DATA_DESCRIPTION ids with `UnsupportedLayout` (exit 2
  in the commands).
- `flagversions.save`: refuses `\ : * ? " < > |` in names on every platform. Reading versions CASA
  wrote is unchanged.
- `fluxstd.manual`: refuses non-finite or non-positive frequencies.
- `gemclean`: `-threshold`, `-abs-threshold` and `-auto-threshold` must be finite and ≥ 0, the same
  check `-auto-mask` already has.

New tests: `tests/test_correctness_audit.py` has 24 cases. The Rust tests are
`gemclean::fits::a_non_ascii_header_byte_does_not_panic`,
`gemclean::mask::fits_masks_read_refuse_and_never_panic`,
`gemclean::cli::thresholds_are_finite_and_not_negative` and
`ffi_flag::decode_steps_reads_known_codes_and_refuses_the_rest`. Results and the check are in §5.

## 4. What is left (proposed order)

1. **GPU parity that cannot pass silently.** Add a `RANG_REQUIRE_GPU=1` that turns the adapter skip into
   a failure, and run it once per merge batch on the Windows host. Write the f32 limit into
   `docs/limits.md`.
2. **Config ranges (#13).** Add a minimum and maximum per numeric key in `core_config`'s schema. It is
   cheap, but it touches every key's doc line, so it gets its own branch.
3. **`OSError` in the pipeline commands (#12).** Report a read failure in preflight as exit 2, and a
   write failure in a stage as exit 1 with the path, without a traceback.
4. **NaN guards in the gridders (#17)** and `certified_clean`'s gain (#18).
5. **Reader error tests without the archive (#24)**, and a `catch_unwind` in `MsTable` (#20).
6. The remaining untested helpers (#25), the BOM (#22), case collisions (#21) and the note fix (#26).

## 5. Run record

Host: the development host (16 threads), every run under the main checkout's `tools/heavy_lock.py`.

| Run | Result | Wall |
|---|---|---|
| `cargo test --release --lib -- gemclean::fits gemclean::mask gemclean::cli ffi_flag` (4 slots) | 13 passed | build plus test, lock wait excluded, not separated |
| pytest on 21 related files, `-n 4`, before the NaN fix | 253 passed, 13 skipped, **1 failed**: `test_gain_solve_nan_cells_equal_flagged_cells`, all 48 gains NaN (finding #6) | 27 s pytest |
| `python -m rang.check --skip core-clippy-gpu,core-test-gpu,pytest` on 4e9b64a (main 2a02470) | PASS: root 23/23 (1 ignored), core 274/274, clippy, ext build, gain hashes | 2,207 s with lock wait |
| `python tools/check_all.py --quick` after rebasing onto main 30d9412 | PASS: core 274/274, pytest (the diff's files) 509 passed and 22 skipped, gain hashes | 903 s, lock wait excluded |
| `python tools/check_all.py --quick` on 898b39d (with the polarisation NaN fix) | PASS: root 23/23, core 274/274, pytest 534 passed and 22 skipped, gain hashes | 902 s, lock wait excluded (17,365 s with it) |

The CI run of the pushed branch is linked in the hand-back. CI has no archives, so the oracle-gated
tests (calibration solvers, imaging, MS writing) need the coordinator's full check at merge.

## For the coordinator

- Branch `claude/correctness-audit-35f2b0`. It is not merged and not for merging by this session. The
  diff is 11 source files, one new test file, this note, its index line and the CHANGELOG.
- Behaviour changes, all on bad input only: see §3 and the CHANGELOG lines. The shipped defaults' numbers
  are unchanged.
- The open items in §4 are follow-ups. Items 1 and 2 are the ones worth doing before v0.2.0.
- The NaN fix (#6, #27) touches the calibration solvers' inputs. It is exact on finite data, and the
  gain-hash gate passed, but the oracle tests need the full check at merge (CI has no archives).
