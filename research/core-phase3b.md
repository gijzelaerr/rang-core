# Rang core, phase 3b: the prospective track on the core

Protocol frozen 2026-10-29, before any phase 3b driver or comparator code was
written. Status: **proposed**. Second part of phase 3 of the port plan
([stack-consolidation-feasibility.md](stack-consolidation-feasibility.md)
section 9.4); [phase 3](core-phase3.md) moved the injection campaign. A
reimplementation; under AGENTS.md not a scientific contribution, and no
archived result may change because of it.

The signal track needs component prediction (Gaussian and point sources
through codex-africanus, UVW from the MS) for its known templates, so it moves
to phase 3c, after a Rust predictor exists.

## Question

Can the prospective track of the five-track campaign
([flagging-next-prospective-verification.md](flagging-next-prospective-verification.md),
archive [gain-tv-next-prospective.json](results/gain-tv-next-prospective.json))
run on the Rust core with no Measurement Set or container and reproduce every
archived decision and number? The track makes 54 solves: three baselines
(clean, time-burst seeds 107 and 109) and every shortlisted action (18, 17
and 16), with TRAIN-only forecasts frozen before any action is measured.

## Design

`python/rangtoy/core_prospective.py` replays `flagging_prospective.run` with
`core_workflow.core_solve`. It imports and reuses unchanged
`make_shortlist`, `forecast_family`, `score_forecasts`, `choose_action`,
`score_control`, `fixed_support_tv` and the `MARGIN` constant, keeps the
ordering of forecasting, scoring, confirmation and measurement, and keeps the
baseline diagnostics in memory instead of reading `diagnostics.npz`. It
replaces MS copies, the flag export and MS audits with array checks. The
frozen campaign modules are not edited.

## Inputs (frozen)

- `outputs/tv-next-wsl-20261029-01/inputs/cases/{clean,time-burst-seed107,time-burst-seed109}`:
  `state.npz`, `manifest.json` and, for the two seeds, `injection.npz`, as
  built by the host reproduction's `initialize` step. Read only.
- Primary oracle: `raw_result_projection` in
  `research/results/gain-tv-next-prospective.json`.
- Secondary oracle: the host reproduction's
  `outputs/tv-next-wsl-20261029-01/experiments/prospective/result.json`, which
  also carries the per-bin response audits.

## Acceptance criteria (frozen)

1. **Decisions and counts, exact.** Candidate order and mask identifiers,
   candidate metadata other than floats, `confirmation_ids`, every
   `guard_pass`, `reason` and `guard_reasons`, every selected `mask_id`,
   `no_change`, `flags_added`, `known_injection_recall`,
   `outside_known_injection`, the per-case and total `actual_QC_solves` (54)
   and `future_two_confirmation_QC_solves`, and every `invalid_predictions`
   and `added_count`. A changed decision fails this criterion; nothing is
   retuned.
2. **Well-posed floats, 1e-9 relative** (absolute where the oracle is zero):
   baseline and action metrics (TV values, scale, valid fraction, losses,
   added fraction), `fixed_support_tv`, every `objective`,
   `predicted_fixed_tv`, `predicted_validation_MSE`, `predicted_objective`,
   `test_MSE`, and candidate floats (`added_fraction`, `residual_score`,
   `tv_score`, metadata `time`).
3. **Differences, 1e-9 relative or 1e-12 absolute:** `predicted_benefit` and
   `predicted_cost_removed_benefit`, which are 1.25 minus an objective.
4. **Response audits (secondary oracle).** Ranks, `native_status`,
   `bin_id` and `guard_pass` exact; `largest_curvature`,
   `smallest_retained_curvature`, `condition`, `damping` and
   `max_relative_step` to 1e-9 relative. `baseline_projected_score_norm` and
   `gauge_null_relative` are rounding-level quantities at a converged solution
   (phase 1, criterion 4) and are reported, not gated.
5. **Excluded:** wall times (`seconds`, `native_response_seconds`,
   `full_training_normals_seconds`), `allocated_bytes`, MS audits, and
   configuration fields naming paths, digests, images or runtimes. The
   configuration's `iterations`, `grid`, `maximum_action_confirmations`,
   `maximum_actual_QC_solves`, `minimum_benefit` and `test_or_truth_selects`
   must be equal.
6. **Margins (reported).** For every forecast, its predicted benefit minus
   `MARGIN`; for every measured action, `1.25 - MARGIN` minus its objective.
7. **No side effects.** Inputs and the tracked tree unchanged; only the run
   directory is written.
8. **Cost (reported).** Wall time and peak RSS with `/usr/bin/time`, logged in
   `tool-timings.md`, next to the 6 min 23 s the reproduced track took inside
   the 435 s campaign.

The phase is reported as passed only if criteria 1–5 and 7 pass as frozen;
any failure is recorded with its numbers.
