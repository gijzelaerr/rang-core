# Rang core, phase 3c-b: the signal track on the core

Protocol frozen 2026-10-29, before any signal driver, comparator or UVW
export was run. Status: **proposed**. Last part of phase 3 of the port plan
([stack-consolidation-feasibility.md](stack-consolidation-feasibility.md)
section 9.4), after the injection campaign, prospective track, actions stage,
trend chain test and the component predictor ([core-phase3c-a.md](core-phase3c-a.md)).
A reimplementation; under AGENTS.md not a scientific contribution, and no
archived result may change because of it.

## Question

Can the signal-guard track of the five-track campaign
([flagging-next-signal-verification.md](flagging-next-signal-verification.md),
archive [gain-tv-next-signal.json](results/gain-tv-next-signal.json)) run on
the Rust core, with no Measurement Set or container, and reproduce the
archive? The track solves two clean baselines (time-burst seeds 107 and 109),
freezes TRAIN-only forecasts and signal guards, measures retained clean arms,
injects the two known response templates into DATA, solves omitted-sky and
complete-diagnostic-sky arms, and fits the paired responses on the common
TEST cells: 9 solves in the archive.

## Design

`python/rangtoy/core_signal.py` replays `flagging_signal_guard.run` with
`core_workflow.core_solve` and keeps every decision function unchanged
(`make_shortlist`, `forecast_family`, `score_forecasts`, `train_signal_guard`,
`choose_slots`, `actual_acceptance`, `_evaluate`, `_rfi_diagnostics`, and the
response helpers `_jones_samples`, `_correct`, `linear_response`,
`_product_distance`). Three MS-bound steps become in-memory arithmetic that
reproduces what the MS round trip stores:

- **prediction** (`flagging_response._predict`): templates from
  `flagging_signal.spatial_templates` times the spectra, as now; the summed
  prediction from `core.predict_components`, which is bit-identical to
  africanus `wsclean_predict` (phase 3c-a);
- **injection** (`flagging_response._inject`): the complex128 sum of the
  complex64 DATA and the predicted delta, stored as complex64, and the
  actual delta as the complex128 difference of the stored values;
- **complete-sky model** (`flagging_response._complete_model`): the scalar
  prediction added to XX and YY in complex128 and stored as complex64.

## Inputs (frozen)

- `outputs/tv-next-wsl-20261029-01/inputs/cases/time-burst-seed{107,109}`:
  `state.npz`, `manifest.json`, `injection.json` and `injection.npz`. Read
  only.
- UVW of the same two cases: exported once, before the driver runs, with
  `examples/export_ms_arrays.py <case>/work.ms <out> UVW ANTENNA1 ANTENNA2 TIME`
  in `rang-flagging:local` into a fresh
  `outputs/core-phase3c-b-uvw-20261029-01/<case>` directory, timed and hashed.
  The driver checks that the exported row metadata equal the state's.
- Primary oracle: `raw_result` in `research/results/gain-tv-next-signal.json`.
  Secondary oracle: the host reproduction's
  `outputs/tv-next-wsl-20261029-01/experiments/signal/result.json`.

## Acceptance criteria (frozen)

1. **Decisions and counts, exact:** `status`, `common_TEST_samples`,
   `original_TEST_samples`, `lost_common_TEST_samples`, every `slots`,
   `accepted`, `nochange_signal_certified`, `mask_id`, `trial`, `sky`, `seed`,
   `guard_reasons`, `guard_pass`, acceptance booleans, fit `available`,
   `rank` and `sample_count`, `unsupported_original_TEST`, every
   `invalid_predictions` and `added_count`, the RFI truth diagnostics' counts,
   `actual_QC_solves` (9), `maximum_QC_solves` and
   `native_flagger_QC_solves`.
2. **Well-posed floats, 1e-9 relative** (absolute where the oracle is zero):
   solve metrics (TV values, scale, valid fraction, losses, added fraction),
   `fixed_baseline_edge_TV`, acceptance `objective`, every fit `flux_jy` and
   `condition`, the methods' `weighted_mse_proxy` and
   `unexplained_weighted_response_energy_fraction`,
   `response_fraction_vs_case_fixedG0`,
   `same_mask_Jones_product_relative_drift`, and the RFI diagnostics' floats.
3. **Differences, 1e-9 relative or 1e-12 absolute:** the reference fits'
   `weighted_mse_proxy` and `unexplained_weighted_response_energy_fraction`
   (about 1e-12, residuals of near-exact fits).
4. **Reported, not gated:** `visibility_closure_linf_jy` and
   `coefficient_closure_linf_jy`, which are rounding-level (about 1e-15 and
   1e-18 Jy) by construction.
5. **Excluded:** wall times, `configuration` (except that `seeds`, `grid`,
   `iterations`, `maximum_QC_solves`, `minimum_benefit`, `probe_jy`,
   `absolute_transfer_limit`, `sources` and `reference_hz` must be equal),
   `audit`, `acceptance_file_sha256`, `observed_allocated_bytes_before_result`,
   `imaging` and `limitations`.
6. **No side effects.** Inputs, the UVW export and the tracked tree unchanged;
   only the run directory is written.
7. **Cost (reported).** Wall time and peak RSS with `/usr/bin/time`, logged in
   `tool-timings.md`, next to the 2 min 39 s the reproduced track took inside
   the 435 s campaign.

The track is reported as passed only if criteria 1–3, 5 and 6 pass as
frozen; any failure is recorded with its numbers. Phase 3 is complete when
this passes, since injections, prospective, actions and trend already do.
