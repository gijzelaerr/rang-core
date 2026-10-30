# Big plan task DF2c: `--gridder` for the campaign runs, the exact-gridder plan in L1's receipts, and L2, L1-M and C1 re-imaged with `wgrid` (post hoc)

Protocol frozen 2026-10-31 on branch `df2c-campaign-gridder` (from `main`
`8ab6db8`), before any driver change. Task DF2c of [big-plan.md](big-plan.md),
a small follow-up of DF2b ([df2b-wgrid.md](df2b-wgrid.md)): its open items
1 and 5 and deviation 7.

**Status at freeze: proposed.** Nothing below is implemented or measured
except the default baselines taken at `8ab6db8` before the freeze (section
"Invariants").

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
