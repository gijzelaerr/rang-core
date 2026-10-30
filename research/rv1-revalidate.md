# RV1: re-validating the Tricolour and QuartiCal ports against the next upstream versions

Task RV1 of [big-plan.md](big-plan.md) (the "Follow-up: Tricolour 0.5.0"
bullet), started 2026-10-30 on branch `rv1-revalidate` from `origin/main`
`3b875e0`. Protocol frozen in `4a23efc` before any RV1 script was written or
any upstream code was run on the archived inputs. No port change is part of
this task.

**Status (2026-10-30): implemented; measured.** Neither Tricolour 0.5.0 nor
QuartiCal 0.2.8 is released, so both comparisons ran on the release branches
at recorded commits.

- **Tricolour `0.5.0-dev` `367ff54`: identical to 0.2.1** on the four task D
  controls. Every strategy step matches (44 window arrays), and so do the
  polarised intensity (bit for bit) and the final FLAG. That holds for the
  kernel chain and for the end-to-end `tricolour` CLI, which agrees with
  `after-native.npz` at all 4 × 2,293,760 elements. The core port therefore
  equals 0.5.0-dev on these inputs: task D's five criteria pass against it.
- **One latent difference.** `apply_static_mask` `uvrange` now selects by
  |uvw| ≤ 550 m. 0.2.1 and the port select by 0.5·|Δp|² ≤ 550², which reaches
  778 m. The controls have no baseline longer than 74 m, so this cannot act
  on them; on the whole array it covers 165 of 1540 baselines (post-hoc).
- **PR #112 as merged:** one kernel signature. **PR #114 head:** flags
  identical in every stage, but two signatures, because its branch predates
  #112. It merges onto `0.5.0-dev` with a conflict in
  `tests/test_flagging.py` only.
- **QuartiCal `v0.2.8-dev` `d54c46b`: does not reproduce 0.2.7** under the
  archived tolerances. The #452 fix moves the 50-iteration iterate: gain
  entries change by up to 1.7e-3 (fixture) and 2.8e-4 (LUNO), and baseline
  products by up to 1.1e-7 and 9.7e-5, against a 1e-6 gate.
- **The core matches 0.2.8-dev with the L5 option.** With
  `RANG_SOLVE_OPTIONS=qp_weights=transposed` it reproduces 0.2.8-dev with
  `G.referenced=false` to 1.2e-15 / 3.3e-16 in entries, with identical flags,
  50 iterations and identical converged fractions.
- **#440 referencing.** By default 0.2.8-dev now references `complex` to the
  `solver.reference_antenna=0` in rang's archived command. That is a pure
  gauge change: products equal the unreferenced run to 4.6e-16.
- **Precondition.** 0.2.7 rerun in a fresh venv reproduces the archived
  oracle to 4e-16.
- **Process.** Three post-hoc fixes to RV1's own scripts, and no port change
  (section 6). Archive:
  [results/rv1-revalidate.json](results/rv1-revalidate.json).

## 1. Facts (established 2026-10-30, before freezing)

Sources: `https://pypi.org/pypi/tricolour/json`,
`https://pypi.org/pypi/quartical/json`, the GitHub REST API for
`ratt-ru/tricolour` and `ratt-ru/QuartiCal` (tags, releases, branches,
issues, pulls, comments), and full clones of both repositories (read as
data; only their own test suites are run, in their own venvs).

**Neither release exists today.**

| | Tricolour | QuartiCal |
| --- | --- | --- |
| Latest PyPI release | 0.2.1 (2026-04-01), `requires_python >=3.10,<3.13` | 0.2.7 (2026-06-12), `requires_python >=3.10,<3.14` |
| Latest tag / GitHub release | `0.2.1` → `c4f96849275db878f8b63bacabf60e4f84eef637` | `v0.2.7` → `d01487e3091aab03beca71128858e724b087d6e3` |
| Next version | 0.5.0: not on PyPI, no tag, no release | 0.2.8: not on PyPI, no tag, no release |
| Release branch, head used here | `0.5.0-dev` → `367ff54d700c134b2ea167b69c950d07873d36cb` (2026-10-30 09:45 UTC, the #112 merge); 34 commits after the 0.2.0 merge base `d9a84c4` | `v0.2.8-dev` → `d54c46b99dc059df678e8e2866883e3440073c2d` (2026-10-30 11:53 UTC, the #456 merge); 16 commits after `v0.2.7` |
| Branch's Python support | `requires-python >=3.11`; classifiers 3.11, 3.12, 3.13; `numpy>=2.4.2`, `numba>=0.64.0`, `ray[serve]`, `xarray-ms>=0.4.0a11,<0.5` (extra `msv2`) | `requires-python >=3.10,<3.14` (version string still `0.2.7`) |
| Licence on the branch | `license = "BSD-3-Clause"` (settles task D's question as rang assumed) | MIT, unchanged |
| Version string reported by the build | `0.0.0` (placeholder in `pyproject.toml`) | `0.2.7` |

Because the version strings do not identify these builds, every RV1
receipt records the commit from the venv's `direct_url.json`.

**Rang's upstream items** (state at 2026-10-30 ~14:00 UTC):

| Item | State | Note |
| --- | --- | --- |
| tricolour#110 (non-TTY ProgressBar) | open | sjperkins: 0.5.0 "should be released soon"; he and bennahugo "are satisfied that it provides the same results as main branch"; PR #108 "still remains to be merged" |
| tricolour#111 (integer `spike_width_time` recompiles) | open | fixed by #112 on `0.5.0-dev` (non-default base, so the issue did not auto-close) |
| tricolour#112 (float casts) | **merged** 2026-10-30 09:45 UTC into `0.5.0-dev`, merge commit `367ff54` (head `7f4d0cf`) | |
| tricolour#113 (rows as lanes) | open | |
| tricolour#114 (rows as lanes, PR) | open, head `gijzelaerr/tricolour@2f476ad1a32e61d140f42cf243abb270eb9ed96c`, base `367ff54` | not merged |
| tricolour#108 (progress dashboard, draft) | open, base `0.5.0-dev` | maintainer: to be merged before the release, so `367ff54` may not be the released 0.5.0 |
| QuartiCal#452 (qp JHJ weights) | open | JSKenyon: "Fixed in #456. Could you please try `v0.2.8-dev`?"; the user replied with a test of `d54c46b` |
| QuartiCal#456 (the fix) | **merged** 2026-10-30 11:53 UTC into `v0.2.8-dev`, `d54c46b` | transposes the weights for the ANTENNA2 side in the shared solver loop (all terms) |
| QuartiCal#453 (HISTORY row) | open | maintainer will look at it |
| QuartiCal#455 (convergence cap) | open, no comment | |

**What changed upstream that can touch rang's comparisons** (read from the
branches before freezing; AST comparison of the kernels, docstrings and
formatting ignored):

- Tricolour `0.5.0-dev` against 0.2.1. The package moved to
  `src/tricolour/core/kernels/{flagging,stokes,mask}.py`; the executor is
  `Flagger.flag` in `core/application/implementation.py` (Ray Serve, data
  through MSv4 / `xarray-ms`, work items of 100 times × 16 baselines × all
  channels by default). Kernel bodies identical to 0.2.1 except:
  `sum_threshold_flagger` and `SumThresholdFlagger.__init__` cast seven
  parameters to float (#112); `flag_autos` takes `ubl` directly;
  `uvcontsub_flagger` casts flags to bool; `polarised_intensity` works on
  the `(baseline, corr, time, chan)` layout; `load_mask` accepts dtype
  subtypes; and **`apply_static_mask` selects by `|uvw(baseline, time)|`
  in metres within `[lo, hi]`, where 0.2.1 (and rang's port) selects whole
  baselines by `0.5·|Δp_ECEF|² ∈ [lo², hi²]`**, i.e. `|Δp| ≤ √2·hi`
  (778 m for CARACal's `0~550`). The executor's accumulation rules are the
  same; after the strategies every correlation is flagged if any is (as in
  0.2.1 for the polarisation mode, where there is one product). Every
  other kernel (`_sum_threshold*`, `_box_gaussian_filter*`,
  `_get_background2d`, `flag_nans_and_zeros`, `stokes_corr_map`,
  `MAD_NORMAL`, …) is AST-identical.
- On the four task D controls the uvrange change cannot act: they hold
  stations m000–m003, whose baselines are 29–74 m (`|uvw|` ≤ 74.2 m), so
  `0~550` selects every baseline in both versions. **Prediction (frozen):
  no flag difference from the uvrange change on these inputs.** It is a
  real difference for array data with baselines between 550 m and 778 m.
- Environment: the archived 0.2.1 oracle ran NumPy 2.0.2 and Numba 0.60.0;
  `0.5.0-dev` needs NumPy ≥ 2.4.2 (resolved 2.5.4) and Numba ≥ 0.64
  (0.68.1).
- QuartiCal `v0.2.8-dev` against 0.2.7: #456 (the #452 fix, all terms);
  #430 (all terms on one shared solver loop); **#440 (`b1a0cb0`): a new
  per-term `referenced` option, default `true`, now applied to the full
  `complex` term**, which pins the reference antenna's diagonal phases;
  rang's archived command passes `solver.reference_antenna=0`, which 0.2.7
  ignored for `complex` and 0.2.8-dev applies; #427 (flagged parameters
  filled with the identity); #443 (reference antenna by name); #441, #447
  (beam and parallactic angles about the pointing; not used here);
  #448, #451, #368, #428, #429, #437 (loading, FEED, DDID, jhj sizing).

## 2. Inputs (archived, read-only)

- **Tricolour (task D).** The four controls of
  `outputs/tv-caracal-wsl-20261029-01/native/strategy-0{0,1}-{operational,holdout_masked}`
  (`diagnostic.ms`, `before-native.npz`, `after-native.npz`,
  `frozen-proposal.npz`; the host run's `state.npz`), the CARACal
  strategies `mk_rfi_flagging_calibrator_fields_firstpass.yaml` and
  `calibrator_mild_flagging.yaml` from
  `outputs/caracal-strategy-inputs-8f7bb363` (hashes in
  `results/caracal-strategies.json`), and the archived 0.2.1 oracle
  `outputs/core-d-oracle-20261029-01/run` (per-stage window flags, final
  flags, intensity, exported arrays). Measured before freezing: every
  `diagnostic.ms` FLAG equals `after-native.npz`, not `before-native.npz`,
  so any run that reads flags from an MS must first write
  `before-native.npz` FLAG into a **copy**.
- **QuartiCal (phase 2 / task F / task K).** Fixture clean case
  `outputs/tv-response-wsl-20261029-01/clean` (`work.ms`, `state.npz`,
  `backups/clean-t2-f32-solve.npz`, the archived 0.2.7 solve
  `trials/clean-t2-f32/{command.json,diagnostics.npz,gains.qc,metrics.json}`);
  LUNO four-station slice `outputs/luno-solve-20261029-02` (`work.ms`,
  the archived 0.2.7 solve `solve/{command.json,gains.npy,gain_flags.npy,summary.json}`)
  and its exported arrays `outputs/core-phase2-inputs-20261029-01/arrays.npz`.
  Measured before freezing: the fixture `work.ms` DATA, RANG_MODEL_DATA and
  WEIGHT_SPECTRUM equal `state.npz`, but its FLAG/FLAG_ROW are the
  workflow's later state, not the solve's; the LUNO `work.ms` columns all
  equal `arrays.npz`. Copies get the solve flags written in.

Nothing under these paths is written. Every RV1 output goes to a fresh
`outputs/rv1-20261030-NN`.

## 3. Environments (frozen)

uv venvs from public PyPI under `~/Build/tmp/20261030-rv1/` (no
container: the archived `rang-flagging*` images are no longer on the host):

| venv | Python | Package | Resolved key versions |
| --- | --- | --- | --- |
| `venv-tric021` | 3.12 | `tricolour==0.2.1` | NumPy 2.0.2, Numba 0.60.0, dask-ms 0.2.32, python-casacore 3.8.1 (the archived oracle's NumPy and Numba) |
| `venv-tric050` | 3.13 | `tricolour[msv2] @ git+…/ratt-ru/tricolour@367ff54` | NumPy 2.5.4, Numba 0.68.1, ray 2.59.0, xarray-ms 0.4.0a12, arcae 0.4.0a16, python-casacore 3.8.1 |
| `venv-tric114` | 3.13 | `tricolour[msv2] @ git+…/gijzelaerr/tricolour@2f476ad` (PR #114 head) | as `venv-tric050` |
| `venv-qc027` | 3.13 | `quartical==0.2.7` | NumPy 2.5.4, Numba 0.68.1 (archive: 0.67.0), dask-ms 0.2.32, codex-africanus 0.4.4 |
| `venv-qc028` | 3.13 | `quartical @ git+…/ratt-ru/QuartiCal@d54c46b` | as `venv-qc027` |

The core is this worktree's `.venv` (Python 3.14, `rang._core` built from
`3b875e0`). Every process runs with `OPENBLAS_NUM_THREADS=1
RAYON_NUM_THREADS=4 NUMBA_NUM_THREADS=4` and a fresh `NUMBA_CACHE_DIR` per
upstream version under the run directory.

## 4. Protocol (frozen)

### (a) Tricolour

- **T0, environment precondition.** `examples/oracle_tricolour.py`
  (unchanged) in `venv-tric021` on the four controls into a fresh
  directory. Gate: every stage array, the intensity window (bit for bit)
  and the final flags equal the archived 0.2.1 oracle's, and the final
  flags equal `after-native.npz`. This shows the venv reproduces the
  archived container, so the archived oracle stays the 0.2.1 reference.
- **T1, the 0.5.0-dev kernel chain (primary).** `examples/oracle_tricolour_050.py
  oracle` in `venv-tric050`: reads each control's `diagnostic.ms`
  read-only (DATA, ANTENNA1/2, TIME, UVW, FLAG_ROW, the subtables) and
  `before-native.npz` FLAG, packs windows with 0.2.1's sorted `ubl` and
  `time_inv` (so stage arrays are comparable element for element; the
  kernels are per baseline, and `flag_autos` takes the same `ubl`), packs
  UVW to `(baseline, time, 3)` the same way, loads the masks with
  `tricolour.core.kernels.mask.load_masks(None)`, and runs the unmodified
  `0.5.0-dev` kernels exactly as `Flagger.flag` chains them for the
  `polarisation` strategy (including the final any-over-correlation and
  broadcast). It writes the 0.2.1 oracle layout (`receipt.json` with
  `host_hashes`, per control `arrays.npz`, `intensity.npz`, `stages.npz`
  with the `NN-task` names, `final.npz`), plus the commit, versions,
  mask hashes, per-step wall time and the number of compiled signatures
  of every Numba dispatcher in `tricolour.core.kernels.flagging`.
- **T2, the 0.5.0-dev application (end to end).** Each control's
  `diagnostic.ms` is copied into the run directory, `before-native.npz`
  FLAG is written into the copy (FLAG_ROW is unchanged by the native
  runs), and `tricolour <copy> -fs polarisation -c <strategy> -nw 4 -tc 100`
  (`venv-tric050`, defaults otherwise: `-bc 16`, `-dv VISIBILITY`, no
  `--ignore-flags`) runs with a 1800 s timeout per control; FLAG is then
  read back. A hang, crash or timeout is recorded as a frozen failure of
  T2 only.
- **T3, PR #114.** T1's chain in `venv-tric114`. Gate: every stage array,
  the intensity and the final flags bit-identical to T1 (its base is
  `367ff54`, so this is a clean A/B).
- **T4, PR #112 as merged.** From T1's receipt: after both strategies ran
  (each contains an integer `spike_width_time: 2`), the Numba dispatcher
  that `sum_threshold_flagger` calls holds exactly one compiled signature.
  Flag identity of integer and float values is implied by the cast and
  already tested upstream; not re-gated.
- **T5, the core.** A fresh `examples/run_core_flags.py` run on the
  archived 0.2.1 oracle's exported arrays (the current tree, not task D's
  run `-04`), then `examples/compare_core_flags.py run` twice: against the
  archived 0.2.1 oracle (task D's five criteria, as a regression check) and
  against T1's directory (the same five criteria with 0.5.0-dev's stages
  and intensity in place of 0.2.1's; criteria 1–2 still compare with
  `after-native.npz` and `frozen-proposal.npz`, which is what "0.5.0
  agrees with 0.2.1" means).
- **Comparison and verdict.** `oracle_tricolour_050.py compare` (worktree
  venv, NumPy only) counts differing elements per control and per stage:
  T1 vs archived 0.2.1 oracle (stages, intensity as uint32 bits, final),
  T1 final vs `after-native.npz`, T2 FLAG vs `after-native.npz` and vs T1
  final, T3 vs T1, T0 vs archived 0.2.1. **Verdict "identical"** if T1
  equals the 0.2.1 oracle in every stage and in the final flags and T2's
  FLAG equals `after-native.npz` on all four controls; otherwise the
  verdict is the list of differences with counts per stage and control,
  explained from the changes in section 1.
- **Conditional diagnostic (labelled, run only if T1 differs from 0.2.1
  in some stage).** To separate the environment from the code, the 0.2.1
  chain is rerun in a copy of `venv-tric021` upgraded to `venv-tric050`'s
  NumPy and Numba (if 0.2.1 installs with them), and the first differing
  stage is located with the elements' distance from the threshold.
- **Dev suite (fact).** `pytest -m "not acceptance"` of the clone at
  `367ff54` in `venv-tric050` (with `pytest`), its own suite only.

### (b) QuartiCal

- **Q0, input copies.** `examples/oracle_quartical_028.py prepare`
  (`venv-qc027`): copies the fixture `work.ms` and the LUNO `work.ms` into
  the run directory; writes `backups/clean-t2-f32-solve.npz` FLAG and
  FLAG_ROW into the fixture copy; checks that the fixture copy's DATA,
  RANG_MODEL_DATA, WEIGHT_SPECTRUM equal `state.npz` and the LUNO copy's
  DATA, MODEL_DATA, WEIGHT_SPECTRUM, FLAG, FLAG_ROW equal `arrays.npz`;
  records hashes of the archived trees before and after.
- **Commands.** The archived `command.json` of each input, verbatim except
  `input_ms.path`, `output.gain_directory`, `output.log_directory` (into
  the run directory). Arms:
  - `qc027`: 0.2.7 (`venv-qc027`), cold cache then warm cache (two runs).
  - `qc028`: `v0.2.8-dev` `d54c46b` (`venv-qc028`), the command verbatim
    (so `complex` is now referenced, #440), cold then warm.
  - `qc028u`: the same plus `G.referenced=false` (0.2.7's unreferenced
    `complex`; isolates #456 and the other changes from #440), one run on
    the warm cache.
  Each run under `/usr/bin/time` (wall, peak RSS), timeout 1800 s; after
  each run FLAG and FLAG_ROW of the copy must be unchanged
  (`output.flags=false`). Gains, gain flags, `conv_iter`, `conv_perc` are
  read from `gains.qc::G` as the archived workflow did.
- **Core arms** (worktree venv, `rang.core.solve_complex` on the same
  arrays the phase 2 validator uses): `core` (`RANG_SOLVE_OPTIONS`
  unset, the archived port) and `core-T`
  (`RANG_SOLVE_OPTIONS=qp_weights=transposed`, the L5 issue 452 fix).
- **Comparator** (`oracle_quartical_028.py compare`, worktree venv,
  `validate_core_phase2.compare_gains`): for each upstream arm against
  the archived 0.2.7 gains, against `qc027` (rerun), against `core` and
  against `core-T`. The tolerances are the archived phase 2 criteria,
  unchanged: (1) gain flags identical; (2) max |Δ| of every complex entry
  on gains unflagged in the reference ≤ 1e-6 and of the baseline products
  `G_p G_q^H` over all unflagged pairs ≤ 1e-6; (3) iterations equal and,
  on LUNO, converged fraction equal to 1e-12 (fixture: reported). For the
  referenced arm `qc028` the raw entries are in another gauge, so only the
  products (gauge-invariant) and criteria 1 and 3 are gated; its entries
  are reported. The observed-pairs product maximum (pairs with training
  data in the interval, L5 amendment 2) is reported as a labelled
  secondary number, never as the gate.
- **Precondition.** `qc027` must pass criteria 1–3 against the archived
  0.2.7 gains on both inputs; otherwise no 0.2.8 difference is attributed
  and the failure is recorded.
- **Expected, frozen as predictions** (not gates): `qc028u` vs archived
  0.2.7 fails criterion 2 on LUNO by about 1e-4 (L5: D_T vs D products
  1.9e-4 all pairs at the 50 cap) and passes on the fixture (L5: 1.5e-7);
  `qc028u` vs `core-T` passes on both near rounding; `qc028` (referenced)
  differs from `qc028u` in products only if referencing inside the loop
  changes the iterate. **Verdicts**: "0.2.8-dev reproduces 0.2.7" if
  `qc028u` passes against the archive; "the core with `qp_weights=transposed`
  reproduces 0.2.8-dev" if `qc028u` passes against `core-T`; each stated
  per input with the numbers.
- **Dev suite (fact).** `testing/tests/gains/test_complex.py` of the
  clone at `d54c46b` in `venv-qc028`, in the background, timeout 1800 s.

### (c) Cost

Wall seconds and peak RSS (`/usr/bin/time -f "%e %M"`) per run for every
arm: T0, T1, T2 (per control), T3, the core flag run (T5), `qc027`,
`qc028` (cold and warm), `qc028u`, `core`, `core-T`; the archived numbers
(0.2.1 oracle 123.9 s; native 302 s per control; QuartiCal 0.2.7 28.3 s
cold, 3.6 s warm; core solve 0.35–0.77 s) quoted beside them. Host load
average recorded before and after each run; numbers are reported, not
gated.

### Rules

- Frozen before running; every failure recorded as it occurred; anything
  decided after seeing a result is labelled post-hoc and gets its own run
  directory. The archived oracles are not replaced: they remain the frozen
  references of task D, phase 2, F and K.
- No change to `core/`, `python/rang/` or any existing example. If the
  port differs from a dev branch, this report says where and proposes the
  follow-up task. A reproduced upstream defect gets an issue text under
  `research/upstream-issues/`, not filed.

## 5. Measured results (2026-10-30)

Host: WSL2, 16 CPUs, load average 1.4–9.9 throughout (quiet compared with
earlier tasks). Run directories are under `outputs/` (section 9).

### 5.1 Tricolour

**T0, precondition (frozen, passed).** Tricolour 0.2.1 in `venv-tric021` ran
`examples/oracle_tricolour.py` unchanged (`rv1-20261030-01`). On all four
controls it equals the archived container oracle `core-d-oracle-20261029-01`
in every stage array, the intensity (bit for bit) and the final flags, and
the final flags equal `after-native.npz`. The archived 0.2.1 oracle therefore
remains the 0.2.1 reference without qualification.

**T1, the 0.5.0-dev kernel chain.**
- The frozen run `-02` failed criterion 3 because of an RV1 script defect
  (section 6.1); its final flags already equalled `after-native.npz`.
- The post-hoc run `-12` uses a copy per snapshot and nothing else changed.
- Comparator `-20`, against the archived 0.2.1 oracle:

| Control (strategy) | Stages | Stage elements differing | Intensity | Final FLAG vs 0.2.1 oracle | Final FLAG vs `after-native.npz` | Flag fraction |
| --- | ---: | ---: | --- | ---: | ---: | ---: |
| 00 operational (first pass, 12 steps) | 12 | 0 in every stage | bit-equal | 0 | 0 | 0.80641 |
| 00 hold-out masked (first pass) | 12 | 0 | bit-equal | 0 | 0 | 0.91789 |
| 01 operational (mild, 10 steps) | 10 | 0 | bit-equal | 0 | 0 | 0.71847 |
| 01 hold-out masked (mild) | 10 | 0 | bit-equal | 0 | 0 | 0.87272 |

Each control has 2,293,760 FLAG elements (140 rows × 4096 channels × 4
correlations). The prediction frozen in section 1 holds: the uvrange change
cannot act here. Every `|uvw|` is at most 74.2 m, so `0~550` selects every
baseline in both versions.

**T2, the 0.5.0-dev application end to end.**
- The frozen run `-04` and post-hoc runs `-14` and `-17` failed on RV1's
  command line (section 6.2).
- Post-hoc run `-19`: `tricolour -fs polarisation -c <strategy> -nw 4 -tc 100
  <absolute copy path>`. It exits 0 on all four controls, and FLAG read back
  from each copy equals `after-native.npz` at all elements. Measured against
  each control's input it changes 775,622, 106,548, 573,902 and 2,940
  elements. FLAG_ROW is unchanged.
- This is the Ray Serve and xarray-ms path that CARACal will run. It
  reproduces the 0.2.1 native runs flag for flag.

**T3, PR #114 head `2f476ad`** (`-03` frozen, `-13` post-hoc, both with
`-12`'s script). Every stage, the intensity and the final flags are
bit-identical to T1. The rows-as-lanes change does not change flags here.

**T4, PR #112 as merged.** After both strategies, which each contain an
integer `spike_width_time: 2`, `_get_flags_impl` holds **1** compiled
signature on `367ff54`. On the PR #114 head it holds **2** (post-hoc
diagnostic `-21`/`-22`):
- `outlier_nsigma` and `spike_width_time` arrive as int64 there, because the
  branch was cut from `b01ac8f`, before #112.
- `git merge-tree 367ff54 2f476ad` merges `flagging.py` cleanly and keeps
  the casts, but conflicts in `tests/test_flagging.py`, where both PRs
  append tests.
- So #114 behaves as intended once it is rebased. It needs a rebase or a
  conflict resolution before it can merge.
- The second signature costs 4.9 s of compilation at step 08 in the cold run
  `-03`, against 0.2.1's 28.7 s in T0 (the #111 cost).

**T5, the core** (`-05`, the current tree, 0.22–0.44 s per control). Task
D's comparator passes on all five criteria in both runs:
- against the archived 0.2.1 oracle (`-06`);
- against the 0.5.0-dev chain (`-15`, post-hoc stages). The proposals are
  26,692, 26,637, 662 and 735, equal to the archive.

The frozen comparison against `-02` (`-07`) failed criterion 3 only, through
the aliasing defect.

**Dev suite.** `pytest -m "not acceptance"` on `367ff54` in `venv-tric050`:
58 passed, 2 skipped in 65 s.

**Verdict (Tricolour): identical.** 0.5.0-dev `367ff54` equals 0.2.1 on the
archived inputs:
- in every stage, the intensity and the final FLAG;
- through the CLI;
- and therefore also against the core port.

The one difference, read from the source and not exercised by these inputs,
is the `uvrange` rule. A synthetic case, labelled post-hoc, confirms it
(`outputs/rv1-20261030-logs/uvrange-demo.log`): a 700 m baseline gets 1,700
masked L-band channels from 0.2.1 and none from 0.5.0-dev, while 300 m and
900 m baselines are treated the same by both. On the LUNO array's 56
antennas, 165 of 1,540 cross baselines lie between 550 and 778 m
(`array-baselines.log`). The core reproduces 0.2.1 here
(`core/src/sumthreshold.rs` lines 1403–1411: `d2 = 0.5·Σ Δ²`, compared with
`low²`, `high²`).

### 5.2 QuartiCal

**Q0.** The input copies check out (`rv1-20261030-10/inputs/receipt.json`):
- the fixture copy, with the solve flags written in, has DATA,
  RANG_MODEL_DATA and WEIGHT_SPECTRUM equal to `state.npz`, and FLAG and
  FLAG_ROW equal to `clean-t2-f32-solve.npz`;
- the LUNO copy equals `arrays.npz` in all five columns;
- the archived trees are unchanged.

Every solve left the copies' flags unchanged.

**Comparisons** (`rv1-20261030-11/result.json`). Entries and products are
maxima over gains unflagged in the reference. Products are taken over all
unflagged pairs; the observed-pairs figure, labelled secondary, is in the
archive. The gate is 1e-6 on both, gain flags must be exact, iterations equal
and, on LUNO only, the converged fraction equal to within 1e-12.

| Input | Arm | Reference | Flags | Max entry Δ | Max product Δ | Iter. | Conv. fraction | Pass |
| --- | --- | --- | --- | ---: | ---: | --- | --- | --- |
| fixture | 0.2.7 rerun (cold) | archived 0.2.7 | equal | 3.9e-16 | 3.5e-16 | 50 | 0.98435 (not archived) | **yes** |
| LUNO | 0.2.7 rerun (cold) | archived 0.2.7 | equal | 1.1e-16 | 2.2e-16 | 50 = 50 | 0.9833234067897558 = | **yes** |
| fixture | 0.2.8-dev, `referenced=false` | archived 0.2.7 | equal | 1.7e-3 | 1.1e-7 | 50 | 0.98435 | **no** (entries) |
| LUNO | 0.2.8-dev, `referenced=false` | archived 0.2.7 | equal | 2.8e-4 | 9.7e-5 | 50 = 50 | equal | **no** (entries, products) |
| fixture | 0.2.8-dev verbatim (referenced) | archived 0.2.7 | equal | (gauge) 0.99 | 1.1e-7 | 50 | 0.98435 | yes (products only gated) |
| LUNO | 0.2.8-dev verbatim (referenced) | archived 0.2.7 | equal | (gauge) 0.074 | 9.7e-5 | 50 = 50 | equal | **no** (products) |
| fixture | 0.2.8-dev, `referenced=false` | core, `qp_weights=transposed` | equal | 1.2e-15 | 2.5e-16 | 50 = 50 | equal | **yes** |
| LUNO | 0.2.8-dev, `referenced=false` | core, `qp_weights=transposed` | equal | 3.3e-16 | 3.4e-16 | 50 = 50 | equal | **yes** |
| fixture | 0.2.8-dev verbatim | core, `qp_weights=transposed` | equal | (gauge) | 4.6e-16 | 50 = 50 | equal | **yes** |
| LUNO | 0.2.8-dev verbatim | core, `qp_weights=transposed` | equal | (gauge) | 5.6e-16 | 50 = 50 | equal | **yes** |
| fixture | 0.2.8-dev, `referenced=false` | core (archived options) | equal | 1.7e-3 | 1.1e-7 | 50 = 50 | equal | no |
| LUNO | 0.2.8-dev, `referenced=false` | core (archived options) | equal | 2.8e-4 | 9.7e-5 | 50 = 50 | equal | no |
| fixture | core (archived options) | archived 0.2.7 | equal | 1.4e-15 | 2.8e-16 | 50 | 0.98435 | **yes** |
| LUNO | core (archived options) | archived 0.2.7 | equal | 3.3e-16 | 5.6e-16 | 50 = 50 | equal | **yes** |

The precondition passes: the 0.2.7 rerun reproduces the archive on both
inputs, cold and warm, to 4e-16.

Against the frozen predictions:
- The LUNO failure of `qc028u` against 0.2.7 was predicted.
- On the fixture, the products pass as predicted (1.1e-7, L5: 1.5e-7), but
  the raw entries fail at 1.7e-3. The fixture's 50-iteration iterate drifts
  in the unconstrained gauge direction, which the gauge-invariant products do
  not see. The prediction had been stated for products only.
- The referenced and unreferenced 0.2.8-dev runs have identical products
  (4.5e-16), the same iteration count and the same converged fraction. On
  these models #440's in-loop referencing is a pure gauge change.

**Verdicts (QuartiCal).**
1. 0.2.8-dev does not reproduce 0.2.7 at the archived tolerances, on either
   input. The cause is #456, the #452 fix, which changes the Gauss–Newton
   step but not the fixed point. The solves stop at the 50-iteration cap
   before converging, so the iterate moves.
2. The core with `RANG_SOLVE_OPTIONS=qp_weights=transposed` reproduces
   0.2.8-dev (`referenced=false`) to rounding on both inputs. With
   referencing it does so in every gauge-invariant quantity. The L5 port of
   the fix is therefore exactly upstream's fix.
3. With the default options the core still reproduces the archived 0.2.7 to
   rounding. The archived comparators keep passing.

**Dev suite.** QuartiCal's `testing/tests/gains/test_complex.py` was not run
(section 6.4).

### 5.3 Cost

Wall time and peak RSS come from `/usr/bin/time` on the whole process.
"Cold" means a fresh `NUMBA_CACHE_DIR`. Numbers are reported, not gated.

| Run | Input | Wall | Peak RSS | Notes |
| --- | --- | ---: | ---: | --- |
| T0 Tricolour 0.2.1 chain, cold | 4 controls | 101.5 s | 911 MB | control 0 95.4 s, of which `sum_threshold` compilation 64.6 s (step 02) + 28.7 s (step 08, the #111 second signature); archived container: 123.9 s |
| T1 0.5.0-dev chain, cold (`-02`) | 4 controls | 24.1 s | 750 MB | control 0 18.7 s (step 02 16.8 s; step 08 0.18 s, no recompilation) |
| T1 0.5.0-dev chain, warm (`-12`) | 4 controls | 9.8 s | 497 MB | chain 8.1 s; warm step 02 1.27 s |
| T3 PR #114 head, cold (`-03`) | 4 controls | 33.5 s | 783 MB | control 0 27.0 s (20.3 s + 4.9 s second signature) |
| T3 PR #114 head, warm (`-13`) | 4 controls | 7.6 s | 505 MB | chain 6.1 s; warm step 02 1.22 s |
| T2 0.5.0-dev `tricolour` CLI (`-19`) | per control | 13.1–15.4 s | 360 MB driver | 56.8 s for 4; Ray start-up dominates; warm Numba cache; RSS of the Ray worker processes not included; archived 0.2.1 native: 302 s per control (300 s ProgressBar) |
| core flag port (`-05`) | 4 controls | 2.2 s | 106 MB | 0.22–0.44 s per control |
| Tricolour 0.5.0-dev suite | 60 tests | 71.1 s | 701 MB | 58 passed, 2 skipped |
| QuartiCal 0.2.7 `goquartical`, cold | fixture | 29.4 s | 652 MB | archived 29.4 s |
| same, warm | fixture | 3.65 s | 398 MB | |
| QuartiCal 0.2.8-dev, cold | fixture | 40.0 s | 721 MB | |
| same, warm | fixture | 2.86 s | 410 MB | `referenced=false`: 3.04 s, 410 MB |
| QuartiCal 0.2.7 (cache warm from the fixture) | LUNO | 4.58 s, 3.41 s | 375 MB | archived cold 28.3 s, warm 3.6 s |
| QuartiCal 0.2.8-dev (cache warm from the fixture) | LUNO | 3.05 s, 2.90 s | 387 MB | `referenced=false`: 3.49 s |
| core `solve_complex`, archived / transposed | fixture | 0.047 s / 0.051 s solve; 0.24 s process | 93 MB | `RAYON_NUM_THREADS=4` |
| same | LUNO | 0.29 s / 0.19 s solve; 0.42 s / 0.38 s process | 79 MB | |

On the quiet host, the 0.5.0-dev kernels cost the same as 0.2.1 once warm
(sum_threshold step 02: 1.27 s against 1.19 s archived). Cold, the chain
falls from 95 s to 19 s per first control, mostly from #112 and the newer
Numba. The CLI's 13–15 s per control is now Ray start-up rather than the
0.2.1 ProgressBar's 300 s, so #110 is resolved by 0.5.0. QuartiCal
0.2.8-dev compiles 36 % longer than 0.2.7 on a cold cache (40.0 s against
29.4 s) and runs warm in 2.9 s against 3.7 s.

## 6. Deviations (all recorded as they happened)

1. **T1 stage snapshots aliased (frozen run `-02` failed criterion 3; fixed
   post-hoc).**
   - `np.ascontiguousarray(bp_flags, dtype=bool)` returns the array itself
     when it is already C-contiguous bool.
   - The 0.5.0 executor updates `bp_flags` in place (`np.logical_or(...,
     out=bp_flags)`), so each snapshot showed the state after the last
     in-place step before the next rebinding. For example, stage 00 of
     control 0 differed from 0.2.1 by 166,770 elements and stage 02 by 0.
   - The final flags of `-02` were already right, because they are computed
     after the loop.
   - Fix `f739d5e`: the snapshot is now a copy. Rerun `-12`/`-13`; nothing
     else changed.
2. **The T2 command line, RV1 defects (frozen run `-04` failed, then post-hoc
   `-14` and `-17` failed).**
   - `-04`: the frozen order `tricolour <ms> -fs …` exits 2 ("Missing
     argument 'ms'"). The CLI is a Typer group whose options must precede
     the MS, as the upstream acceptance test calls it.
   - `-14`: with the order fixed, the CLI was given a relative MS path while
     running in the control directory, so `msv4_utils.infer_backend` found
     no table (`MSv4Backend.UNKNOWN`).
   - `-17`: the strategy path was relative as well (`FileNotFoundError`).
   - Fixes `f739d5e`, `1352d3b`, `995e367`; `-19` passed.
   - None of these is an upstream defect. A Typer group that does not accept
     options after the positional is easy to trip over, but it is not worth
     an issue.
3. **Cold-cache cost on LUNO.** The frozen protocol keeps one Numba cache per
   version, and the fixture runs first. The LUNO "cold" runs therefore found
   22 and 24 cache index files already present and are effectively warm.
   Cold cost is measured on the fixture only.
4. **QuartiCal dev suite not run.** `testing/conftest.py` downloads its test
   Measurement Sets from Dropbox. That download was not authorised for this
   task, so the frozen fact "suite result" is missing for QuartiCal. The
   user's own comment on #452 reports a test of `d54c46b`.
5. **Fixture prediction.** The frozen prediction that `qc028u` would pass
   against 0.2.7 on the fixture was stated in terms of products. It holds
   for products, but criterion 2 also gates entries, and those fail
   (5.2). The gates were not changed.
6. **Post-hoc analyses (labelled):**
   - the #114 signature diagnostic (`-21`, `-22`, stage arrays deleted, logs
     kept);
   - the `git merge-tree` check of #114;
   - the synthetic uvrange demonstration and the whole-array baseline count
     (`outputs/rv1-20261030-logs/`).

## 7. Open items

- Neither release exists. `367ff54` may not be 0.5.0: draft PR #108 is to
  land first, and #114 is open. `d54c46b` may not be 0.2.8, since the
  maintainer will release "once I am happy that I haven't broken anything".
  When either is tagged, rerun `examples/oracle_tricolour_050.py` (`oracle`,
  `cli`, `compare`) and `examples/oracle_quartical_028.py` against the
  tagged commit. The scripts take the venv's commit from `direct_url.json`.
- PR #114 needs a rebase onto `0.5.0-dev`. The conflict is in
  `tests/test_flagging.py` only, and the rebase brings in the #112 casts.
- The CARACal intention behind `uvrange: "0~550"` (effective 778 m on 0.2.x):
  issue text in
  [upstream-issues/tricolour-uvrange-semantics.md](upstream-issues/tricolour-uvrange-semantics.md).
- The whole-array campaigns (L1, L2, C1 and the L4 verdict) ran the CARACal
  first pass through the port with the 0.2.1 uvrange rule. That matches what
  CARACal ran at the time. Under 0.5.0 the `uvrange_static_mask` step would
  skip 165 of 1540 baselines. The effect on those campaigns' flags is not
  measured; they are closed and archived, and nothing here changes them.

## 8. Proposed follow-up tasks

- **RV2, uvrange rule of Tricolour 0.5.0 in the core flag port (only when
  0.5.0 is released, or when a campaign needs it).**
  - Owner files: `core/src/sumthreshold.rs`, `core/src/ffi_flag.rs` (UVW per
    row as an input), `python/rang/core_flag.py` (a
    `uvrange_rule="0.2"|"0.5"` argument, defaulting to `"0.2"` so every
    archived comparator is unchanged), a new
    `tests/test_core_flag_uvrange.py`, and a report.
  - Acceptance, first: task D's comparator still passes with the default.
  - Acceptance, second: with `"0.5"`, the port equals the released 0.5.0
    kernel chain (`oracle_tricolour_050.py oracle`) in every stage on a
    synthetic case with baselines of 300, 700 and 900 m.
  - Acceptance, third: the same on one LUNO whole-array row chunk (the L1
    inputs) with the first-pass strategy.
  - Also report the change in flags on that chunk.
- **RV3, adopt `qp_weights=transposed` as the core's default once QuartiCal
  0.2.8 is released.**
  - Owner files: `core/src/solve.rs` (default only), `python/rang/core.py`
    docs, a report, tests.
  - Acceptance, first: the core with the new default equals released 0.2.8
    with `G.referenced=false` on the fixture and LUNO to ≤ 1e-6 (measured
    here: 1.2e-15).
  - Acceptance, second: `RANG_SOLVE_OPTIONS=qp_weights=archived` reproduces
    every archived 0.2.7 comparator.
  - Acceptance, third: the products against the referenced default are
    ≤ 1e-6.
  - L5 found no held-out effect from the change (|Δ| ≤ 8e-9), so this is
    alignment with upstream, not a science change. The user decides; L5's
    decision rule kept the archived default.

## 9. Ignored output directories (`outputs/`, not committed)

| Directory | Size | What |
| --- | ---: | --- |
| `rv1-20261030-01` | 98 MB | T0, Tricolour 0.2.1 venv chain (equals the archived oracle) |
| `rv1-20261030-02`, `-03` | 98 MB each | frozen T1 / T3 (aliased stages; receipts used for cold timings) |
| `rv1-20261030-04`, `-14`, `-17` | 0.2 MB each | failed CLI runs (logs, unchanged FLAG) |
| `rv1-20261030-05` | 29 MB | core flag run |
| `rv1-20261030-06`, `-07`, `-08`, `-15`, `-16`, `-18`, `-20` | 12 KB each | comparator results |
| `rv1-20261030-10` | 102 MB | QuartiCal input copies, every arm's gains, logs and `gains.qc` |
| `rv1-20261030-11` | 48 KB | QuartiCal comparator |
| `rv1-20261030-12`, `-13` | 98 MB each | T1 / T3 post-hoc (the references of the verdict) |
| `rv1-20261030-19` | 0.2 MB | T2 CLI, passing run (final FLAG per control) |
| `rv1-20261030-21`, `-22` | 12 KB each | #114 signature diagnostic (receipts only) |
| `rv1-20261030-logs` | 0.2 MB | per-run `/usr/bin/time` logs, the dev suite log, the post-hoc scripts and logs |
| `rv1-20261030-check-all.log` | – | `tools/check-all.sh` |

About 720 MB in all. The archived inputs (`tv-caracal-wsl-20261029-01`,
`core-d-oracle-20261029-01`, `tv-response-wsl-20261029-01`,
`luno-solve-20261029-02`, `core-phase2-inputs-20261029-01`) were read only:
- every Tricolour receipt records `host_unchanged: true`;
- after all runs, the task D host hashes equal the archived oracle's record,
  and the QuartiCal archived hashes equal those taken before Q0.

## 10. Timings (rows for `tool-timings.md`)

| Date | Tool / stage | Input | Wall | Peak RSS | Notes |
| --- | --- | --- | ---: | ---: | --- |
| 2026-10-30 | PyPI JSON + GitHub API facts (tags, branches, 10 issues/PRs, comments) | 2 + ~20 requests | about 5 s | – | unauthenticated API |
| 2026-10-30 | `git clone` tricolour, QuartiCal | 2 repos | 2.4 s, 2.7 s | – | |
| 2026-10-30 | worktree venv (`uv venv` + editable install with the extension) | worktree | 86.4 s | 1.1 GB | |
| 2026-10-30 | five oracle uv venvs (tricolour 0.2.1 / 0.5.0-dev / #114, QuartiCal 0.2.7 / 0.2.8-dev) | – | 12.7, 3.8, 1.6, 2.2, 0.5 s | ≤ 117 MB | warm uv cache |
| 2026-10-30 | Tricolour 0.2.1 step chain, cold Numba (venv, Python 3.12) | 4 controls, 140 rows × 4096 ch | 101.5 s | 911 MB | 64.6 + 28.7 s compilation in control 0 |
| 2026-10-30 | Tricolour 0.5.0-dev `367ff54` step chain, cold | same | 24.1 s | 750 MB | 16.8 s compilation, one signature |
| 2026-10-30 | same, warm | same | 9.8 s | 497 MB | chain 8.1 s |
| 2026-10-30 | Tricolour PR #114 head step chain, cold / warm | same | 33.5 s / 7.6 s | 783 / 505 MB | two signatures (branch predates #112) |
| 2026-10-30 | Tricolour 0.5.0-dev `tricolour` CLI (Ray Serve, xarray-ms), `-nw 4` | per control | 13.1–15.4 s | 360 MB (driver) | warm Numba; 0.2.1 native was 302 s |
| 2026-10-30 | Tricolour 0.5.0-dev `pytest -m "not acceptance"` | 60 tests | 71.1 s | 701 MB | 58 passed, 2 skipped |
| 2026-10-30 | core flag port, `run_core_flags.py` | 4 controls | 2.2 s | 106 MB | 0.22–0.44 s per control |
| 2026-10-30 | QuartiCal 0.2.7 `goquartical`, fixture, cold / warm | 140 rows × 4096 ch, 2 × 32 | 29.4 s / 3.65 s | 652 / 398 MB | fresh uv venv, Numba 0.68.1 |
| 2026-10-30 | QuartiCal 0.2.8-dev `d54c46b`, fixture, cold / warm / `referenced=false` | same | 40.0 / 2.86 / 3.04 s | 721 / 410 / 410 MB | |
| 2026-10-30 | QuartiCal 0.2.7, LUNO slice (cache warm from fixture), two runs | 192 rows × 2048 ch | 4.58 s, 3.41 s | 375 MB | |
| 2026-10-30 | QuartiCal 0.2.8-dev, LUNO slice, verbatim ×2 / `referenced=false` | same | 3.05, 2.90 / 3.49 s | 387 MB | |
| 2026-10-30 | core `solve_complex`, fixture / LUNO, archived and `qp_weights=transposed` | 50 iterations | 0.047–0.051 s / 0.19–0.29 s solve; ≤ 0.42 s process | 93 / 79 MB | `RAYON_NUM_THREADS=4` |
| 2026-10-30 | RV1 comparators (flags ×7, QuartiCal ×1, archive build) | – | 0.4–2.3 s each | ≤ 90 MB | |

## 11. For the coordinator

Branch `rv1-revalidate`. Owner files only: this report,
`results/rv1-revalidate.json`, `examples/oracle_tricolour_050.py`,
`examples/oracle_quartical_028.py`, `tests/test_rv1_revalidate.py` and
`upstream-issues/tricolour-uvrange-semantics.md`. No shared file is edited.

**`research/README.md`, new index line (top of the "New" list):**

> New, 2026-10-30: RV1, [re-validation](rv1-revalidate.md) against the
> unreleased Tricolour 0.5.0-dev (`367ff54`: flag for flag identical to
> 0.2.1 and the core port, CLI included; the `uvrange` rule changed) and
> QuartiCal v0.2.8-dev (`d54c46b`: the #452 fix moves 50-iteration gains by
> up to 2.8e-4; the core's `qp_weights=transposed` reproduces it to 1e-15).

**`research/STATE.md`, new top paragraph:**

> RV1 re-validation (big plan), 2026-10-30 (implemented; measured;
> [rv1-revalidate.md](rv1-revalidate.md)). Neither Tricolour 0.5.0 nor
> QuartiCal 0.2.8 is released (PyPI: 0.2.1 and 0.2.7), so the release branches
> were used at recorded commits.
>
> Tricolour `0.5.0-dev` `367ff54` (Python ≥ 3.11, Ray Serve, xarray-ms)
> reproduces 0.2.1 on task D's four controls:
> - every one of the 44 strategy-step windows, the polarised intensity bit
>   for bit, and the final FLAG are identical;
> - the `tricolour` CLI end to end gives FLAG equal to `after-native.npz`;
> - so task D's comparator passes the core against 0.5.0-dev unchanged.
>
> The one difference is latent. `apply_static_mask`'s `uvrange` now selects
> |uvw| ≤ 550 m, where 0.2.1 and the port select 0.5·|Δp|² ≤ 550², up to
> 778 m. That is 165 of 1540 LUNO array baselines, and none of task D's.
>
> #112 leaves one kernel signature. #114 gives identical flags but needs a
> rebase, because its branch predates #112.
>
> QuartiCal `v0.2.8-dev` `d54c46b` fixes #452 (#456). That moves the gains of
> the capped 50-iteration solves away from the archived 0.2.7 oracle: entries
> by up to 1.7e-3 (fixture) and 2.8e-4 (LUNO), products by up to 1.1e-7 and
> 9.7e-5. The core with `RANG_SOLVE_OPTIONS=qp_weights=transposed` (L5)
> reproduces 0.2.8-dev to 1.2e-15, with the same flags, iterations and
> converged fractions. #440's default referencing of `complex` is a pure
> gauge change (products equal to 5.6e-16).
>
> 0.2.7 rerun in a fresh venv reproduces the archive to 4e-16. No port
> change. Archive `results/rv1-revalidate.json`.

**`research/tool-timings.md`:** the rows of section 10.

**`research/big-plan.md`:**
- Under the "Follow-up: Tricolour 0.5.0" bullet, append: "RV1 done
  2026-10-30 (`rv1-revalidate.md`): 0.5.0-dev `367ff54` identical to 0.2.1
  and the port on task D's inputs; the `uvrange` rule differs (RV2
  proposed); QuartiCal v0.2.8-dev reproduced by the core's
  `qp_weights=transposed` (RV3 proposed). Rerun both scripts when the
  releases are tagged."
- Add RV2 and RV3 from section 8 as proposed tasks.

**`research/upstream-notes.md`, new section "Upstream status after task RV1
(2026-10-30; `rv1-revalidate.md`)":**
- Tricolour 0.5.0 not released; `0.5.0-dev` `367ff54` reproduces 0.2.1 flag
  for flag on the four task D controls (kernel chain and CLI). The licence
  metadata is BSD-3-Clause there.
- Tricolour #110: resolved in 0.5.0-dev (no ProgressBar; the CLI takes
  13–15 s per control, mostly Ray start-up, against 302 s).
- Tricolour #111: fixed by #112 (one signature measured). The issue is still
  open because the PR targeted a non-default branch; it can be closed with a
  comment pointing to #112.
- Tricolour `uvrange` semantics changed in 0.5.0 (|uvw| against
  0.5·|Δp|²; effective 778 m becomes 550 m for CARACal's `0~550`; 165 of 1540
  MeerKAT baselines). Text in `upstream-issues/tricolour-uvrange-semantics.md`;
  a release-note request, not a defect; not filed.
- QuartiCal 0.2.8 not released; `v0.2.8-dev` `d54c46b` contains the #452
  fix (#456), verified against the core's independent port of the fix to
  1e-15 on two inputs. #440 makes `complex` referenced by default: rang's
  archived command (`solver.reference_antenna=0`) now yields gains in a
  different gauge with identical products. The dev branch still reports
  version `0.2.7`, and Tricolour's reports `0.0.0`.

**`research/upstream-prs.md`, summary table updates:**
- Row "Tricolour frequency axis, rows as lanes": append "RV1: flags
  bit-identical to `367ff54` in every stage on task D's controls; the head
  `2f476ad` predates #112 (two kernel signatures) and conflicts with it in
  `tests/test_flagging.py`; needs a rebase onto `0.5.0-dev`".
- Row "QuartiCal qp JHJ weights": replace the PR cell with "fixed upstream by
  #456 (`d54c46b`, `v0.2.8-dev`); RV1: matches the core's
  `qp_weights=transposed` to 1.2e-15".
- Row "Tricolour integer `spike_width_time`": append "RV1: one signature on
  `367ff54` after both CARACal strategies".

**`pyproject.toml`: no change.** The `flagging` extra pins `quartical==0.2.7`
and `stimela==2.1.4` for the frozen history. No bump is warranted:
- 0.2.8 is not on PyPI, and the project uses public PyPI only;
- every archived oracle and comparator was made with 0.2.7, and a bump would
  make the extra disagree with them, by up to 2.8e-4 in gains, as measured
  here.

When 0.2.8 is released, a separate extra or a documented second pin is
better than moving this one (RV3).

**Upstream observations to file or list (the user decides):**
1. `tricolour-uvrange-semantics.md`: a release-note request on
   ratt-ru/tricolour, plus a question to caracal-pipeline about 550 m against
   778 m.
2. PR #114 rebase onto `0.5.0-dev` (rang's own PR; a push to the user's fork
   needs the user's go-ahead).
3. Optional comments: on #111 that #112 resolves it (one signature
   measured), and on #110 that 0.5.0-dev removes the wait.

**Ignored output directories:** section 9 (about 720 MB).
