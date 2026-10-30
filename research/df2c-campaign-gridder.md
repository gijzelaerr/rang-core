# Big plan task DF2c: `--gridder` for the campaign runs, the exact-gridder plan in L1's receipts, and L2, L1-M and C1 re-imaged with `wgrid` (post hoc)

Protocol frozen 2026-10-31 on branch `df2c-campaign-gridder` (from `main`
`8ab6db8`), before any driver change. Task DF2c of [big-plan.md](big-plan.md),
a small follow-up of DF2b ([df2b-wgrid.md](df2b-wgrid.md)): its open items
1 and 5 and deviation 7.

**Status at freeze: proposed.** Nothing below is implemented or measured
except the default baselines taken at `8ab6db8` before the freeze (section
"Invariants").

**Status now: implemented and measured; every gated criterion passes**
([Measured results](#measured-results-2026-10-31)). `--gridder wstack|wgrid`
reaches all five campaign drivers (K, L1, L2, L1-M, C1). The default is
bit-identical to `8ab6db8`: 28 precondition FITS, every image number and
three whole-array images. With `wgrid`, the run records the plan (ε,
threads, backend, the `_ex2` entry point) and every image records its own
plan. L1, L2, L1-M and C1 each ran end to end with `wgrid` on four
stations. Post hoc, all 44 archived arms of L1, L2, L1-M and C1 were
re-imaged from their saved gains and flags, and the `wstack` reconstruction
reproduced every one first. Against the archived images, `wgrid` moves the
dirty image by at most 0.45 % of the peak at the edge and 0.012 % in the
central half (L2: 0.68 % and 0.017 %). The residual RMS drops by 0.36–0.65 %
on chunk 0 and by 0.95–1.1 % on L2. Residual-RMS ratios move by at most
1.4e-4. **None of the 55 recorded residual-RMS calls changes.**

## Scope and owner files

1. `--gridder wstack|wgrid` (default `wstack`) for every campaign driver:
   K (`core_campaign.run`), L1 (`core_campaign_array.run`), L2
   (`core_campaign_1830.run`), L1-M (`core_campaign_fieldmodel.run`) and C1
   (`core_campaign_closure.run`), through `rang-core campaign run` (a
   function verb in `core_cli.py`) and the script verbs `rang-core
   campaign-array run`, `campaign-1830 run`, `campaign-fieldmodel run` and
   `examples/run_c1.py`, which forward their arguments unchanged.
2. The receipt fields: the gridder of every image and run, and for `wgrid`
   the plan (DF2b deviation 7, its suggested lines for
   `core_campaign_array.image_arm`).
3. A post-hoc re-imaging of L2's, L1-M's and C1's archived arms with `wgrid`
   from their saved gains and additions (DF2b open item 5), as DF2b did for
   L1. Labelled post hoc; it changes no verdict and rewrites nothing.

Owner files: the five drivers (minimal hunks: `run` signatures, the
`image_arm` calls, the receipt fields), `tests/test_df2c_campaign_gridder.py`,
`examples/reimage_df2c.py`, `research/results/df2c-campaign-gridder.json`,
`docs/cli.md` (regenerated) and this file. `core_cli.py` is a coordinator
file (hunk listed verbatim). The four run scripts in `examples/` are not
owner files; their `--gridder` hunks are listed verbatim as a deviation.
Not edited: `core_grid.py`, `core_wgridder.py`, the Rust core, any archive.

## The option (frozen)

- Values: `wstack` (the default, the archive reproducer) or `wgrid` (DF2b's
  exact gridder, ε 1e-6). Anything else is refused with `ValueError` before
  the run directory is created.
- **K.** `core_campaign.run(..., gridder="wstack")` passes it to every
  `image_arm(..., gridder=gridder)` call.
- **L1.** `core_campaign_array.run(..., gridder="wstack")`. For `wgrid` the
  run's image dict is a copy with `"gridder": "wgrid"` (the module constants
  `ARRAY_IMAGE` and `core_campaign.IMAGE` are never mutated) and the channel
  groups are **1**: DF2b froze one call for `wgrid`, because per-group plans
  differ by 3e-8 of the peak (its open item 3). Both are recorded in
  `settings.image` and `settings.channel_groups`. An image dict that already
  names a gridder different from the argument is refused.
- **L2.** `core_campaign_1830.run(..., gridder="wstack")`, the same rule (its
  default groups are already 1).
- **L1-M** and **C1.** `run(..., gridder="wstack")` passes it to
  `core_campaign_array.run`. C1's two added arms are imaged by
  `image_or_reuse` from `settings.image` and `settings.channel_groups`, which
  carry the gridder, so they follow the run's gridder without a further edit.
- **Labels.** A non-default gridder appends `; gridder wgrid` to the run
  label, so a `wgrid` run is never mistaken for a frozen campaign.
- **CLI.** `rang-core campaign run RUN_DIR --gridder wgrid` (the function
  verb). The four run scripts take `--gridder` and pass it to their
  driver's `run`; `rang-core campaign-array run ... --gridder wgrid` reaches
  it unchanged. The scripts' precondition and memory guards are unchanged.

## Receipt fields (frozen)

- **Per image** (K's and L1's `image_arm`, so also L2, L1-M and C1):
  `gridder_name` (`wstack` or `wgrid`); for `wgrid`, `wgridder`: the plan
  `core_grid.invert` returns (ε, backend, raw PSF centre, kernel index,
  support, `nu`, `nv`, planes, `wmin_d`/`wmax_d`, ...). For `wgrid` in
  several channel groups (only when `image_arm` is called directly) each
  group record keeps its own `wgridder`. FITS get `RANGGRID` for `wgrid`
  only (K's DF2b convention), so `wstack` FITS stay byte-identical.
- **Per run**: `settings.gridder` = `{"name": "wstack"}`, or for `wgrid`
  `{"name", "epsilon", "nthreads", "cpu_count", "backend", "entry_point"}`:
  `nthreads` is `RAYON_NUM_THREADS` as set (null: Rayon's default, the
  logical CPUs, `cpu_count` beside it; the extension exposes no pool size);
  `entry_point` is `rang._core.wgridder_vis2dirty_f64` →
  `rang_core_wgridder_vis2dirty_ex2_f64` (the two-weight `_ex2` entry of
  DF2b) for the extension backend, or `rang_core_wgridder_vis2dirty_ex_f64`
  for the ctypes fallback.
- With the default, `result.json` gains only these keys (`settings.gridder`,
  `arms.*.image.gridder_name` for L1/L2/L1-M/C1, K's already has it); every
  value present before is unchanged (timings aside).

## Invariants (gated)

- **D1 — the default is unchanged.** Measured at `8ab6db8` before any driver
  edit and again on the branch, compared exactly (`reimage_df2c.py
  default`; the added receipt keys and timings excluded):
  - the L1 and L2 preconditions (`examples/precondition_luno_{array,1830}.py`;
    their replays image K's arms through L1's and L2's `image_arm`): the
    SHA256 of all 28 FITS, every arm's image numbers and the hypotheses
    (base run `outputs/df2c-20261031-01-default/base`, 15.0 s and 12.4 s);
  - whole-array `wstack` images through `core_campaign_array.image_arm` with
    the archived groups: L1 `original` (4 groups), C1 `closure-outlier`
    (4 groups) and L2 stored `original` (1 group): dirty and PSF SHA256,
    counters and metrics (`reimage_df2c.py ... --gridders wstack` at base).
- **D2 — the preconditions pass.** `tests/test_pc1_preconditions.py` (both
  tests run, not skipped) and `bash tools/check-all.sh` print `overall: PASS`.
- **D3 — the option reaches every driver** (`tests/test_df2c_campaign_gridder.py`):
  the CLI and the four scripts hand `gridder` to their `run`; L1-M and C1
  hand it to L1's `run`; an unknown value is refused; the default is
  `wstack` everywhere; a fast synthetic image through L1's `image_arm`
  with both gridders: `wstack` equal to the direct `core_grid.invert` call
  with no new FITS key, `wgrid` equal to `core_grid.invert(gridder="wgrid")`
  with `gridder_name`, the plan and `RANGGRID`.

## Post-hoc comparison (labelled post hoc; changes no verdict)

**Archives.** L2 `l2-1830-20261030-02-stored` and `-02-scalar` (6 imaged
arms each, 1 group); L1-M `l1m-20261030-01-stored`, `-02b-point`, `-03-field`
(6 each, 4 groups; `-02-point` is the failed, empty run); C1 `c1-20261030-01`
(L1's 6 arms plus `closure-outlier` and `closure-tv-policy`, which reuses
`tv-policy`'s image); L1 `luno-array-campaign-20261030-01` as the reference
(DF2b re-imaged 3 of its arms).

**Method** (`examples/reimage_df2c.py chunk0` and `l2`). The state is built
by the drivers' own functions from the local tiles (L1, L1-M and C1 share
LUNO row chunk 0) and from L2's fetch, each checked against its receipts.
For every archived arm: the saved gains and additions (SHA256 checked
against the archive), then the driver's own `core_campaign_array.image_arm`
twice — `wstack` with the archived groups, then `wgrid` in one call. Arms
with equal gains and additions are imaged once per state. Metrics are
recomputed with the archive's boxes and its recorded model flux (the L1-M
and L2 model arms change only MODEL_DATA, which enters only the flux
recovery). No solve, flagger or TV loop is repeated.

**Reconstruction gate (gated per arm, before any `wgrid` number counts).**
`wstack` with the archived settings reproduces the archived peak, residual
RMS and off-source RMS within 1e-9 relative (PC1's tolerance for P2's image
bits) and the archived float32 FITS within one float32 ulp at the peak
(dirty over the peak, PSF absolute). An arm that fails is reported without
its `wgrid` numbers.

**Reported** per archive (worst over its arms): `wgrid` against the archived
FITS in DF2b's terms — L∞ over the peak of the whole image, of the edge (the
outer two pixels) and of the central half, and the RMS — for dirty and PSF;
the moved metrics per arm (peak, residual RMS, off-source RMS, robust
residual σ, flux recovery); every recorded residual-RMS call (the
hypotheses, amendment 1's pairs, C1's pairs) recomputed from the `wgrid`
residual RMS under the frozen band (better ≤ 0.99, worse ≥ 1.01), and
whether any changes. The MSE calls do not read the image and are not
recomputed.

**Prediction** (from DF2b's L1 `original`: 0.45 % of the peak overall,
0.01 % central, residual RMS −0.36 %), reported, not gated: on these
whole-array images every dirty L∞ is ≤ 1 % of the peak and ≤ 0.1 % in the
central half, and no residual-RMS call changes. Cross-check: L1-M `stored`
and C1's L1 arms equal L1's gains, so their `wgrid` numbers equal L1's and
DF2b's (`original`: peak 14.800390, residual RMS 0.016365).

**Cost** (reported): wall and peak RSS of each replay process, seconds per
image and gridder, `RAYON_NUM_THREADS=4`, the one-minute load.

Failures are recorded as frozen; anything decided after this commit is
labelled post hoc.

## What was built (post-freeze)

The protocol and the harness are `3a729c0`. The D1 baselines were measured
at `8ab6db8` (the code tree of `3a729c0`) before any driver edit. Then:

- **`a63e227` — drivers.**
  - `core_campaign.gridder_settings(gridder)` refuses an unknown name and
    returns the run record of "Receipt fields".
  - K: `run(..., gridder)` passes it to `image_arm` and records
    `settings.gridder`.
  - L1: `image_settings(image, groups, gridder)` returns a copied image dict
    and the groups (one for `wgrid`). `run(..., gridder)` uses it, labels
    the run and records `settings.gridder`. `image_arm` records
    `gridder_name` and the plan and writes `RANGGRID` for `wgrid` only.
    `grouped_invert` keeps each group's plan.
  - L2: `run(..., gridder)` follows the same rule as L1.
  - L1-M and C1: `run(..., gridder)` validates the name first and passes it
    to L1's `run`.
  - The four run scripts get `--gridder`.
- **`9984590` — CLI.**
  - `rang-core campaign run --gridder`.
  - The script verbs' help notes `--gridder wstack|wgrid`.
  - `docs/cli.md` is regenerated.
- **`8de59b7` — tests.** `tests/test_df2c_campaign_gridder.py` has 18 tests,
  matching D3:
  - the CLI and the four scripts pass the gridder;
  - L1-M and C1 hand it to L1;
  - the `image_settings` rule;
  - an unknown name is refused before the run directory exists, in all
    five drivers;
  - the run record;
  - L1's `image_arm` with both gridders against direct `core_grid.invert`
    calls (FITS keys included);
  - per-group plans.

  All 105 tests of the campaign, CLI, docs and DF2b files pass.
- **Harness** `examples/reimage_df2c.py`. It has the subcommands `chunk0`,
  `l2`, `default` and `summary`, and produced
  `research/results/df2c-campaign-gridder.json`.

## Measured results (2026-10-31)

| Run | Contents |
| --- | --- |
| `outputs/df2c-20261031-01-default` | D1. `base/` at `8ab6db8` and `after/` at `8de59b7`: both preconditions with their hashes. `base-chunk0`, `base-l2`: `wstack` replays at base. Comparisons `default-*.json` |
| `outputs/df2c-20261031-02-reimage` | Code `8de59b7`: the post-hoc replays `chunk0/` (L1, L1-M ×3, C1) and `l2/` (stored, scalar), with logs and `time -v` |
| `outputs/df2c-20261031-03-smoke` | Code `8de59b7`: four-station `wgrid` smokes of L1 (`rang-core campaign-array run ... --gridder wgrid`), L2 (`rang-core campaign-1830 run`), L1-M and C1 (their `run` called directly; their scripts only accept `outputs/l1m-` and `outputs/c1-` paths). Receipts in `summary.json` |

Host: WSL2, 16 threads, 30 GiB, `RAYON_NUM_THREADS=4`. The one-minute load
was 3–8 from sibling tasks.

### Gated criteria

| # | Criterion | Result | Figure |
| --- | --- | --- | --- |
| D1 | default unchanged | **pass** | Preconditions: 28 FITS SHA256 and 16 image-number records (arms and hypotheses) equal, 44 entries, 0 differ. Whole-array `wstack` through `image_arm`: L1 `original` and C1 `closure-outlier` (4 groups), L2 stored `original` (1 group). Dirty and PSF SHA256, counters and metrics are equal |
| D2 | preconditions pass | **pass** | Both pass at base and after (`all_passed` true). `tests/test_pc1_preconditions.py` ran both tests, not skipped, in check-all (see "Tool runs") |
| D3 | the option reaches every driver | **pass** | 17 tests. End to end, the smokes record `settings.gridder` with the plan, `settings.image.gridder = wgrid` and one channel group. Every arm has `gridder_name = wgrid` and its `wgridder` plan, including C1's two arms. The label ends `; gridder wgrid` |
| R | reconstruction (per arm) | **pass**, all 44 | The `wstack` replay reproduces every archived peak, residual RMS and off-source RMS. The difference is 0 except on L1 run `-01`, at ≤ 1.1e-15 relative: it predates P2. FITS agree within one float32 ulp, 3.6e-8 of the peak at worst |

The archived image hashes (`dirty_sha256`) are reproduced exactly on
L1-M, C1 and L2. They are not reproduced on L1 run `-01`, which predates
P2's FFT change.

Run record of a `wgrid` run (the smokes; identical on all four):

```json
{"name": "wgrid", "epsilon": 1e-06, "nthreads": 4, "cpu_count": 16,
 "backend": "extension",
 "entry_point": "rang._core.wgridder_vis2dirty_f64 -> rang_core_wgridder_vis2dirty_ex2_f64"}
```

The per-image plan on the whole array: support 7, grid 2376², 7 w planes on
chunk 0 and 8 on L2, ε 1e-6.

### Post hoc: `wgrid` against the archived images (labelled; changes no verdict)

Worst over the archive's arms. L∞ of the difference is over the archived
peak for the dirty image and absolute for the PSF (peak one). "Edge" is the
outer two pixels and "central" the central half. RMS is over the peak.

| Archive (arms imaged, unique images) | Dirty L∞ | Edge | Central | RMS | PSF L∞ | PSF central | Residual-RMS calls | Calls unchanged |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| L1 `-01` (6; reference) | 4.46e-3 | 4.46e-3 | 1.21e-4 | 5.0e-4 | 4.46e-3 | 1.19e-4 | 7 | yes |
| L2 stored (6, 4) | 6.69e-3 | 6.69e-3 | 1.67e-4 | 5.8e-4 | 6.82e-3 | 1.59e-4 | 7 | yes |
| L2 scalar (6, 4) | 6.78e-3 | 6.78e-3 | 1.62e-4 | 5.8e-4 | 6.82e-3 | 1.59e-4 | 7 | yes |
| L1-M stored (6; = L1) | 4.46e-3 | 4.46e-3 | 1.21e-4 | 5.0e-4 | 4.46e-3 | 1.19e-4 | 7 | yes |
| L1-M point (6, 4) | 4.46e-3 | 4.46e-3 | 1.21e-4 | 5.0e-4 | 4.46e-3 | 1.19e-4 | 7 | yes |
| L1-M field (6, 4) | 4.46e-3 | 4.46e-3 | 1.21e-4 | 5.0e-4 | 4.46e-3 | 1.19e-4 | 7 | yes |
| C1 `-01` (8; L1's 6 + 1 new) | 4.46e-3 | 4.46e-3 | 1.21e-4 | 5.0e-4 | 4.46e-3 | 1.19e-4 | 13 | yes |

- **The prediction holds.** Dirty L∞ is ≤ 1 % of the peak and ≤ 0.1 % in
  the central half. The edge carries the whole maximum: on 53–56-station
  images the aliasing that dominates four-station images is small. L2's
  1830−211 field is 1.5× more affected than 1934−638, but the same order.
- **Cross-check.** L1-M stored and C1's six L1 arms have L1's gains, and
  their `wgrid` images are L1's. `original` gives peak 14.800390, residual
  RMS 0.016365 and off-source RMS 0.068792, which are DF2b's L1 numbers.
- **Moved metrics** (`original`, `wgrid` against the archive; the other arms
  move the same way):

  | Archive | Peak (Jy/beam) | Residual RMS | Off-source RMS | Robust residual σ | Flux recovery |
  | --- | --- | --- | --- | --- | --- |
  | L1, L1-M stored, C1 | 14.8003897 / 14.8003895 | 0.016365 / 0.016424 (−0.36 %) | 0.06879 / 0.07069 (−2.7 %) | 3.88 / 4.00 mJy | 1.1193773 (equal) |
  | L1-M point | 14.763832 / 14.763832 | 0.018830 / 0.018951 (−0.64 %) | 0.06875 / 0.07065 | 8.02 / 8.26 mJy | 1.1285812 (equal) |
  | L1-M field | 14.763365 / 14.763364 | 0.018828 / 0.018949 (−0.64 %) | 0.06875 / 0.07065 | 8.02 / 8.26 mJy | 1.1285874 (equal) |
  | L2 stored | 12.575288 / 12.575288 | 0.010843 / 0.010963 (−1.09 %) | 0.05856 / 0.06070 (−3.5 %) | 5.48 / 5.65 mJy | 1.0436242 (equal) |
  | L2 scalar | 7.868048 / 7.868048 | 0.0018553 / 0.0018731 (−0.95 %) | 0.03643 / 0.03775 (−3.5 %) | 1.33 / 1.36 mJy | 0.999086 (equal) |
  | C1 `closure-outlier` | 14.8003848 / 14.8003846 | 0.016365 / 0.016424 (−0.36 %) | 0.06879 / 0.07069 | 3.88 / 4.00 mJy | 1.1193772 (equal) |

  The peaks move by ≤ 5e-8 relative and the flux recovery not at all at
  the printed digits. The noise metrics drop, because the archived
  w-stacking images carry aliased far sidelobes. Every arm of an archive
  moves together, so the ratios between arms barely move.
- **Calls.** All 55 recorded residual-RMS calls (frozen hypotheses,
  amendment 1's pairs, C1's frozen pairs) are recomputed under the band
  0.99/1.01. The archived calls are `null` or `undecidable` (an
  unavailable arm), and every one is unchanged. The largest ratio move is
  1.4e-4 (L2 stored); on chunk 0 it is 2.3e-6, and 8.1e-5 under the L1-M
  model arms. The headline `tv-policy` / `tricolour-firstpass` ratios:

  | Archive | Archived | `wgrid` |
  | --- | ---: | ---: |
  | L1, L1-M stored, C1 | 0.995419 | 0.995422 |
  | L1-M point, field | 0.994095 | 0.994176 |
  | L2 stored | 0.998345 | 0.998209 |
  | L2 scalar | 0.998158 | 0.998180 |

  All stay `null`. The MSE calls do not read the image. No verdict of K,
  L1, L2, L1-M or C1 changes.

### Cost (reported)

| Run | Wall | Peak RSS | Notes |
| --- | ---: | ---: | --- |
| chunk 0 replay (13 unique arms × 2 gridders) | 6 min 58 s | 10.6 GB | state 38 s; per image `wstack` (4 groups) 11.5–21.4 s, `wgrid` (one call) 4.2–7.4 s of gridding |
| L2 replay (8 unique × 2) | 1 min 48 s | 4.65 GB | state 18 s; `wstack` (1 group) 4.7–6.0 s, `wgrid` 3.1–3.9 s |

## Deviations from the protocol

1. **The image dict's gridder** (clarified while implementing, before any
   measured run). With the default argument, a gridder already named in
   `image` holds, and only an explicit contradiction is refused. DF2b's
   `kdriver` replay passes `image=dict(core_campaign.IMAGE,
   gridder="wgrid")` with the default argument, and the frozen sentence
   would have refused it.
2. **No run label for K.** `core_campaign.run` has no label. A K `wgrid`
   run is identified by `settings.gridder` and by each arm's `gridder_name`.
3. **Non-owner files:** the four run scripts in `examples/` (two lines
   each, verbatim under "For the coordinator").
4. **K end to end with `wgrid` was not rerun.** `rang-core campaign run`
   fetches from the bucket. Its option is covered by the tests (CLI →
   `campaign` → `core_campaign.run` → `image_arm`) and by DF2b's post-hoc
   `kdriver` run of K's `image_arm`.
5. **Smokes of L1-M and C1** called their `run` directly. Their scripts
   accept only `outputs/l1m-` and `outputs/c1-` paths, and this task writes
   only `outputs/df2c-*`. The scripts' `--gridder` is covered by the tests.
6. **Failed tool runs:**
   - The first C1 smoke exited at once: `cargo` was not on that script's
     PATH, and `core_closure.library()` builds the closure kernel. It was
     rerun with PATH set (log `c1-first-no-cargo.log` kept).
   - The first `summary` call failed on a relative path. The script was
     fixed and the call repeated.
   - One patch command lost a docstring phrase to the shell's backtick
     substitution. It was fixed before the commit.

## Open items

1. Making `wgrid` the default is still DF2's decision (DF2b open item 4).
   This task adds the residual-RMS moves of L2 (−1 %) and L1-M (−0.6 %),
   and none changes a call.
2. K's science calls from a fresh fetch with `wgrid` (DF1 open item 3)
   remain open: K's bytes are not on the host.
3. WSClean's 2–4e-7 agreement floor is DF2b's open item 2, unchanged.

## Tool runs

All runs on 2026-10-31. Wall time and peak RSS are from GNU `time` unless
noted.

| Tool | Input | Wall | Max RSS | Notes |
| --- | --- | ---: | ---: | --- |
| `uv venv -p 3.14` + `uv pip install -e '.[pointing,beam,test,imaging]' ruff maturin pip` | worktree | 2 min 57 s | 1.14 GB | builds `rang._core` |
| `precondition_luno_array.py` (base / after) | K slice, four stations | 15.0 / 16.0 s | 340 / 342 MB | pass, identical |
| `precondition_luno_1830.py` (base / after) | K slice | 12.4 / 13.8 s | 307 / 306 MB | pass, identical |
| `reimage_df2c.py chunk0 --gridders wstack` (base) | L1 `original`, C1 `closure-outlier` | 1 min 31 s | 10.2 GB | state 41.6 s |
| `reimage_df2c.py l2 --gridders wstack` (base) | L2 stored `original` | 33.8 s | 4.38 GB | |
| pytest, the DF2c, DF2b, CLI, docs and five campaign test files | 106 tests | 5.3 s | 94 MB | 105 passed, 1 skipped |
| `reimage_df2c.py chunk0` | L1, L1-M ×3, C1: 32 arms | 6 min 58 s | 10.6 GB | load 6–8 |
| `reimage_df2c.py l2` | L2 stored, scalar: 12 arms | 1 min 48 s | 4.65 GB | |
| `reimage_df2c.py default` ×3, `summary` (first failed: path; repeated) | | < 1 s each | – | |
| `rang-core campaign-array run --smoke --stations 0-3 --gridder wgrid` | four stations | 12.1 s | 225 MB | |
| `rang-core campaign-1830 run --model stored --smoke --stations 0-3 --gridder wgrid` | four stations | 6.8 s | 168 MB | |
| `core_campaign_fieldmodel.run(..., 'stored', gridder='wgrid')` | four stations | 11.5 s | 225 MB | |
| `core_campaign_closure.run(..., gridder='wgrid')` (first: no cargo on PATH; repeated) | four stations | 0.3 / 17.8 s | 39 / 284 MB | |
