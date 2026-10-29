# Rang core, wave 2 task I: the imaging track replayed on the core

Protocol frozen 2026-10-29 on branch `core/i-imaging-replay` (from origin/main
`3e64bab`), before any driver code was written. Protocol commit `80d7523`. Status: **implemented; measured: criteria 1–7
pass as frozen against the archive and the host reproduction (pixels
within 6.1e-7 of the peak, PSFs 4.2e-7, template fluxes 1.4e-7 relative,
response fractions 1.3e-7 absolute, weights 1.4e-15, closures below
1e-8 Jy/beam); criterion 8 failed as frozen on its git-status clause
through an operator edit during the 62 s run (archive inputs unchanged)
and holds on both criterion 9 runs; criterion 9 passed through the CLI as
frozen and through Stimela only after a labelled environment step
(Stimela 2.1.4 cannot run cabs on Python 3.14; rerun in a 3.13 venv)**. Task I of
[core-parallel-plan.md](core-parallel-plan.md): run the fifteen archived dirty
inversions of [flagging-imaging.md](flagging-imaging.md) (archive
[gain-tv-next-imaging.json](results/gain-tv-next-imaging.json), WSL
reproduction `outputs/tv-next-imaging-wsl-20261029-01`) with the core's
imaging weights ([task B](core-b-weighting.md)), w-stacking gridder
([task C](core-c-gridder.md)) and Measurement Set reader
([task E](core-e-ms-reader.md)) instead of WSClean 3.6-1 in the
`rang-flagging-next-imaging:local` container, and recompute the archived
template fits, response fractions and closures with the unedited audit
algebra of `flagging_imaging`. A reimplementation; under AGENTS.md not a
scientific contribution, and no archived result may change because of it.

## Question

Does the archived imaging family, which was measured through WSClean, come
out the same when every pixel is produced by the Rust core, within the
tolerances task A derived from WSClean's own approximation sensitivity
([core-a-imaging-sensitivity.md](core-a-imaging-sensitivity.md)): template
flux 4.7e-6 relative, response fraction 1.6e-7 absolute, dirty-image
L∞ 8.8e-6 of the peak, PSF L∞ 2.8e-6, weight sums 1e-9 relative?

## Design (fixed before code)

- **Inputs, read only.** The archived run `outputs/tv-next-imaging-wsl-20261029-01`:
  the two whole-MS backups `backups/response-input.ms` and
  `backups/caracal-input.ms` (the clean inputs the archived columns were
  written into), the fifteen `checkpoints/<label>-written.npz`
  (`CORRECTED_DATA` complex64, `FLAG`, `FLAG_ROW`, `support`, verified by
  the archived audit to equal what WSClean read), `checkpoints/<label>-result.json`
  (the job's role) and `images/<label>-{dirty,psf}.fits` for the pixel
  comparison. No gain is re-solved, no visibility recomputed, no injection
  regenerated, no Measurement Set copied or written.
- **Reader.** `rangtoy.core_ms` reads `UVW`, `WEIGHT_SPECTRUM`, `FIELD_ID`,
  `ANTENNA1`, `ANTENNA2`, `DATA_DESC_ID` and the `SPECTRAL_WINDOW/CHAN_FREQ`,
  `FIELD/PHASE_DIR` and `POLARIZATION/CORR_TYPE` subtables of each backup
  through the core (TiledColumnStMan, TiledShapeStMan, StandardStMan,
  IncrementalStMan). The columns are checked against task C's python-casacore
  export (`outputs/core-c-20261029-01/inputs/<role>-common.npz`); a mismatch
  stops the run.
- **Per job** (`rangtoy.core_imaging.image_job`), in the order of the archived
  family: channels 1024–3071 of the checkpoint's `CORRECTED_DATA`, `FLAG` and
  the backup's `WEIGHT_SPECTRUM` go through `core_weights.stokes_i` (WSClean's
  `-pol I` rule); `core_weights.imaging_weights` with Briggs 0.5 on the
  padded 616-pixel half grid, rank filter 3.0/16, rows selected by field 0,
  cross-correlations and data description 0, wavelengths by
  `wsclean_wavelengths` (task B, bit-identical to WSClean); the reader weight
  is zeroed on rows with `FLAG_ROW` (task C); `core_grid.invert` with the
  archived settings (512 × 512 at 8 arcsec, Kaiser–Bessel 7, 1023×, 64
  w-layers, padding 1.2) returns the dirty image, the PSF and WSClean's
  counters; `core_grid.write_fits` writes `images/<label>-{dirty,psf}.fits`
  with the archived WCS and the header keys `WSCVWSUM`, `WSCIMGWG`,
  `WSCNORMF`, `WSCNVIS`, `WSCNWLAY`, `WSCDATAC`, `WSCWEIGH`, `WSCNITER`.
- **Metrics.** The unedited `flagging_imaging.linear_image_fit`,
  `image_diagnostics` and `image_geometry` (module SHA256 recorded) give the
  unit basis, the fixedG0 reference fit, the known-family fits of the eight
  paired jobs and the two unit jobs, the conditional responses, the fixed
  offsource RMS, the two dirty-image closures and the PSF L∞ against the
  fixedG0 PSF. The result is written as `result.json` in the archive's raw
  layout (`jobs/<label>/{role, headers, image_geometry, diagnostics,
  PSF_linf_difference_vs_fixedG0, known_family_dirty_fit,
  conditional_response_vs_fixedG0, unsupported_original_TEST_samples}`,
  `reference_fit`, `dirty_image_closures_jy_per_beam`, `settings`,
  `new_QC_solves`, `policy_selection`, `exported_or_deployable_MS`) plus
  the core's own `stats`, `seconds` and provenance (core library SHA256,
  checkpoint SHA256s, module SHA256s). Archive fields the replay cannot
  reproduce are not written and are excluded by the comparator (listed in
  `core_imaging.EXCLUDED_KEYS`): the WSClean version, the Gaussian beam fit
  `BMAJ/BMIN/BPA` (not ported), `training_additions` (a caracal-input
  provenance count the checkpoints do not carry), the precast visibility
  closures (computed before the complex64 cast the checkpoints hold), the
  MS audits, FITS file hashes and wall times.
- **Comparator** `examples/compare_core_imaging.py` (`core_imaging.compare_replay`,
  `pixel_comparison`): every archive leaf is classified by
  `classify_replay` into exact, template flux (relative 4.7e-6), unit-template
  self-fit coefficients (absolute 4.7e-6 against the 1 Jy template; see the
  precondition), response fraction (absolute 1.6e-7), PSF L∞ versus fixedG0
  (absolute 2.8e-6), weight sums (relative 1e-9), WCS floats (1e-9 degrees),
  closures (both archive and core at or below the family's frozen 1e-6
  Jy/beam, difference reported), reported (offsource RMS and std, peak,
  fit condition, MSE proxy) or excluded. A missing non-excluded field fails.
  Pixels are compared as in task C (L∞, RMS, L∞ relative to the archive
  peak, WCS keys) with the central 256 × 256 and the border reported
  separately, as task A suggested.
- **Side effects.** The run snapshots size and modification time of every
  file of the archived run and of `git status` before and after
  (`side-effects.json`, as task H's `_audited`), and writes only into its
  fresh `outputs/core-i-<date>-NN` directory.
- **Recipe and CLI.** `recipes/core-imaging.yaml` (python-flavour cabs on
  the native backend, `_include: core-cabs.yaml`, steps `image`,
  `environment`, `compare`) and `python -m rangtoy.core_imaging {run,compare}`.
  The task H pattern fits except in two shared places this branch does not
  edit: `rangtoy.core_cli` (the `rang-core imaging` subcommand and the
  `COMPARATORS["imaging"]` entry) and the shared `rang-core-compare` cab's
  `choices` list; the recipe therefore carries its own compare cab calling
  `rangtoy.core_imaging.compare`, and the `core_cli` lines are listed under
  "For the coordinator".

## Precondition: comparator on archive versus host reproduction (measured before the freeze)

`compare_core_imaging.py outputs/tv-next-imaging-wsl-20261029-01/result.json
research/results/gain-tv-next-imaging.json ... --images outputs/core-c-20261029-01/images
outputs/tv-next-imaging-wsl-20261029-01/images` (receipt
`outputs/core-i-20261029-00-precondition/archive-vs-host.json`, 0.27 s, 68 MB):

| Class | Compared | Worst difference |
| --- | ---: | ---: |
| exact | 532 | 0 |
| template flux (relative) | 16 | 3.9e-16 |
| unit-template self-fit (absolute, Jy) | 4 | 2.2e-16 |
| response fraction (absolute) | 16 | 3.3e-16 |
| PSF L∞ versus fixedG0 (absolute) | 15 | 0 |
| weight sums (relative) | 30 | 0 |
| WCS floats (degrees) | 180 | 0 |
| closures (both ≤ 1e-6 Jy/beam) | 2 | 0 |
| reported | 65 | 0.77 relative on the `unit-extended` self-fit MSE proxy (7e-17 against 6e-17 Jy²) |
| excluded | 423 | – |

Zero failures; task C's WSClean rerun images are pixel-identical to the
archive on all 30 images (L∞ 0). The first run of the comparator had one
failure: the `unit-extended` self-fit's cross coefficient is 6.2e-17 Jy in
the archive and 7.1e-17 Jy in the host reproduction, a rounding zero on
which a relative rule is undefined; task A's spread (`FITTED_JOBS` and the
reference fit) never covered the two unit jobs. The unit-flux class above was
added before the freeze and is the only change. The core's MS reads were
also checked before the freeze: `UVW`, `WEIGHT_SPECTRUM`, `CHAN_FREQ` and
`PHASE_DIR` of both backups equal task C's export exactly, and the Briggs
weights of `omitted-total` computed from them equal WSClean's stored
`IMAGING_WEIGHT_SPECTRUM` bit for bit (as task B found on its own oracle).

## Acceptance criteria (frozen)

Gated, decided here:

1. **Weights.** For all fifteen jobs the core's `WSCVWSUM`, `WSCIMGWG` and
   `WSCNORMF` equal the archived FITS headers within 1e-9 relative and
   `WSCNVIS` exactly (9169; 7812 on `caracal-firstpass-rejected`).
2. **Pixels.** Against the archived FITS, every dirty image is within 8.8e-6
   of its own archived peak (L∞) and every PSF within 2.8e-6 absolute; the
   eight WCS keys agree (floats to 1e-9 degrees).
3. **Template fluxes.** The reference fit's two coefficients and the eight
   paired jobs' coefficients agree with the archive within 4.7e-6 relative;
   the unit jobs' self-fit coefficients within 4.7e-6 Jy absolute; `rank`
   2 and `available` true everywhere the archive has them.
4. **Response fractions.** The sixteen conditional responses agree within
   1.6e-7 absolute.
5. **Closures and matched PSFs.** Both core dirty-image closures are at or
   below 1e-6 Jy/beam (the family's frozen tolerance), and every
   `PSF_linf_difference_vs_fixedG0` agrees with the archive within 2.8e-6
   absolute (0 on the fourteen matched jobs is expected and reported; the
   gate is the tolerance).
6. **Exact fields.** Every other compared archive field (roles, settings,
   `image_geometry` strings and `CRPIX`, `unsupported_original_TEST_samples`,
   `fixed_offsource_pixels`, `pixel_count`, header strings and integers,
   `new_QC_solves`, `policy_selection`, `exported_or_deployable_MS`) is
   equal, and no non-excluded field is missing.
7. **Host reproduction.** Criteria 3–6 also hold against
   `outputs/tv-next-imaging-wsl-20261029-01/result.json`.
8. **No side effects.** The archived run's files (size and modification
   time) and `git status` are unchanged; the run writes only into its own
   directory.
9. **Recipe and CLI.** One Stimela run of `recipes/core-imaging.yaml` and
   one direct `python -m rangtoy.core_imaging run` each produce a result that
   passes criteria 1–7; the two results are compared with each other and
   their differences reported (0 expected from the deterministic core).

Reported, not gated:

10. The offsource RMS and std, peaks, fit conditions and MSE proxies
    (relative differences), the closure values themselves against the
    archive's, and the central and border RMS pixel differences per job.
11. Cost: per job the read, weighting, gridding and FITS times; the whole
    run with `/usr/bin/time` (wall, peak RSS); the Stimela run beside the
    direct run; against the archived container run (24.7 s of WSClean wall
    inside the container for the fifteen inversions, 2.5–4.8 s each) and
    task C's core gridding (27–37 s per job). Every tool run of this task is
    logged below.

The task is reported as passed only if criteria 1–9 pass as frozen. A
failure is recorded here with its numbers; any later step is labelled
post-hoc and the result archived as
[core-i-imaging-replay.json](results/core-i-imaging-replay.json).

## Timings (every tool run of this task)

| When | Tool run | Wall | Peak RSS | Note |
| --- | --- | ---: | ---: | --- |
| 2026-10-29 | `uv venv -p /usr/bin/python3.14` + `uv pip install -e '.[pointing,beam,test,imaging]' ruff` (public PyPI) | 1.6 s | – | uv cache warm from wave 1 |
| 2026-10-29 | `cargo +1.93 build --release` core and root crates, `CARGO_BUILD_JOBS=8` | 3.8 s | – | |
| 2026-10-29 | `uv pip install stimela==2.1.4` | 2.9 s | – | for criterion 9 |
| 2026-10-29 | input probe: core MS reads of both backups, task C export check, one job's Briggs weights | 2.8 s (2.5 s first library load) | – | scratch, not committed |
| 2026-10-29 | `compare_core_imaging.py` archive vs host reproduction with 30 task C rerun images (precondition) | 0.59 s, then 0.27 s | 68 MB | first run found the unit-flux gap |
| 2026-10-29 | `pytest tests/test_core_imaging.py` (8 tests), four times while writing; `tests/test_core_cli.py` (8) once | 0.1–0.5 s | – | |
| 2026-10-29 | one-job smoke (`omitted-total`) through `image_job`, scratch script | 4.3 s | 119 MB | labelled smoke; FITS deleted |
| 2026-10-29 | **frozen run `-01`**, `examples/run_core_imaging.py` (15 jobs, both comparisons) | 61.9 s | 213 MB | gridding 3.96–4.09 s per job (60.6 s), Stokes I + weights 6 ms per job, FITS 10 ms, MS reads 0.04 s each; comparators 0.3 s and 0.1 s |
| 2026-10-29 | Stimela `core-imaging`, Python 3.14 venv (failed load of the native backend) | 1.2 s | 93 MB | `outputs/core-i-20261029-02-stimela`, logs only |
| 2026-10-29 | direct CLI run `-03` + two `compare` subcommands | 60.5 s + 0.27 s + 0.08 s | 222 MB | criterion 9 |
| 2026-10-29 | `uv venv -p 3.13 .venv313` + extras + `stimela==2.1.4` | 1.9 s | – | environment step for criterion 9; not committed, deleted after the run |
| 2026-10-29 | Stimela `core-imaging` run `-04`, Python 3.13 venv, + host comparison | 62.7 s + 0.07 s | 221 MB | `image` cab 60.7 s; Stimela overhead 1.5 s |
| 2026-10-29 | `examples/archive_core_imaging.py` (three runs) | 0.09 s | – | |
| 2026-10-29 | `bash tools/check-all.sh`, `CARGO_BUILD_JOBS=8` | 216 s (pytest 721 passed in 208 s) | 1.76 GB | once before the final commit; overall PASS, machine otherwise idle |

## Measured result of the frozen run (2026-10-29)

Code written after the freeze: the driver half of
`python/rangtoy/core_imaging.py` (`read_ms_inputs`, `image_job`, `run`,
`compare`, `main`), `examples/run_core_imaging.py`,
`examples/archive_core_imaging.py`, `recipes/core-imaging.yaml` and
`tests/test_core_imaging.py`. A one-job smoke of `omitted-total`
(`outputs/core-i-20261029-00-smoke`, 4.3 s, deleted FITS) preceded the
frozen run and is not part of the measurement.

**Frozen run `-01`** (`outputs/core-i-20261029-01`,
`examples/run_core_imaging.py`, 61.9 s wall, 213 MB peak RSS under
`/usr/bin/time`; receipts `compare-archive.json`, `compare-host.json`,
`side-effects.json`; archive
[core-i-imaging-replay.json](results/core-i-imaging-replay.json)). The core
read both backup Measurement Sets in 0.04 s each (equal to task C's export
on every checked column), formed Stokes I and Briggs weights in 6 ms per
job, gridded each job in 3.96–4.09 s and wrote the FITS in 10 ms. Against
the archive (`raw_result`), with the archived FITS pixels:

| Criterion | Class | Compared | Worst | Tolerance | Result |
| --- | --- | ---: | ---: | ---: | --- |
| 1 weights | `WSCVWSUM`, `WSCIMGWG`, `WSCNORMF` vs the archived FITS headers (relative); `WSCNVIS` exact | 45 + 15 | 1.4e-15 | 1e-9 | **pass** (9169 on fourteen jobs, 7812 on `caracal-firstpass-rejected`) |
| 2 pixels | dirty L∞ / archived peak | 15 | 6.11e-7 (`complete-total`) | 8.8e-6 | **pass** |
| 2 pixels | PSF L∞ | 15 | 4.17e-7 (`caracal-firstpass-rejected`) | 2.8e-6 | **pass** |
| 2 pixels | WCS keys (degrees) | 240 | 4.3e-14 | 1e-9 | **pass** |
| 3 template fluxes | reference fit and eight paired fits, relative | 16 | 1.43e-7 (`complete-adaptation`, extended) | 4.7e-6 | **pass** |
| 3 template fluxes | unit self-fits, absolute Jy | 4 | 1.1e-15 | 4.7e-6 | **pass** |
| 4 response fractions | absolute | 16 | 1.31e-7 (`omitted-direct`, extended) | 1.6e-7 | **pass** |
| 5 closures | omitted, complete (core 7.45e-9, 7.36e-9 Jy/beam; archive 3.54e-8, 3.81e-8) | 2 | 3.07e-8 difference | both ≤ 1e-6 | **pass** |
| 5 matched PSFs | `PSF_linf_difference_vs_fixedG0`, absolute | 15 | 8.9e-8 (`caracal-firstpass-rejected`: 0.07469796 vs 0.07469787; 0 on the fourteen matched jobs) | 2.8e-6 | **pass** |
| 6 exact | strings, integers, booleans, `CRPIX` | 532 | 0 | – | **pass**, no non-excluded field missing (423 excluded) |
| 7 host reproduction | all of the above against `outputs/tv-next-imaging-wsl-20261029-01/result.json` | same counts | fluxes 1.43e-7, responses 1.31e-7, otherwise identical | – | **pass** |
| 8 side effects | archive files (458) and git status | – | inputs unchanged; **git status changed** | – | **fails as frozen on the git clause**, see below |

The reference fit recovers 60.0000014 / 119.9999933 mJy against the
archive's 59.9999962 / 119.9999904 (1.4e-7 and 2.4e-8 relative). The
response fractions:

| Job | Core (compact, extended) | Archive | Absolute difference |
| --- | ---: | ---: | ---: |
| `omitted-total` | 0.4916699, 0.7756690 | 0.4916699, 0.7756689 | 4.8e-8, 6.4e-8 |
| `omitted-direct` | 1.0019789, 0.9998813 | 1.0019789, 0.9998814 | 1.0e-9, 1.3e-7 |
| `omitted-adaptation` | −0.5103091, −0.2242123 | −0.5103091, −0.2242123 | 2.6e-8, 5.8e-9 |
| `complete-total` | 0.9969156, 0.9864974 | 0.9969156, 0.9864974 | 1.2e-8, 9.8e-9 |
| `complete-direct` | 1.0000353, 1.0000176 | 1.0000353, 1.0000176 | 1.6e-8, 8.2e-8 |
| `complete-adaptation` | −0.0031198, −0.0135202 | −0.0031198, −0.0135202 | 2.0e-10, 2.3e-9 |

Pixels per job, core against the archived FITS (Jy/beam; the central
256 × 256 and the border RMS separately; the same numbers as task C's run
`-05` to the printed digit, so the gridder has not moved since):

| Job | Dirty max abs | Dirty RMS | Central / border RMS | Archive peak | Max / peak | PSF max abs | PSF RMS | Grid s |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `unit-compact` | 4.17e-07 | 4.70e-08 | 5.2e-08 / 4.5e-08 | 0.9908 | 4.21e-07 | 3.58e-07 | 5.78e-08 | 4.02 |
| `unit-extended` | 2.38e-07 | 2.75e-08 | 3.0e-08 / 2.7e-08 | 0.4722 | 5.05e-07 | 3.58e-07 | 5.78e-08 | 3.96 |
| `fixedG0-reference` | 4.47e-08 | 5.81e-09 | 6.7e-09 / 5.5e-09 | 0.08573 | 5.21e-07 | 3.58e-07 | 5.78e-08 | 4.00 |
| `clean-full` | 5.72e-06 | 8.31e-07 | 7.9e-07 / 8.4e-07 | 14.96 | 3.83e-07 | 3.58e-07 | 5.78e-08 | 4.05 |
| `omitted-full` | 5.72e-06 | 8.85e-07 | 7.6e-07 / 9.2e-07 | 14.96 | 3.83e-07 | 3.58e-07 | 5.78e-08 | 4.02 |
| `omitted-total` | 3.73e-08 | 4.56e-09 | 5.2e-09 / 4.3e-09 | 0.06297 | 5.92e-07 | 3.58e-07 | 5.78e-08 | 4.07 |
| `omitted-direct` | 4.47e-08 | 4.83e-09 | 6.0e-09 / 4.4e-09 | 0.08585 | 5.21e-07 | 3.58e-07 | 5.78e-08 | 4.09 |
| `omitted-adaptation` | 2.24e-08 | 2.78e-09 | 3.2e-09 / 2.6e-09 | 0.0419 | 5.33e-07 | 3.58e-07 | 5.78e-08 | 4.03 |
| `complete-full` | 6.68e-06 | 8.08e-07 | 7.7e-07 / 8.2e-07 | 14.93 | 4.47e-07 | 3.58e-07 | 5.78e-08 | 4.04 |
| `complete-total` | 5.22e-08 | 5.75e-09 | 6.6e-09 / 5.4e-09 | 0.08541 | 6.11e-07 | 3.58e-07 | 5.78e-08 | 4.05 |
| `complete-direct` | 4.47e-08 | 4.86e-09 | 6.0e-09 / 4.4e-09 | 0.08574 | 5.21e-07 | 3.58e-07 | 5.78e-08 | 4.03 |
| `complete-adaptation` | 8.15e-10 | 1.14e-10 | 8.4e-11 / 1.2e-10 | 0.001402 | 5.81e-07 | 3.58e-07 | 5.78e-08 | 4.03 |
| `caracal-no-change` | 5.72e-06 | 8.31e-07 | 7.9e-07 / 8.4e-07 | 14.96 | 3.83e-07 | 3.58e-07 | 5.78e-08 | 4.05 |
| `caracal-mild` | 6.68e-06 | 8.74e-07 | 7.9e-07 / 9.0e-07 | 14.96 | 4.46e-07 | 3.58e-07 | 5.78e-08 | 4.04 |
| `caracal-firstpass-rejected` | 5.72e-06 | 7.22e-07 | 6.7e-07 / 7.4e-07 | 14.73 | 3.89e-07 | 4.17e-07 | 7.60e-08 | 4.09 |

Reported (criterion 10): the offsource RMS and std move by at most 2.2e-7
relative (`fixedG0-reference`), the peaks by at most 4.7e-7 (`omitted-total`),
the fit conditions by 3.4e-8; the MSE proxies of the two unit self-fits are
rounding residuals (3.9e-32 against 2.6e-33 Jy², a "difference" of 0.93) and
of the fitted jobs agree to better than 1e-6. The core's closures (7.4e-9
Jy/beam) are five times smaller than WSClean's (3.5e-8, 3.8e-8) because the
core grids and transforms in double precision and the only rounding left
is the float32 FITS write; both are far below the family's 1e-6. The
difference is uniform over the image (central and border RMS within 20 % of
each other on every job), as expected for single-precision rounding and
unlike task A's kernel-size differences, which lived at the edges.

**Criterion 8 fails as frozen on the git clause.** `side-effects.json`
records `inputs_unchanged: true` (458 archive files, size and mtime) but
`git_status_unchanged: false`. The cause is the operator, not the driver:
`tests/test_core_cli.py` (the task H recipe test, see "For the
coordinator") was edited and `examples/archive_core_imaging.py` created
while the 62 s run was going (the test file's mtime is 50 s before
`result.json`'s). The run wrote only `images/` and `result.json`; the
comparator receipts were added by the runner afterwards. The criterion 9
runs below, during which nothing was edited, show the clause holding. No
rerun of `-01` was made.

### Criterion 9: recipe and CLI (measured, run after `-01`)

- **Direct CLI run** `python -m rangtoy.core_imaging run outputs/core-i-20261029-03-cli`
  (60.5 s wall, 222 MB; the two `compare` subcommands 0.27 s and 0.08 s):
  passes criteria 1–7 with every class at the frozen run's numbers (the
  core is deterministic: all 30 FITS SHA256 equal run `-01`'s, the
  reference fit and closures identical) and criterion 8 in full
  (`inputs_unchanged: true`, `git_status_unchanged: true`).
- **Stimela run, first attempt** (`outputs/core-i-20261029-02-stimela`,
  logs only, 1.2 s): the recipe loaded, validated its inputs and enabled
  the steps `image environment compare`, then Stimela 2.1.4 failed before
  invoking the cab with `RuntimeError: There is no current event loop in
  thread 'MainThread'` in its native backend. This is the asyncio
  event-loop change of Python 3.14 (the worktree venv is the system
  3.14.4; task H ran on a uv-managed 3.13.16). **Failed as frozen** on the
  environment, not on the recipe or the driver; the failed logs are kept.
- **Stimela run, repeated in a Python 3.13 venv** (environment step,
  labelled; no code or recipe change; `uv venv -p 3.13 .venv313`, the same
  extras plus `stimela==2.1.4`, not committed):
  `stimela -s opts.log.dir=... run recipes/core-imaging.yaml run-dir=outputs/core-i-20261029-04-stimela/imaging
  archive-dir=outputs/tv-next-imaging-wsl-20261029-01 export-dir=outputs/core-c-20261029-01/inputs`
  (62.7 s wall, 221 MB; the `image` cab 60.7 s, `environment` 0.2 s,
  `compare` 0.3 s; Stimela overhead 1.5 s) passes criteria 1–8:
  the recipe's own `compare` step against the archive with pixels, a
  separate comparison against the host reproduction, all 30 FITS SHA256
  equal run `-01`'s, `inputs_unchanged` and `git_status_unchanged` true.
  `environment.json` records the 3.13 venv with no `quartical`
  distribution, import or `goquartical` on `PATH` (the recipe never
  needed one). The failed 3.14 attempt and this run are both archived.
- **Run against run.** Under the frozen classes with wall times and the
  runs' own paths removed, the Stimela and CLI results equal run `-01`'s
  on all 1214 compared leaves with worst difference 0 (the core is
  deterministic across venvs and interpreters, 3.13 and 3.14).

## What this shows

The archived imaging family comes out the same on the core, with no
WSClean, no container, no Measurement Set copy and no python-casacore: the
checkpointed columns and the backup MSs go through the core's reader,
weights and gridder, and the unedited audit algebra returns the archived
template fluxes to 1.4e-7 relative, the response fractions to 1.3e-7
absolute and the closures below 1e-8 Jy/beam, while the pixels agree with
WSClean's to 6.1e-7 of the peak and the PSFs to 4.2e-7. Every difference is
at the single-precision level task C predicted, and 10–30 times inside task
A's tolerances; the response fractions, at 82 % of their tolerance, are
the closest, because 1.6e-7 is the finest of A's proposals (one tenth of
a 1.6e-6 movement) and the fractions divide two fits that each carry
float32 rounding. The whole family runs in 62 s, against 24.7 s of WSClean
wall inside the container for the inversions alone (the archived run's
emulated 2.5–4.8 s per job, which exclude the MS copies, column writes and
audits the container run also did; its complete wall was not archived),
so the core is 2.5× slower than WSClean on the inversion at these settings
and 7–9× faster than task C's run `-05` measured for the same gridder
code (the difference is machine load: eight sibling sessions then, one now).
Not ported: WSClean's Gaussian beam fit (`BMAJ`, `BMIN`, `BPA`), which the
archive carries as reported floats and nothing downstream uses.

## For the coordinator

- Shared files this branch had to touch, both listed here as the plan
  requires: `tests/test_core_cli.py` (task H's static recipe test
  hard-codes the list of `recipes/core-*.yaml` files and requires every cab
  to call `rangtoy.core_cli`; two minimal edits admit `core-imaging.yaml`
  and its `rangtoy.core_imaging` cabs, which `tests/test_core_imaging.py`
  checks). Nothing else outside the task's own files was edited.
- `python/rangtoy/core_cli.py` (not edited): to give `rang-core imaging`
  as task H's pattern wants, add a subparser `imaging` with `run_dir`,
  `--archive-dir` and `--export-dir` delegating to
  `rangtoy.core_imaging.run`, and `COMPARATORS["imaging"] = "compare_core_imaging.py"`
  (that script takes `result oracle receipt [--images CANDIDATE REFERENCE]`,
  the phase 3 argument order). The shared `rang-core-compare` cab in
  `recipes/core-cabs.yaml` would then need `imaging` in its `choices`; until
  then `core-imaging.yaml` carries its own compare cab.
- `research/tool-timings.md`: the rows of the timings table above.
  `README.md` and `STATE.md`: this report as the task I entry with the
  status line at the top. No `pub mod` line is needed: no Rust was added.
- Environment finding for every later recipe run: Stimela 2.1.4's native
  backend raises `There is no current event loop` on Python 3.14; the
  worktree venv is the system 3.14 (`uv venv -p /usr/bin/python3.14`), so
  core recipes need a 3.13 venv (`uv venv -p 3.13`) until Stimela catches
  up. Task H did not see this because uv chose 3.13 for it.
- Evidence to keep: `outputs/core-i-20261029-01` (frozen run, 32 MB of
  FITS and receipts), `-03-cli` and `-04-stimela`; `-00-precondition`
  (one receipt), `-00-smoke` (empty) and `-02-stimela` (failed logs,
  cited above) can be deleted after merging.
- Lesson for later protocols: the side-effect audit's git clause is only
  meaningful if the operator does not edit tracked files during the run;
  state that in the protocol, or snapshot only the paths the run may touch.

## Open questions

- The response-fraction tolerance (1.6e-7 absolute) is the tightest of
  task A's proposals and the replay sits at 82 % of it (`omitted-direct`,
  extended, 1.31e-7): a fraction divides two fits that each carry WSClean's
  float32 rounding, so a port at the single-precision level cannot do much
  better. Should the coordinator keep the tolerance (it held) or record
  that it is close to the floor of what float32 FITS can resolve?
- WSClean's Gaussian beam fit (`BMAJ/BMIN/BPA`) is the only archived
  per-job quantity the core does not produce. Nothing in the family uses
  it; port it only if a later stage needs restored images.
- The core grids in 4 s per job on an idle machine against 27–37 s in
  task C's run `-05` with the same `grid.rs` (`e4ecab1`, unchanged since);
  the gap is attributed to the eight concurrent wave 1 sessions then, not
  measured. WSClean needs 1.4–1.7 s per inversion single-threaded, so the
  core is about 2.5× slower on the inversion; an FFT crate remains the
  obvious performance step (task C's note).
