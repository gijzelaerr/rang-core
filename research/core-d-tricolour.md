# Rang core, wave 1 task D: Tricolour

Task D of [core-parallel-plan.md](core-parallel-plan.md), started 2026-10-29
on branch `core/d-tricolour` from `9e12326`. Status: **licence decided
(section 1); protocol frozen in `5ff1e89` before any port code;
implemented; measured: the frozen run `-01` failed criteria 1–3 through one
porting error, and after that fix run `-02` passes all five gated criteria
on all four controls, flag for flag** (section 6). Archive:
[results/core-d-tricolour.json](results/core-d-tricolour.json). A
reimplementation; under AGENTS.md not a scientific contribution.

## 1. Licence decision (decided 2026-10-29)

**Question.** Rang is GPL-3.0-or-later. Is Tricolour (and Crystalball, which
shares the question) GPL-2.0-only, which would be incompatible, or something
rang may port from?

**What was inspected.** The exact Tricolour the archived controls ran:
version 0.2.1 from the `rang-flagging-parallel:local` image
(`/opt/tricolour`, recorded in `research/results/gain-tv-caracal.json`
under `config.engine`), installed from the PyPI wheel
`tricolour-0.2.1-py3-none-any.whl` (SHA256 `7dd8dfcf…1c63b`). The installed
package, the wheel and sdist from PyPI (hashes verified against the PyPI
JSON), and the files at the GitHub tag `0.2.1` and on `master` were copied
as data into `outputs/core-d-20261029-01/` (`SHA256SUMS` there lists all
110 files). Nothing from that directory is imported or executed.

**Evidence, Tricolour 0.2.1.**

| Source | Says | Where |
| --- | --- | --- |
| Wheel metadata (installed) | `License: GPLv2`; classifier `License :: Other/Proprietary License` | `tricolour-0.2.1.dist-info/METADATA` lines 5 and 10 |
| `pyproject.toml` (sdist, tag `0.2.1`, `master`) | `license = "GPLv2"` | line 10 |
| `LICENSE` (wheel `dist-info/licenses/LICENSE`, sdist, tag `0.2.1`, `master`) | BSD-3-Clause text, "Copyright (c) 2019, National Research Foundation (South African Radio Astronomy Observatory)"; 28 lines, SHA256 `fd367a7d…c355`, byte-identical in all four places | whole file |
| Source files (all 13 modules, tests, `conf`, `data`) | no licence header or notice of any kind; no GPL text anywhere in the sdist, wheel or fetched repository files | `grep -ri licen\|gpl\|copyright` over `tricolour/` matches nothing |
| Git history of `LICENSE` | one commit: added 2020-01-06 in `2a6d8c8f7c` "Prepare for 0.1.7 release (#64)", unchanged since | GitHub commits API, `path=LICENSE` |
| `setup.py` 0.1.7 – 0.1.8.2 (2020–2023) | no `license=` argument and no licence classifier; PyPI metadata for 0.1.8 has `license: ''` | `setup.py` lines 27–37 at tag `0.1.8.2` |
| First appearance of "GPLv2" | `pyproject.toml` of `98ab13af6a` "Prepare 0.2.0 (#94)", 2026-01-22: the setuptools-to-Poetry migration. Poetry emits `License :: Other/Proprietary License` for a licence string it cannot map, which explains the classifier | GitHub commits API, `path=pyproject.toml` |
| Provenance of the kernel | `tricolour/flagging.py` docstring ("Library to contain 2d RFI flagging routines and other RFI related functions."), `MAD_NORMAL`, and the functions `_time_median`, `_median_abs`, `_median_abs_axis0`, `_linearly_interpolate_nans`, `_box_gaussian_filter1d`, `_box_gaussian_filter`, `masked_gaussian_filter`, `_get_background2d`, `_convolve_flags`, `_sum_threshold1d`, `_sum_threshold`, `_get_flags_impl`, `_combine_flags`, `_average_freq`, `_unaverage_freq`, `_get_baseline_flags`, `SumThresholdFlagger` are the same inventory as katsdpsigproc `src/katsdpsigproc/rfi/twodflag.py`, which carries a BSD-3-Clause header ("Copyright (c) 2014-2020, 2025, National Research Foundation (SARAO)", lines 1–15) and whose repository `LICENSE` is BSD-3-Clause. Tricolour's own README calls it "A variant of the Science Data Processing flagging code" | `outputs/core-d-20261029-01/github/katsdpsigproc/` |

**Evidence, Crystalball 0.4.3** (the version in `rang-flagging-sky:local`,
`/opt/sky`): `pyproject.toml` line 6 `license = "GPLv2"`; `LICENSE` is the
full GPL version 2 text (340 lines, SHA256 `c03cea02…8cad`); no per-file
headers and no "or any later version" statement anywhere. The conservative
reading is **GPL-2.0-only**.

**Decision.**

1. *Tricolour 0.2.1 is treated as BSD-3-Clause and therefore compatible
   with GPL-3.0-or-later.* The only licence text the copyright holder
   distributes with the work, in every form of it (repository, sdist,
   wheel), is the BSD-3-Clause `LICENSE`, present since the first release
   with a licence at all. The string `GPLv2` is a metadata field introduced
   in 2026 by a packaging migration, has never been accompanied by GPL text,
   a notice or a header, and is contradicted by the licence file the same
   metadata points at (`License-File: LICENSE`). Independently of that,
   the SumThreshold kernel itself is available under an unambiguous
   BSD-3-Clause header from katsdpsigproc. The port therefore proceeds,
   keeping the Tricolour copyright notice and the BSD conditions in the
   Rust module and beside the copied static-mask data (`core/data/`), as
   `core/src/predict.rs` does for codex-africanus and `core/src/solve.rs`
   for QuartiCal.
2. *Residual risk, recorded.* If SARAO states that the `GPLv2` string is the
   intended licence, Tricolour-specific code (`flag_nans_and_zeros`,
   `flag_autos`, `apply_static_mask`, `uvcontsub_flagger`, `stokes.py`, the
   strategy executor and the static masks; about 400 lines) would have to be
   re-derived from the documented behaviour rather than ported. The kernel
   (about 800 lines) is covered by katsdpsigproc. Resolving the
   contradiction upstream is an item for `upstream-notes.md` (coordinator
   section below); nothing is sent without the user's go-ahead.
3. *Crystalball is GPL-2.0-only and is not ported.* Rang only runs it as a
   separate process in its own container as an imaging-sky oracle, which
   the GPL permits; the component predictor rang ported in phase 3c-a is
   codex-africanus (BSD), not Crystalball. No Crystalball code may be
   copied into the core.

## 2. What is ported

Tricolour 0.2.1 as the archived controls ran it: the command in
`outputs/tv-caracal-wsl-20261029-01/native/*/command.json`
(`--flagging-strategy polarisation --data-column DATA --window-backend
numpy --nworkers 1`, no `--ignore-flags`, no model subtraction), with the two
pinned CARACAL strategies
`mk_rfi_flagging_calibrator_fields_firstpass.yaml` (12 steps) and
`calibrator_mild_flagging.yaml` (10 steps) from
`outputs/caracal-strategy-inputs-8f7bb363` (hashes in
`results/caracal-strategies.json`). Semantics come from reading
`apps/tricolour/app.py`, `apps/tricolour/strat_executor.py`, `stokes.py`,
`mask.py`, `packing.py`, `flagging.py` and `dask_wrappers.py` of the
installed package:

- **Grouping and windows.** Rows are grouped by field, data description and
  scan (one group here: field J1939-6342, scan 9, 140 rows), unique times
  are sorted, unique baselines are the sorted `(ANTENNA1, ANTENNA2)` pairs,
  and visibilities and flags are packed into `(baseline, correlation, time,
  channel)` windows whose defaults are NaN and flagged.
- **Polarisation mode.** With correlations XX, XY, YX, YY the flagger sees
  one "correlation": $\sqrt{|Q|^2+|U|^2+|V|^2}$ with
  $Q=\tfrac12(XX-YY)$, $U=\tfrac12(XY+YX)$, $V=-\tfrac{i}{2}(XY-YX)$,
  computed in double precision from the single-precision data and stored as
  complex64 with zero imaginary part; the input flag is the OR over
  correlations. On output every correlation receives the window flag.
- **Steps.** `flag_nans_zeros` (flag where the intensity is 0 or NaN, ORed
  into the running flags),
  `apply_static_mask` (both shipped masks, `4k_lband_meerkat` and
  `4k_uhfband_meerkat`, are loaded; a channel is masked when a mask
  frequency falls in $[\nu-\Delta\nu/2,\nu+\Delta\nu/2)$; the `uvrange`
  selects baselines by $\tfrac12|\mathbf p_1-\mathbf p_2|^2$ from the
  ECEF antenna positions, as the source does), `sum_threshold` (the
  katsdpsigproc kernel: frequency averaging, time-median spectrum,
  iterative masked box-Gaussian background with MAD rejection, SumThreshold
  along frequency then time then frequency with $\rho^{\log_2 w}$ threshold
  scaling, time and frequency smearing, row/column fraction cuts, major
  iterations; the step returns only the last major iteration's flags, which
  the executor ORs into the running flags), `uvcontsub_flagger` (per
  baseline: time-mean of the unflagged intensity, a 4096-point FFT keeping
  the first `taylor_degrees` bins as a smooth fit, residual MAD clipping at
  `sigma`, with the running flags discarded before `or_original_from_cycle`),
  `flag_autos`, and `combine_with_input_flags` (OR with the window flags as
  packed). The executor's accumulation rules (`|=` for `sum_threshold`,
  `flag_autos` and `or` masks; replacement for `uvcontsub_flagger`) are
  kept exactly.
- **Numeric types.** The kernel's single-precision data, double-precision
  accumulators and the Numba promotion rules (a float32 array divided by a
  float64 scalar is float64; `(a + b) / 2` of two float32 medians rounds the
  sum in float32) are followed where they can change a comparison. The one
  place that cannot be followed bit for bit is the `uvcontsub_flagger` FFT:
  NumPy 2.0 computes it in complex64 with pocketfft, whose rounding sequence
  depends on its radix plan; the port computes the same low-pass fit in
  double precision and rounds to complex64. A flag flips only where the
  float32 residual lies within a few units in the last place of the
  threshold; the protocol records any such differences rather than hiding
  them.

Not ported: the `zarr-disk` window backend, `total_power` and `standard`
flagging strategies, model-column subtraction, field and scan selection
beyond one group, `unflag`, dilation of masks, the window statistics
summary and the Measurement Set writer. The Python wrapper reads arrays;
the Measurement Set edge stays in python-casacore inside the pinned
container, as in earlier phases.

## 3. Protocol (frozen in this commit, before any port code)

**Precondition (measured before freezing).** The comparator
`examples/compare_core_flags.py archive-host` compared the archived control
records in `results/gain-tv-caracal.json` (run of 2026-09-23) with the host
reproduction `outputs/tv-caracal-wsl-20261029-01` (run of 2026-10-29): 68
fields (exit codes, audits, added counts and fractions, valid-gain
fractions, invalid-prediction counts, guard outcomes exactly; TV, scale and
objectives to 1e-9 relative) agree for all four controls and the baseline,
FLAG_ROW is unchanged by every native run, and every after-native snapshot
is uniform across correlations. Result in
`outputs/core-d-20261029-01/compare-archive-host/result.json` (0.22 s).
The host snapshots `before-native.npz`, `after-native.npz` and
`frozen-proposal.npz` under `outputs/tv-caracal-wsl-20261029-01/native/`
are therefore the oracle for the port.

**Oracle step.** `examples/oracle_tricolour.py` runs once in
`rang-flagging-parallel:local` with `/opt/tricolour/bin/python` (Tricolour
0.2.1, Numba 0.60.0, NumPy 2.0.2, python-casacore 3.8.1) into a fresh
`outputs/core-d-oracle-<date>-NN`. For each of the four controls it reads
the control's `diagnostic.ms` read-only and `before-native.npz`, exports the
arrays the port needs (`DATA`, `ANTENNA1`, `ANTENNA2`, `TIME`, the input
flags, antenna positions, channel frequencies and widths, correlation
types), and then calls the unmodified `tricolour.stokes` and
`tricolour.flagging` NumPy functions step by step exactly as
`strat_executor.py` chains them, saving the polarised intensity window, the
window flags after every step, and the final per-row flags. It checks its
own final flags against `after-native.npz`; a mismatch means the protocol's
reading of `app.py` is wrong and is recorded as such (the oracle is then
only the per-step reference). It records hashes of everything it read,
Tricolour's per-step wall time (including JIT), and the versions. The port
is compared only after this step has run.

**Port run.** `examples/run_core_flags.py <oracle-dir> outputs/<fresh>`
runs the Rust port on the exported arrays for each control and writes
`flags.npz` (FLAG as `(row, chan, corr)` and the training proposal `added`
from `flagging_caracal.training_proposal`), `intensity.npz`,
`stages.npz`, per-control timings and a receipt with the same host hashes.
`examples/compare_core_flags.py run` then applies the criteria.

**Acceptance criteria.**

1. **Final flags, exact.** For every control, the port's FLAG equals
   `after-native.npz` FLAG at all 140 × 4096 × 4 elements. FLAG_ROW is not
   produced (Tricolour does not write it).
2. **Training proposal.** The proposal computed from the port's flags
   equals `frozen-proposal.npz` and its count equals the archive's
   `added_count` (26,692 for the first-pass operational control).
3. **Stages, exact.** Every per-step window flag array equals the oracle's.
4. **Polarised intensity, bit-equal.** The port's complex64 intensity window
   equals the oracle's bit for bit (NaN patterns included).
5. **No side effects.** SHA256 of the four `diagnostic.ms` trees and the
   `before-native.npz` and `after-native.npz` snapshots are the same before
   the oracle step and after the port run; the tracked tree is clean apart
   from this task's files.
6. **Cost (reported, not gated).** Port wall time per control; the oracle's
   per-step and total wall time (which includes Numba compilation); and the
   archived native 301.7–302.9 s per control, of which 300 s is the
   non-TTY `ProgressBar(dt=300)` artefact already recorded in
   `flagging-caracal.md`.

The task is reported as passed only if criteria 1–5 pass as frozen. Any
failure is recorded with its numbers, the stage at which the first
difference appears, and whether the differing elements lie within float32
rounding of a threshold; any change after a failure is a labelled post-hoc
step with its own run directory.

## 4. What was built

- `core/src/sumthreshold.rs` (about 1,100 lines with tests): the kernels of
  section 2 and the strategy executor, over windows of one correlation
  product per baseline. Eight unit tests cover the float32 median rounding,
  the boxcar filter, the radius truncation, the `linspace` chunk ends, flag
  smearing, the low-pass identity, the Stokes map and the executor's
  accumulation rules.
- `core/src/ffi_flag.rs`: one C ABI entry, `rang_core_flag_rows`, taking
  rows, flags, baseline and time indices, geometry, the mask frequencies and
  a flat step table (`STEP_WIDTH = 32` doubles per step), and writing the
  per-row flags, the polarised-intensity window and the per-step window
  flags.
- `python/rangtoy/core_flag.py`: strategy YAML reader (the subset CARACAL's
  files use; PyYAML is not in the venv), static-mask loader, step encoder
  with Tricolour's defaults, Tricolour's baseline order, and `flag_rows`.
  `core/data/` holds the two static masks and Tricolour's licence file.
- `examples/oracle_tricolour.py` (container), `examples/run_core_flags.py`,
  `examples/compare_core_flags.py`, `tests/test_core_flag.py` (nine tests,
  synthetic data and the committed `caracal-strategies.json`).

## 5. Timings

Host load average was 55–74 on 16 cores throughout (seven sibling sessions
building and testing), so wall times of the port are three to five times
its CPU time; CPU seconds are given where measured.

| Date | Tool / stage | Input | Wall | Notes |
| --- | --- | --- | ---: | --- |
| 2026-10-29 | PyPI JSON for tricolour 0.2.1 and crystalball 0.4.3 | 2 requests | 1.0 s | |
| 2026-10-29 | curl sdist + wheel of tricolour 0.2.1, extract | 2 files | 1.7 s | hashes equal PyPI |
| 2026-10-29 | `uv venv` + `uv pip install -e .[pointing,beam,test] ruff` | worktree | 2 s | cached wheels; `python3 -m venv` fails on this host (no `ensurepip` for Python 3.14), so `uv venv` was used with the same public index |
| 2026-10-29 | `cargo +1.93 build --release` core and root | worktree | 2 s + 1 s | |
| 2026-10-29 | `docker run` + python-casacore facts script in `rang-flagging-parallel:local` | 4 diagnostic MSs | 2.0 s | |
| 2026-10-29 | `compare_core_flags.py archive-host` | 2 JSON + 8 npz | 0.22 s | pass |
| 2026-10-29 | oracle step, `oracle_tricolour.py` in the container | 4 controls | 123.9 s (121.2 s in Python) | control 0: 116.5 s, of which Numba compilation of `sum_threshold_flagger` 74.9 s at step 2 and 39.2 s again at step 8 (the narrow step passes `spike_width_time: 2`, an int, so Numba specialises a second time); controls 1–3 warm: 2.2 s, 1.2 s, 1.3 s |
| 2026-10-29 | port run `-01` (`run_core_flags.py`) | 4 controls | 40.8 s | failed criteria 1–3 |
| 2026-10-29 | port run `-02` | 4 controls | 60.9 s (19.0, 17.4, 11.3, 10.5 s) | pass; load 68 |
| 2026-10-29 | port run `-03` after speedups | 4 controls | 50.7 s (12.7, 15.5, 10.8, 9.0 s) | pass; load 59–65 |
| 2026-10-29 | `compare_core_flags.py run` | 3 runs | 1.9 s each | |
| 2026-10-29 | port, control 0 first-pass strategy, CPU | 140 rows × 4096 ch | 4.16 s CPU (18.4 s wall) | step 2 `sum_threshold` 2.40 s CPU, `uvcontsub` steps 0.13 s and 0.17 s CPU |
| 2026-10-29 | Tricolour 0.2.1 warm kernels, same inputs, in the container | same | step 2: 1.19 s CPU; `uvcontsub` step 3: 0.11 s CPU | first call of step 2: 73.9 s CPU (JIT) |
| 2026-10-29 | `tools/check-all.sh` (pytest 677 tests) | repo | 2119 s (pytest 2092 s) | PASS; load 60–74, against 175–986 s for the suite on a quiet host |

## 6. Measured result (2026-10-29)

**Oracle step** (`outputs/core-d-oracle-20261029-01/run`, receipt there):
for all four controls the step-by-step NumPy chain of the unmodified
Tricolour functions reproduces `after-native.npz` exactly, so the reading
of `app.py` in section 2 is confirmed and the per-step window flags are a
valid reference. Host inputs unchanged (hashes recorded).

**Run `-01`, frozen, failed** (`outputs/core-d-20261029-02`, comparator
`outputs/core-d-compare-20261029-01`). Criterion 4 (polarised intensity
bit-equal) and 5 (no side effects) passed; criteria 1–3 failed on every
control: 34,776, 1,188, 14,232 and 7,640 final-flag differences out of
2,293,760; proposals 26,736 against 26,692 and so on; the first stage,
`00-flag_nans_zeros`, already differed by 268,778 window elements. Cause:
the port replaced the running flags with the zero-or-NaN flags, whereas
`flagging.py` line 59 ORs the input flags in (`flag = flag or
flag_windows[...] != 0`). A porting error, found by criterion 3 at the
first stage.

**Run `-02`, post-hoc fix, passed** (`outputs/core-d-20261029-03`,
`outputs/core-d-compare-20261029-02`). The executor now ORs the
`flag_nans_zeros` result into the running flags; no criterion changed.
All five criteria pass on all four controls: final flags identical at all
2,293,760 elements each (fractions 0.80641, 0.91789, 0.71847, 0.87272);
training proposals equal `frozen-proposal.npz` with counts 26,692, 26,637,
662 and 735, equal to the archive; every one of the 44 per-step window
arrays identical to the oracle's; intensity windows bit-equal; host inputs
unchanged. The `uvcontsub_flagger` double-precision fit therefore produced
no flag different from Tricolour's complex64 pocketfft path on these data.

**Run `-03`, post-hoc speedups, passed** (`outputs/core-d-20261029-04`,
`outputs/core-d-compare-20261029-03`). Four result-preserving changes
(time-axis box filter in column chunks of 256 as Tricolour does, median by
selection instead of sorting, incremental twiddle index in the low-pass
fit, binary search in the static mask) give the same flags under all five
criteria.

**Cost.** On control 0's first-pass strategy the port spends 4.16 s CPU in
total, 2.40 s of it in the heaviest `sum_threshold` step, against 1.19 s
CPU for Tricolour's warm Numba kernel on the same step (the port's
`uvcontsub` matches Tricolour's 0.11 s). The port is therefore about twice
the kernel cost of warm Numba, with no compilation: Tricolour's first call
of that kernel costs 73.9 s CPU, and the archived native runs took 302 s
per control, of which 300 s is the non-TTY progress bar. Where the
remaining factor of two goes was not resolved; `perf` under this load gave
no usable symbol attribution. Not optimised further.

**Checks.** `cargo +1.93 clippy -D warnings`, `cargo fmt --check`, the
module's unit tests, `ruff check` and `ruff format --check` on the new
files, and `tests/test_core_flag.py` pass; `bash tools/check-all.sh` was
run once before the final commit with the two `pub mod` lines present in
the working tree: overall PASS, 677 tests in 2092 s (log in
`outputs/core-d-20261029-01/check-all.log`).

## 7. For the coordinator

- `core/src/lib.rs`: add `pub mod ffi_flag;` and `pub mod sumthreshold;`
  (alphabetical among the existing lines). The branch deliberately leaves
  `lib.rs` untouched, so on the branch alone the new module is not compiled
  and `tests/test_core_flag.py` fails on the missing symbol; the checks in
  section 6 were run with the lines present.
- `README.md`: a line that the Tricolour strategies run on the core
  (`rangtoy.core_flag`, `research/core-d-tricolour.md`) and that
  `core/data/` carries Tricolour's static masks under the BSD notice.
- `STATE.md`, new top entry: "Core task D, 2026-10-29 (implemented;
  measured): Tricolour 0.2.1 treated as BSD-3-Clause (LICENSE file; the
  `GPLv2` metadata string is unaccompanied), Crystalball GPL-2.0-only and
  not ported. `core/src/sumthreshold.rs` reproduces the four archived
  CARACAL controls flag for flag (run `-02`, after one post-hoc fix of the
  `flag_nans_zeros` accumulation); 4.2 s CPU per first-pass strategy
  against 1.2 s warm Numba plus 74 s compilation. Archive
  `results/core-d-tricolour.json`."
- `upstream-notes.md`, Tricolour 0.2.1 section (observed, not raised):
  (1) the wheel declares `License: GPLv2` but ships only a BSD-3-Clause
  `LICENSE`; the string dates from the Poetry migration in PR #94; worth a
  question to the maintainers. Crystalball 0.4.3 has the same metadata
  string with a real GPL-2 text. (2) Of the 302 s per archived native run,
  300 s is `ProgressBar(dt=300)` (already noted) and about 114 s of CPU is
  Numba compilation: 75 s for `sum_threshold_flagger` and 39 s again for the
  strategy step whose YAML gives `spike_width_time: 2` as an integer, which
  makes Numba compile a second specialisation; the kernels themselves take
  about 1.2 s warm. A persistent `NUMBA_CACHE_DIR` or floats in the shipped
  YAML would remove most of it. (3) `nanmean` of an all-flagged channel
  logs "Mean of empty slice" on every call.
- `tool-timings.md`: the rows of section 5.
- `core-parallel-plan.md`: task D done; wave 2 may use `core_flag.flag_rows`
  for a core-native flagging recipe.
