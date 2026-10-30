# P11: extract what the core uses from the frozen modules, then retire them

Big plan wave 2 task P11 ([big-plan.md](big-plan.md); proposal in
[simplification-review.md](simplification-review.md) section 3 "P11", section 4
row P11). Branch `p11-retire` from main `2da566c`, worktree
`~/Worktrees/rang/p11-retire`. Status: **done, measured.** The protocol below
was frozen and committed (`1040854`) before any copy or move; results, timings
and the coordinator notes follow it. Paths: the 21 frozen modules named in
research notes moved to [`history/`](../history/README.md) on 2026-10-30;
their live definitions are in the `core_*` extracts listed below.

## Protocol (frozen before extracting)

### What retires

The 21 frozen campaign modules that live code still imports, 11,217 lines at
`2da566c`: `python/rangtoy/flagging.py`, `flagging_{actions, balanced,
caracal, comparators, equivariance, imaging, influence, injections, next,
prepared, prospective, response, signal, signal_guard, sky, structured,
structured_proposals, trend, workflow}.py` and `imaging_sensitivity.py`.
They move with `git mv` to `history/python/`, byte-identical (sha256 manifest
before and after, as P8 did), beside P8's six recipe-only modules. Their 21
test files (4,838 lines: `tests/test_flagging{,_actions, …}.py` for each
module above, `tests/test_flagging_trend_review.py`,
`tests/test_imaging_sensitivity.py`) move the same way to `history/tests/`.
`tests/test_flagging_followup_archives.py` stays: it reads archived JSON only
and imports no frozen module. `projector.py` stays: its `_native_library`
shim (task P7) is what the extracted copies call.

Live Python lines at `2da566c` (`git ls-files … | xargs cat | wc -l`):
`python/rangtoy` 31,100; `tests` 13,042; `examples` 18,287.

### Inventory: what the live chains execute (fresh coverage, suite `-01`)

Coverage (`coverage run -p --source=python/rangtoy,history`, `COVERAGE_CORE=sysmon`)
of every step of the live-chain suite below at `2da566c`
(`outputs/p11-20261030-01`, plus `-01b` for `bench f`, which needed
`numcodecs` installed): the frozen modules execute **1,293 of 4,395
statements (29 %)**. S1 measured 1,340 of 4,281 with the K replay included;
the K replay cannot run now (its fetched spans were pruned, see "Suite").

The extraction set is the **static closure**, not the executed lines: every
top-level definition that a live importer names (package, `rangtoy.notebook`,
examples, tools and the tests that stay), plus every definition those name,
transitively across the frozen modules. Copying executed lines only would cut
functions in half; the closure is a superset of what runs. Coverage is the
evidence that nothing executed is left behind: **no frozen function executed
by the suite is outside the closure** (checked per function; class method
bodies counted, not the `def` lines that run at import).

| Frozen module | Extract | Statements | Executed | Lines | Extract lines | Functions executed by the suite | Extracted, not executed by the suite | Constants extracted |
| --- | --- | ---: | ---: | ---: | ---: | --- | --- | --- |
| `flagging` | `core_policy` | 151 | 106 | 267 | 233 | _tv_kernel, assert_preserved, axis_weights, fixed_support_tv, gain_tv, polar_gauge, policy_mask, protected_flags, residual_features | split_holdout (notebook) |  |
| `flagging_actions` | `core_patches` | 179 | 81 | 464 | 194 | candidate_patches, fit_action_model, proposal_from_model, split_actions |  | FEATURE_NAMES |
| `flagging_balanced` | `core_balanced` | 147 | 36 | 365 | 59 | balanced_rank |  | GROUPS, RANDOM_SEED, RANKINGS |
| `flagging_caracal` | `core_controls` | 156 | 38 | 386 | 53 | score_control, training_proposal |  |  |
| `flagging_comparators` | none | 243 | 24 | 580 | 0 | (import-time lines only) |  |  |
| `flagging_equivariance` | `core_cases` | 164 | 40 | 384 | 60 | phase_factors |  | CASES, PATTERNS, REFERENCE_HZ |
| `flagging_imaging` | `core_image_fit` | 376 | 76 | 899 | 156 | _read_images, image_diagnostics, image_geometry, linear_image_fit |  | IMAGE_CLOSURE_JY, SETTINGS |
| `flagging_influence` | `core_influence` | 281 | 108 | 780 | 263 | _complex, _functions, _maps, _npz, _predict, _training_bundle, anchored_response, training_normals | jones_jacobian (tests) | INFO, REASONS |
| `flagging_injections` | `core_injection_model` | 225 | 79 | 500 | 164 | injection_scores, make_injection, reference_distance |  | PATTERNS |
| `flagging_next` | `core_receipts` | 78 | 22 | 151 | 31 | source_receipts |  |  |
| `flagging_prepared` | `core_paths` | 143 | 14 | 263 | 21 | reject_nested_paths |  |  |
| `flagging_prospective` | `core_forecast` | 265 | 93 | 647 | 250 | _freeze_view, forecast_family, make_shortlist, score_forecasts | CampaignBudget | MARGIN, SEEDS |
| `flagging_response` | `core_response` | 376 | 104 | 929 | 258 | Budget, _correct, _jones_samples, _product_distance, allocated_bytes, linear_response | _json_default, copy_bound | ALLOCATION_BYTES, CONDITION_LIMIT, GRIDS, RESERVE_BYTES, SKIES, SOURCES |
| `flagging_signal` | `core_templates` | 295 | 44 | 929 | 123 | spatial_templates | corrected_intensity (P6 port's oracle, `response._correct`) | ARCMIN, INVERSE_CONDITION_LIMIT, REFERENCE_HZ, SOURCES |
| `flagging_signal_guard` | `core_guard` | 323 | 87 | 934 | 405 | _evaluate, _rfi_diagnostics, actual_acceptance, choose_slots | fit_transfer, inverse_tangent, train_signal_guard (imported by `core_signal`) | GRID, MAXIMUM_SOLVES, MINIMUM_BENEFIT, PROBE_JY, SEEDS, TRANSFER_LIMIT |
| `flagging_sky` | `core_catalog` | 184 | 39 | 595 | 43 | point_catalog_predict |  |  |
| `flagging_structured` | `core_structured` | 89 | 18 | 267 | 42 | _compact, choose_action |  |  |
| `flagging_structured_proposals` | `core_proposals` | 124 | 108 | 280 | 278 | _bool_shape, _inputs, _row_groups, generate_candidates, rank_candidates |  | FREQUENCY_WIDTHS, TV_CAP |
| `flagging_trend` | `core_trend_run` | 135 | 120 | 318 | 322 | TrendBudget, _kernel, detrended_tv, estimate_trend, guidance_from_tv, run, training_gain_support |  |  |
| `flagging_workflow` | `core_state` | 333 | 33 | 917 | 39 | load_state, tree_digest | write_json (examples) |  |
| `imaging_sensitivity` | `core_sensitivity` | 128 | 23 | 362 | 375 | (constants only, from `core_imaging`) | the task A study functions (`run_imaging_sensitivity.py`, `compare_imaging_reproduction.py`, `summarize_imaging_sensitivity.py`) | ADJACENT, DEFAULTS, FITTED_JOBS, FLAGS, JOBS, ROLES, UNIT_JOBS, WEIGHT_KEYS |

Extract lines are the generator's dry run (header included); about 3,370
lines replace 11,217. The full per-function record (lines, statements,
executed statements, extracted) is
[results/p11-extract/inventory.json](results/p11-extract/inventory.json).

### Extraction rule

1. **One extract per frozen module**, `python/rangtoy/core_<x>.py` (names in
   the table), never merged. Reasons: `core_trend.run` patches the trend
   module's global `generate_candidates` for the duration of the frozen
   `run`; `core_signal`'s P6 path patches `response.corrected_intensity` (a
   name `flagging_response` imports from `flagging_signal`) and the
   shortlist's `generate_candidates`; and `SOURCES`, `REFERENCE_HZ`,
   `SEEDS`, `PATTERNS`, `_compact`, `_npz`, `_bool_shape` exist in several
   modules with different meanings. One namespace per frozen module keeps
   every patch and every name where it was. The extracts stay in
   `python/rangtoy/` (code that finds the repository through
   `Path(__file__).parents[2]` keeps working).
2. **Verbatim.** Every top-level definition that binds a closure name is
   copied byte for byte, in source order, with its decorators and the comment
   lines directly above it. The copies are written by a script
   ([results/p11-extract/gen_extract.py](results/p11-extract/gen_extract.py)),
   not by hand.
3. **Only imports differ.** The import block keeps, in source order, the
   imports the copied definitions use (and any closure name a module only
   re-exports, such as `flagging_response.corrected_intensity`); a frozen
   module is replaced by its extract (`from .flagging import gain_tv` →
   `from .core_policy import gain_tv`; `from . import flagging_influence as
   influence` → `from . import core_influence as influence`). Two in-body
   imports are rewritten the same way: `flagging_trend.run`'s
   `from .flagging_next import source_receipts` and
   `imaging_sensitivity.job_metrics`'s `from .flagging_imaging import …`.
   Each extract opens with a docstring naming the source module, the commit
   `2da566c` and the source file's SHA256.
4. **Checked.** A new test (`tests/test_p11_extract.py`) reads
   `history/python/<source>.py` as text (it imports nothing from `history/`)
   and asserts that every definition of every extract equals its source
   segment, after mapping the two in-body import lines back; it also checks
   each extract's recorded SHA256 against the history file. "The frozen
   consumer runs unedited" stays checkable by diff.
5. **Refactor only afterwards** (not in this task): the extracts keep the
   frozen modules' names, docstrings and ctypes-shaped calls.

### Rewiring (import lines; necessary non-import edits listed)

- `core_*` drivers and campaign modules: `core_actions`, `core_injections`,
  `core_prospective`, `core_signal`, `core_trend`, `core_imaging`,
  `core_campaign`, `core_campaign_array`, `core_campaign_1830`,
  `core_campaign_fieldmodel`, `core_solver_study`, `core_workflow`, and the
  four lazy imports in `core_cli` (import lines only). Module aliases keep
  their old local names so that bodies do not change (for example
  `from . import core_trend_run as flagging_trend` in `core_trend`).
- `rangtoy.notebook` (`data`, `image`, `survey`).
- Examples that import frozen names (import lines only): `prototype_section6`,
  `check_section6`, `validate_core_phase1`, `validate_core_phase2`,
  `validate_core_phase3c_a`, `bench_core_f`, `bench_p4_eigen`,
  `bench_p6_hotspots`, `build_core_trend_mirror`, `run_core_flags`,
  `survey_luno_solved`, `survey_luno_support`, `audit_luno_support_status`,
  `diagnose_native_support`, `oracle_wsclean_predict`,
  `run_imaging_sensitivity`, `compare_imaging_reproduction`,
  `summarize_imaging_sensitivity`; and `tools/wheel/run_installed.py`
  (its receipt shim patches `source_receipts`, now in `core_receipts`).
  No archive checks the SHA256 of any of these scripts against a stored
  value (`prototype_section6`'s receipt records its own hash per run).
- Necessary non-import edits:
  - `core_imaging.MODULES` names `"flagging_imaging"` and hashes
    `Path(__file__).with_name(name + ".py")` into the imaging result's
    `provenance.module_sha256`; after the move that file does not exist. The
    entry becomes `"core_image_fit"`, the module that now runs (receipts,
    below).
  - `tests/test_core_cli.py` asserts
    `core_trend.flagging_trend.run.__module__ == "rangtoy.flagging_trend"`;
    it becomes `"rangtoy.core_trend_run"`.
  - `tests/test_p7_architecture.py` imports `flagging`, `flagging_influence`
    and `flagging_trend` inside a subprocess script string; the names are
    repointed at the extracts.
- `projector.py`: docstring only (it names the frozen modules as its users).

### Tests

- The 21 frozen test files move whole (`git mv`, byte-identical).
- Every test function of those files that uses only extracted names (with the
  module-level helpers, fixtures and constants it uses) is copied verbatim
  into a live `tests/test_<extract>.py` (for example `test_flagging.py` →
  `tests/test_core_policy.py`), with import lines (including in-body imports
  and `monkeypatch` string targets) repointed at the extracts. A test that
  needs a frozen-only name (QuartiCal orchestration, MS preparation,
  containers, a frozen `run`) stays in history only. Static split at `2da566c`:
  111 test functions stay live, 99 move only; the final counts are measured
  with pytest and recorded below.
- Other live tests that import frozen names get their import lines
  repointed: `test_core`, `test_core_backends`, `test_core_campaign_array`,
  `test_core_workflow`, `test_p4_eigen`, `test_p5_memory`, `test_p6_signal`,
  `test_p6_trend` (P6's "frozen" oracle becomes the verbatim extract).
- `history/tests/` is not collected (`testpaths = ["tests"]`) and not linted.

### Receipts that hash frozen source, and how each stays truthful

| Receipt field | Written by | Before | After | Truthful because |
| --- | --- | --- | --- | --- |
| trend `configuration.module_sha256`, `audit.module_unchanged` | frozen `flagging_trend.run` (now its verbatim copy in `core_trend_run`) via `sha256(Path(__file__))` | SHA256 of `flagging_trend.py` = `3c578c5e…` = the archive's (`gain-tv-next-trend.json`) | SHA256 of `core_trend_run.py` (the module that ran; differs because of the header and import lines) | it hashes the code that ran; `history/python/flagging_trend.py` keeps `3c578c5e…` (manifest), and `test_p11_extract` proves `run` is that file's `run` verbatim. The trend comparator excludes `configuration` and every `*sha256*` key, so the verdict cannot depend on it; `module_unchanged` compares within one run and stays true |
| trend `configuration.runtime_receipts` | `source_receipts()` (now `core_receipts`) | SHA256 of every `python/rangtoy/*.py`, `src/*.rs`, manifests and the extension (P8 already removed the recipe and `tools/flagging` entries) | the same globs over the new tree: the frozen files drop out, the extracts come in | it lists what is on disk at run time, as designed; excluded by the comparator; `runtime_unchanged` compares within one run |
| trend `native_library_sha256` | same `run` | extension SHA256 | unchanged (same build) | no change |
| imaging `provenance.module_sha256` | `core_imaging._module_sha256` over `MODULES` | includes `flagging_imaging` | includes `core_image_fit` instead | it hashes the module whose functions ran; the key is in the imaging comparator's excluded set (`core_compare`, volatile and provenance keys) |
| section 6 receipt `code_sha256` | `prototype_section6.py` hashes itself, `core.py`, `core_zarr.py`, `core/src/*.rs` | script SHA256 | changes (import lines) | records the script that ran; `check_section6` checks the key's presence only |
| rang receipts `commit`, `inputs`/`outputs` digests, timings | `rang-core` (P9) | HEAD `2da566c` | branch HEAD | volatile by design |
| campaign `code_sha256` (K, L1, L2, L1-M receipts; found after the protocol, see Results) | `core_campaign.CODE_FILES`, inherited by `core_campaign_array`, `_1830`, `_fieldmodel` | includes `python/rangtoy/flagging.py` | includes `python/rangtoy/core_policy.py` instead (one string in `CODE_FILES`) | it hashes the module that runs; the key is copied into archives and excluded by every comparator; without the edit the receipt would hash the C1 re-export, or fail once it is deleted |
| frozen-only receipts (`flagging_actions.run`, `flagging_balanced`, `flagging_caracal.run`, `flagging_structured.run`, `flagging_equivariance.run`, `flagging_influence.run`, `flagging_comparators.run`, `flagging_imaging` tool receipts) | not extracted | – | – | not on any live chain; the history copies are byte-identical |

### Compatibility re-exports for running siblings

Checked at the start (diffs against each sibling's merge base and
uncommitted files in `~/Worktrees/rang/{c1-closure, df2-wgridder-speed,
e3-table-writer, fs1-flux-standards}`): only C1's new
`python/rangtoy/core_campaign_closure.py` imports a frozen module
(`from .flagging import fixed_support_tv, gain_tv, polar_gauge`). A thin
`python/rangtoy/flagging.py` re-exporting those three names from
`core_policy` is added in a commit after the move (so that git records the
move as a rename), marked temporary; the coordinator switches C1's line to
`from .core_policy import …` at its merge and deletes the shim. No live code
on this branch imports it (the import-blocker test below excludes it).

### Suite (live chains)

[results/p11-extract/suite.sh](results/p11-extract/suite.sh): S1's suite
through `rang-core STAGE VERB`, every step under coverage, with
`OPENBLAS_NUM_THREADS=1 RAYON_NUM_THREADS=4`. Steps: K precondition, L1 and
L2 preconditions (added: nothing else reaches `core_campaign_array` and
`core_campaign_1830`), section 6 run and checker, phase 1, phase 2 and phase
3c-a validators, `bench f check`, actions, injections, prospective, signal
(default and `RANG_P6=1`), trend mirror and run, every comparator (trend as
frozen and post hoc), weights (B), gridder (C), flags (D), MS reader (E),
imaging replay (I) and its archive and host comparators. Dropped from S1's
list: the K replay and K checker (`outputs/core-k-20261030-01/fetch` was
pruned, as P9 found), and the `-blas1` timing variants.

Baseline at `2da566c` (`outputs/p11-20261030-01`, `-01b`): every comparator
as archived (actions exact 61 / float 102 / difference 24; injections exact
864 / float 940 / injection_float 24 / distance 54; prospective exact 1,875 /
float 1,239 / difference 102; signal and signal P6 exact 261 / float 208 /
difference 4 / reported 12; trend frozen fails with 28 failures and post hoc
passes, exact 875 / float 168; imaging archive and host pass; B criteria 1–5;
C measurement and WCS; D pass; E pass; section 6 all 11 criteria; K
precondition all checks, χ² 0.26823507037914956; phase 2 all; phase 1 all
but criterion 4 (post hoc 4b passes, as archived); phase 3c-a measured;
bench f all identity checks true). Two steps fail at the base and are kept
as identity-of-failure checks: the L1 precondition (`all_equal: false`,
first hypothesis false, `pass: false`; K's hash matches the archive) and the
L2 precondition (`ValueError` broadcasting `(192, 2048)` against `(128,)` in
`core_campaign_array.solve_flags_lean`). Both are pre-existing and outside
this task; listed under open items.

### Acceptance

1. **Byte identity of the moved files**: the sha256 manifest of the 21
   modules and 21 test files before and after the move is identical (paths
   aside).
2. **Verbatim extracts**: `tests/test_p11_extract.py` passes.
3. **Live-chain identity**: the suite after the rewiring (frozen modules
   still present, `-02`) and after the move (`-03`) gives the same exit
   status for every step, and every JSON file of every step's output equals
   the baseline's after normalising the run directory, except the volatile
   keys (timings, RSS, loads, `commit`, input-directory listings) and the
   provenance keys named in the receipts table; NPZ, FITS and other binary
   outputs are byte-identical. The comparator receipts (verdicts and class
   counts) are identical. The diff tool
   ([results/p11-extract/identity.py](results/p11-extract/identity.py))
   reports every differing key and its class; no unexpected difference.
4. **No history import on a live chain**: coverage of `-02` shows 0 executed
   statements in the frozen modules (still present), and of `-03` no
   `history/` file at all; an import check with `history/` renamed away and
   a `sys.meta_path` blocker that raises on `rangtoy.flagging*` and
   `rangtoy.imaging_sensitivity` imports `rangtoy`, every `rangtoy.core_*`
   module, every `rangtoy.notebook.*` module, and runs `rang-core -h`.
5. **Notebooks execute** (`tests/test_notebook_execute.py`).
6. **check-all passes** (`bash tools/check-all.sh`), once before the final
   commit.
7. **Lines** counted before and after (`git ls-files` per tree).

## Results

Commits on `p11-retire`: `1040854` protocol; `2223f05` extracts and rewiring
(frozen modules still present); `0fb637d` the move (42 renames, all `R100`);
`0dbf6ff` the C1 re-export; `a04766d` campaign `CODE_FILES` names
`core_policy.py`, and `test_p11_extract` allows exactly C1's import; the final
commit adds this section and the evidence.

### 1. Byte identity of the moved files: pass

`manifest-before.txt` (taken at `2223f05`, unchanged against `2da566c`) and
`manifest-after.txt` (the same 42 names under `history/python/` and
`history/tests/`) are identical
([results/p11-extract/](results/p11-extract/)). `git show -M --name-status
0fb637d` lists 42 `R100` renames, so `git log --follow history/<path>` keeps
each file's history. `history/python/flagging_trend.py` keeps SHA256
`3c578c5e…`, the trend archive's `module_sha256`.

### 2. Verbatim extracts: pass

20 extracts, 3,389 lines (with headers), replace 11,217 frozen lines.
`tests/test_p11_extract.py` (23 tests) checks every copied definition of every
extract against its history file as text (decorators and leading comments
included, source order, only the two in-body import lines mapped back), the
SHA256 each extract records, and that the extracts import no frozen module. A
deliberate one-character edit of `core_state.tree_digest` makes it fail. The
generator ran `ruff check --fix` (import sorting only) and `ruff format` on the
extracts; neither touched a copied definition (the test proves it).

### 3. Live-chain identity: pass

[results/p11-extract/identity.py](results/p11-extract/identity.py) compares two
suite directories file by file. Calibration first: two runs at the base,
`-01` and `-01r` (`numcodecs` installed for `-01r` so that `bench f` runs),
differ only in timings, RSS, loads, `started_utc`, `cores_busy`, the L1 cost
ratio of timings, `git_status_unchanged` (the tree changed between the runs)
and three digests over results that contain timings
(`frozen_train_responses_sha256`, `acceptance_digest_core`, the trend
`source_digest` of the mirror); those leaves are the calibration set
(`calibration.json`). `-01r` is the reference.

| Run | Tree | Files compared (JSON / binary equal) | Unexpected | Exit statuses |
| --- | --- | ---: | ---: | --- |
| `-02` | `2223f05` (extracts used, frozen present) | 214 (99 / 115) | 3, all `phase3c-a` criterion 4 `git_status_unchanged`: I generated test files while it ran; `-02b` (quiet tree) passes criterion 4 and `bench f` | equal except that step |
| `-03` | `0dbf6ff` (frozen moved) | 214 (99 / 115) | **0** | **all equal** |
| `-04` | `a04766d` (campaign `CODE_FILES` fixed; extension rebuilt by check-all) | 214 (99 / 115) | **0** | **all equal** |

`-04` also differs in `library_sha256` / `core_library_sha256` /
`native_library_sha256`: check-all's `ext-build` step rebuilt the extension
between `-03` and `-04` from unchanged Rust sources (`git diff 2da566c --
core src Cargo.toml Cargo.lock` is empty; maturin builds are not
byte-reproducible); classified as provenance.

The `archive` verbs, which the suite does not run, were run once on `-01r` and
`-04` (`outputs/p11-20261030-05`): `rang-core {imaging, actions, trend,
signal} archive` and `imaging legacy-archive` all exit 0, and the archives
differ only in timings, provenance (`module_sha256` with `core_image_fit` for
`flagging_imaging`, library hash) and `result_sha256` / the calibrated digests,
which hash results that contain timings.

Every comparator verdict and class count in `-03` equals the baseline (the
protocol's list: actions 61/102/24, injections 864/940/24/54, prospective
1,875/1,239/102, signal and signal P6 261/208/4/12, trend frozen 28 failures
and post hoc pass with 875/168, imaging archive and host pass, B, C, D, E,
section 6, K precondition χ² 0.26823507037914956, phase 1, phase 2, phase 3c-a,
bench f), every NPZ, FITS and other binary output is byte-identical, and the
L1 and L2 preconditions fail exactly as at the base. The 233 provenance
differences in `-03` are the receipt fields of the receipts table: the trend
`module_sha256` (now `core_trend_run.py`) and `runtime_receipts` (the
package's file list), the imaging `provenance.module_sha256` (`core_image_fit`
instead of `flagging_imaging`) and its `comparator_sha256` (of `core_imaging.py`,
whose import lines changed), the `code_sha256` of the edited example scripts
and of `core_campaign*`/`core_workflow` (L1 receipt), `bench f`'s `git_head`,
and the `rang.receipt` `commit`/`inputs`/`outputs` fields.
Reports: `identity-01r-02.json`, `identity-01r-03.json`.

### 4. No history import on a live chain: pass

- Coverage `-02` (frozen modules present, still under `--source`): **0 of
  4,395** frozen statements executed (21 files at 0 %), against 1,293 at the
  base.
- Coverage `-03` (`--source=python/rangtoy,history`): no `history/` file and no
  frozen module in the data; the C1 re-export `rangtoy/flagging.py` is listed
  with 0 of 2 statements executed.
- With `history/` renamed away: `import rangtoy`, all 50 `rangtoy.core_*` and
  `rangtoy.notebook.*` modules import, no `rangtoy.flagging*` or
  `imaging_sensitivity` module in `sys.modules`, and `rang-core -h` runs.
  `tests/test_p11_extract.py` repeats this with a `sys.meta_path` blocker, and
  statically checks that no file in `python/`, `examples/`, `tools/` or
  `tests/` imports a frozen module, in import statements or in script strings
  (this check found the recorder script string in `test_p4_eigen.py`, which
  the first rewiring missed: its test failed, then passed once repointed).

### 5. Notebooks: pass

`tests/test_notebook_execute.py` and `test_notebook_functions.py`: 15 passed
(all five notebooks executed, LUNO sections off as in check-all).

### 6. check-all

`bash tools/check-all.sh` at `61e3b26` and again at the final tree (`a04766d` plus this
note and the evidence files): **PASS**, every step (core tests 74, clippy,
fmt, extension build, ruff, ruff format 226 files, diff check), pytest **570
passed, 3 skipped** in 136 s (first) and 106 s (final).

### 7. Lines

| Tree (`git ls-files *.py`) | `2da566c` | After | Change |
| --- | ---: | ---: | ---: |
| `python/rangtoy` | 31,100 | 23,283 | **−7,817** (−11,217 frozen, +3,389 extracts, +13 C1 re-export; the rest is import blocks rewritten more compactly) |
| `tests` | 13,042 | 10,784 | −2,258 (−4,838 moved, +2,393 live copies, +185 `test_p11_extract.py`) |
| `examples` | 18,287 | 18,287 | 0 (import lines only) |

S1 estimated −7,300 package lines. Tests collected (`pytest --collect-only`):
722 at the base, 572 after (check-all's run reports 570 passed and 3 skipped): 342 collected items left with the 21 test files; 169 of them run live
again from 19 new `tests/test_core_<extract>.py` files (111 test functions and
their 21 helpers, 132 definitions checked verbatim by `check_tests.py`), plus
the 23 new P11 tests. The 99 test functions that stay in history only need
a frozen-only name (QuartiCal orchestration, MS preparation and copies,
containers, a frozen `run`, `flagging_comparators`, `flagging_prospective`'s
campaign driver).

### Deviations from the protocol

- After the first results commit, a review found that `core_campaign.CODE_FILES`
  (K, and through inheritance L1, L2, L1-M) hashes `python/rangtoy/flagging.py`
  by file name: after the move that is the C1 re-export. It now names
  `core_policy.py` (`a04766d`); `test_p11_extract` gained a check that no
  package file names a frozen module by file name, and fails on the old line.
  Suite `-04` reran everything after that edit.

- The identity tool gained a calibration step (two base runs) after the first
  comparison showed digests over timing-bearing results differing between two
  runs of the same commit; the classification of every other leaf is as
  frozen.
- `bench f` needs `numcodecs`, which no extra of `pyproject.toml` installs; it
  was installed into the worktree venv (public PyPI) for `-01b` onwards.
- Besides the listed non-import edits: the docstring line of
  `examples/bench_p4_eigen.py` and two `print` messages of
  `tools/wheel/run_installed.py` now name `core_influence` / `core_receipts`;
  a comment in `tests/test_core_cli.py`.
- The `-02` run overlapped my writing of test files (criterion 4 of phase
  3c-a, above); `-03` ran on a quiet tree.

### Open items

- L1 precondition fails at the base and after (`all_equal: false`, first
  hypothesis false) and the L2 precondition raises a broadcast `ValueError` in
  `core_campaign_array.solve_flags_lean` at the base and after; both
  pre-existing, not investigated here (owners of L1/L2).
- The C1 re-export `python/rangtoy/flagging.py` is temporary.
- The extracts keep the frozen modules' names, docstrings, ctypes-shaped
  kernel calls and the `projector._native_library` door; refactoring them
  (and dropping the old local aliases such as `core_trend_run as
  flagging_trend`) is follow-up work, now checkable by diff against history.
- `recipes/core-trend.yaml` and other `recipes/core-*.yaml` comments still
  say "the frozen rangtoy.flagging_trend.run"; not edited (Stimela logs of task
  H record those recipes).

## Timings (every tool run of this task)

| Date | Run | Wall | Result |
| --- | --- | ---: | --- |
| 2026-10-30 | venv (uv) and `maturin develop --release --offline` | about 2 min | built |
| 2026-10-30 | suite `-01` under coverage, base | 134 s (steps) | baseline; `bench f` missing `numcodecs` |
| 2026-10-30 | suite `-01b` (`bench f`), base | 36 s | pass |
| 2026-10-30 | suite `-01r`, base repeat | 164 s | calibration, reference |
| 2026-10-30 | suite `-02`, extracts, frozen present | 169 s | identical but phase 3c-a criterion 4 (concurrent edits) |
| 2026-10-30 | suite `-02b` (phase 3c-a, `bench f`) | 41 s | pass |
| 2026-10-30 | suite `-03`, after the move | 174 s | identical, 0 unexpected |
| 2026-10-30 | targeted pytest (new live copies) | 2.4 s | 169 passed |
| 2026-10-30 | targeted pytest (rewired tests, notebooks) | 23 s | 120 passed |
| 2026-10-30 | pytest collect-only at the base (temporary worktree, removed) | 2.4 s | 722 collected |
| 2026-10-30 | `bash tools/check-all.sh` at `61e3b26` | 482 s (pytest 136 s) | PASS, 570 passed, 3 skipped |
| 2026-10-30 | suite `-04` at `a04766d` | 170 s (steps) | identical, 0 unexpected |
| 2026-10-30 | `archive` verbs and `imaging legacy-archive` on `-01r` and `-04` | about 10 s | all exit 0; timings and provenance only |
| 2026-10-30 | `bash tools/check-all.sh` at the final tree | 196 s (pytest 106 s) | PASS, 570 passed, 3 skipped |

## For the coordinator

- **STATE paragraph.** "P11 merged: the 21 frozen campaign modules
  (`flagging*.py`, `imaging_sensitivity.py`, 11,217 lines) and their 21 test
  files moved byte-identical to `history/` (research/p11-extract.md). What the
  live chains use from them, 127 top-level definitions by the static closure, is copied
  verbatim into 20 `core_*` extracts (`core_policy`, `core_influence`,
  `core_trend_run`, `core_forecast`, `core_guard`, `core_response`, … one per
  frozen module, 3,389 lines), checked definition by definition against
  `history/` by `tests/test_p11_extract.py`. Live Python in `python/rangtoy`
  31,100 → 23,283 lines (−7,817). The live-chain suite (S1's, through
  `rang-core`) is identical before and after: every verdict, class count and
  binary output; only receipt provenance (trend `module_sha256`, imaging
  `module_sha256`, script hashes) changes. No live chain imports anything
  from `history/` (coverage, a blocked-import check, a static check). Tests
  722 → 572 collected (169 of the moved tests run live again)."
- **Timing rows** for `research/tool-timings.md`: the table above.
- **README / CONTRIBUTING lines.** README, repository guide, after the P8
  `history/` sentence: "Since P11 `history/python/` also holds the 21 frozen
  campaign modules; the package keeps verbatim extracts of what the core uses
  (`core_policy`, `core_influence`, `core_trend_run`, …;
  research/p11-extract.md)." `README.md`, `CONTRIBUTING.md`,
  `examples/README.md`, `docs/`, `.github/` and `pyproject.toml` name no moved
  file (grep), so nothing there breaks.
- **Research notes that name moved files** (links that now 404; P8 added one
  pointer line after the status paragraph, the same line works here: "Paths:
  the frozen modules named here moved to [`history/`](../history/README.md)
  on 2026-10-30 (task P11); their live definitions are in the `core_*`
  extracts of [p11-extract.md](p11-extract.md)."):
  `core-a-imaging-sensitivity.md:262`, `core-h-recipes.md:205`,
  `core-phase1.md:64`, `core-phase2.md:17`, `core-phase3-trend.md:51`,
  `flagging-equivariance-verification.md:152`, `flagging-structured.md:16-17`,
  `stack-consolidation-feasibility.md` (44 links from line 55),
  `x1-crossplatform.md:84`, `tool-timings.md:90` (coordinator file), and
  `simplification-review.md` (describes the pre-move tree).
- **Compatibility re-export for running siblings.** Only C1 imports a frozen
  module: `python/rangtoy/core_campaign_closure.py:37` `from .flagging import
  fixed_support_tv, gain_tv, polar_gauge` (C1, E3 and FS1 are on main since
  this task started; DF2a and their diffs against their merge bases import no
  frozen module). This branch adds `python/rangtoy/flagging.py`, re-exporting
  those three names from `core_policy`, so the merge with main works as is
  (`git merge-tree HEAD main`: clean, no file changed on both sides);
  `test_p11_extract` accepts exactly that import in exactly that file and
  checks that the re-export is `core_policy`'s objects. After merging, change
  line 37 to `from .core_policy import fixed_support_tv, gain_tv, polar_gauge`
  and delete `python/rangtoy/flagging.py`. Files whose import lines P11
  changed (expect textual conflicts only if a later branch edits the same
  lines): the `core_*` drivers listed under "Rewiring", `core_cli.py` (four
  lazy imports), `notebook/{data,image,survey}.py`, 18 examples,
  `tools/wheel/run_installed.py`, and the tests listed under "Tests".
- **What P12 must rename.** The 20 extracts, `core_*` modules all, plus the
  extract headers' "`rangtoy.<frozen>`" mentions (they name the historical
  module and can stay); `tests/test_p11_extract.py` matches `rangtoy.` in its
  blocker and regexes and `SOURCE` reads "python/rangtoy/…" paths in the
  headers (keep the header text as is, or adjust the regex with the rename);
  the old local aliases (`core_trend_run as flagging_trend`, …) are names
  only. `history/` files are not renamed.
- **Upstream observations.** None.
- **`numcodecs`** is needed by `rang-core bench f` but in no extra.
- **Evidence to keep.** `research/results/p11-extract/` (scripts, inventory,
  closure, manifests, extract and test-split reports, calibration and identity
  reports). Raw runs in `outputs/p11-20261030-{01,01b,01r,02,02b,03,04,05}`
  (about 2 GB in total, mostly trend mirrors and images); `-01r`, `-03` and `-04` are the
  pair the acceptance cites.
