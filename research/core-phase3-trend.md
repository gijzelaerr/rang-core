# Rang core, phase 3: trend chain test

Protocol frozen 2026-10-29 in `625cf57`, before any mirror or comparator
code was written. Status: **implemented; measured: criterion 3 failed as
frozen on rounding-level reference slopes; post-hoc criterion 3b passes**. Part of phase 3 of the port plan
([stack-consolidation-feasibility.md](stack-consolidation-feasibility.md)
section 9.4). A reimplementation test; under AGENTS.md not a scientific
contribution, and no archived result may change because of it.

## Question

Can unmodified downstream code consume core-produced solutions? Phases 3 and
3b compared core results with archived results. This test instead hands core
output to a frozen campaign module that has never seen it. The trend track of
the five-track campaign ([flagging-trend.md](flagging-trend.md), archive
[gain-tv-next-trend.json](results/gain-tv-next-trend.json)) makes no solves:
it reads seven saved baseline solutions (state, `diagnostics.npz`,
`metrics.json`) from the concurrent suite and computes trend-corrected TV for
four phase patterns each.

## Design

`examples/build_core_trend_mirror.py` writes a mirror of the concurrent
suite's seven `experiments/<case>` directories: `state.npz` and
`manifest.json` copied byte for byte, and `trials/baseline/diagnostics.npz`
and `metrics.json` produced by `core_workflow.core_solve` (complex, 2 × 32, 50
iterations, polar gauge) with the same keys as `flagging_workflow.solve`
writes. The frozen `rangtoy.flagging_trend.run` then runs on the mirror with
no edits, from the host venv.

## Inputs (frozen)

- `outputs/tv-concurrent-wsl-20261029-01/experiments/<case>` for the seven
  `flagging_equivariance.CASES`: `state.npz`, `manifest.json`, and QuartiCal's
  `trials/baseline/diagnostics.npz` (for criterion 1 only). Read only.
- Oracle: `raw_result` in `research/results/gain-tv-next-trend.json`.

## Acceptance criteria (frozen)

1. **Mirror baselines.** For each case, the core baseline's gain validity
   equals QuartiCal's saved `gain_valid` exactly, and gains on valid entries
   differ by at most 1e-6 (as phase 2). The worst difference is reported.
2. **Trend result, exact:** `status`, every `case_id`, `pattern`,
   `available`, `edge_counts`, `rankings`, `finite_primary_edges`,
   `finite_detrended_edges`, `new_QC_solves` and `added_flags`.
3. **Trend result, floats to 1e-9 relative** (absolute where the oracle is
   zero): `slopes_time_rad_per_second_frequency_rad_per_hz`,
   `primary_polar_TV` and `detrended_guidance_TV`.
4. **Excluded:** `configuration` (paths, source digest, module, native and
   runtime receipts, image, environment), digests and allocation figures.
5. **Unmodified consumer.** `python/rangtoy/flagging_trend.py` is byte-equal
   to the version whose hash the archive records as `module_sha256`.
6. **No side effects.** The concurrent suite inputs and the tracked tree are
   unchanged; only the mirror and the trend output directory are written.
7. **Cost (reported).** Wall time of the mirror build (seven core solves) and
   of the trend run, logged in `tool-timings.md`.

The test is reported as passed only if criteria 1–6 pass as frozen; any
failure is recorded with its numbers.

## Measured result (2026-10-29)

Mirror `outputs/core-trend-mirror-20261029-01` (seven core solves, 14.5 s)
and trend run `outputs/core-trend-20261029-01` (the frozen
`flagging_trend.run`, unedited, 31.3 s). Archive:
[core-phase3-trend.json](results/core-phase3-trend.json).

| Criterion | Measured | Outcome |
| --- | --- | --- |
| 1 mirror baselines | gain validity identical in all seven cases; gains within 1.4e-15; states copied byte for byte | pass |
| 2 exact trend fields | 875 equal, including every ranking and edge count | pass |
| 3 floats to 1e-9 relative | TV values pass; **28 slope failures**, worst relative 1.28 | **fail** |
| 4 excluded fields | configuration only | – |
| 5 unmodified consumer | `flagging_trend.py` SHA256 `3c578c5e…` equals the archived `module_sha256` | pass |
| 6 side effects | concurrent-suite file list, sizes and times, and `git status` unchanged | pass |

**Diagnosis.** All 28 failures are the slope of antenna 0 in the 28
case × pattern records. Antenna 0 is the polar-gauge reference, so its
determinant phase is zero by construction and its fitted slopes are rounding
noise: the archive has at most 6.0e-19 rad/s and 7.8e-25 rad/Hz, against
3e-5 to 5e-4 rad/s and about 6e-10 rad/Hz for the other antennas. Relative
comparison of such values is ill-posed, the same lesson as phase 1 criterion
4, which this protocol did not apply to the slopes. Every quantity computed
from the slopes passes: detrended TV, rankings and edge counts.

## Post-hoc criterion 3b (after the frozen comparison)

Each slope is compared with the largest absolute slope of the same axis in
the same record, keeping the frozen constant: |Δ| ≤ 1e-9 × max|slope|. It is
applied by `examples/compare_core_trend.py --posthoc-slope-scale`, with no
rerun of the solves or the trend module. Worst scaled difference:
8.4e-14. Pass.

**What this shows.** Core-solved baselines, written with the same file
layout and keys, are consumed by an unmodified frozen campaign module and
reproduce its archived output. This is the first hand-off test; phases 3 and
3b compared results produced by core drivers.

**Cost (reported).** Seven core solves in 14.5 s (196 MB); the frozen trend
module itself took 31.3 s (355 MB), as it does on QuartiCal-produced inputs.

Paths: the frozen modules named here moved to [`history/`](../history/README.md)
on 2026-10-30 (task P11); their live definitions are in the `core_*` extracts
of [p11-extract.md](p11-extract.md).
