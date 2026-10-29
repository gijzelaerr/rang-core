# Rang core, wave 2 task I: the imaging track replayed on the core

Protocol frozen 2026-10-29 on branch `core/i-imaging-replay` (from origin/main
`3e64bab`), before any driver code was written. Status: **proposed; protocol
frozen, comparator precondition measured; driver not yet written**. Task I of
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
