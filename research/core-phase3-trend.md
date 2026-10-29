# Rang core, phase 3: trend chain test

Protocol frozen 2026-10-29, before any mirror or comparator code was written.
Status: **proposed**. Part of phase 3 of the port plan
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
