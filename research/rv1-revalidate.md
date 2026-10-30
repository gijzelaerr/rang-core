# RV1: re-validating the Tricolour and QuartiCal ports against the next upstream versions

Task RV1 of [big-plan.md](big-plan.md) (the "Follow-up: Tricolour 0.5.0"
bullet), started 2026-10-30 on branch `rv1-revalidate` from `origin/main`
`3b875e0`. Status: **protocol frozen (this commit), before any RV1 script was
written or any upstream code was run on the archived inputs.** No port
change is part of this task.

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
