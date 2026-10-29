# Rang core, phase 3: the injection campaign on the core

Protocol frozen 2026-10-29 in `a34aba5`, before any phase 3 driver or
comparator code was written. Status: **implemented; measured** (see the
measured result and the labelled post-hoc extension below). Phase 3 of the port plan in
[stack-consolidation-feasibility.md](stack-consolidation-feasibility.md)
section 9.4. A reimplementation; under AGENTS.md it is not a scientific
contribution, and no archived result may change because of it.

## Question

Can the injection campaign ([flagging-injections.md](flagging-injections.md),
archive [gain-tv-injections.json](results/gain-tv-injections.json)) run
entirely on the Rust core, with no Measurement Set, no container and no
QuartiCal subprocess, and reproduce every archived decision and number?

The campaign makes 49 solves: one clean reference, and for each of six cases
(narrowband, time-burst and antenna-local at strengths 3 and 10) a
contaminated solve, an injected-mask oracle solve and the deduplicated
3 × 3 grid of TV-guided policy trials, selected by the frozen objective.

## Design

- A new module `python/rangtoy/core_workflow.py` provides `core_solve`, which
  returns the same metrics, TV dictionary, residuals and guidance as
  `flagging_workflow.solve`, and the same diagnostics keys as its
  `diagnostics.npz`. It differs only in how gains are obtained: the
  solve-time FLAG and FLAG_ROW are the arrays `set_flags` would write
  (original flags and rows, holdouts, autocorrelations and out-of-window
  channels, plus the candidate additions, through `protected_flags`), the
  gains come from `core.solve_complex`, and residuals and split losses come
  from the phase 1 fused pass.
- A new module `python/rangtoy/core_injections.py` replays
  `flagging_injections.run` with `core_solve`. It reuses `make_injection`,
  `policy_mask`, `residual_features`, `fixed_support_tv`, `injection_scores`
  and `reference_distance` unchanged and keeps the selection logic of
  `_train_policy` verbatim. It reads the prepared clean state and manifest of
  the host reproduction instead of unpacking and copying an MS, and
  regenerates every injection from its seed.
- The frozen campaign modules are not edited. Writing `flagged.ms` is an
  edge step and is not part of this gate; the final additions are compared as
  arrays.
- `examples/compare_core_injections.py` compares the core result with the
  archive by the field classes below and writes a receipt.

## Inputs (frozen)

- Prepared clean input: `outputs/tv-injections-wsl-20261029-01/state.npz` and
  `manifest.json` (seed 7 splits, channels 1024–3072, grid 2 × 32), which the
  host reproduction built with the unchanged frozen recipe (STATE.md).
- Per-case saved injections: `cases/<case>/injection.npz`, `injection.json`
  and `state.npz` in the same directory, used only to check that the
  regenerated injections are identical.
- Oracle: `research/results/gain-tv-injections.json`. The host reproduction's
  `result.json` is compared as a secondary oracle and reported.

## Acceptance criteria (frozen)

1. **Injections.** Every regenerated mask, delta and DATA array equals the
   saved one exactly, and every `injection` metadata field equals the archive
   (strings and integers exactly, floats to 1e-12 relative).
2. **Decisions.** For every case, the selected trial, every candidate's policy,
   trial name, duplicate-mask fingerprint and accepted flag, and every
   `added_count`, `invalid_predictions`, `recovered_injected_samples`,
   `additions_outside_injections` and `unsupported_clean_gain_bins` equal the
   archive exactly. A policy flip is a failure of this criterion, not a reason
   to retune anything.
3. **Well-posed floats.** Every TV value (`tv`, `raw_tv`, `time_tv`,
   `frequency_tv`, `fixed_clean_support_tv`, `fixed_contaminated_support_tv`
   and the ratio), `scale`, `valid_gain_fraction`, every split loss, every
   objective, `added_fraction`, `injection_recall` and
   `outside_injection_train_fraction` agrees with the archive to 1e-9
   relative (absolute where the archived value is zero).
4. **Distances to clean.** `polar_gauge_gain_mse_to_clean` and both
   `weighted_prediction_mse_to_clean` values are differences of nearly equal
   quantities. They must agree to 1e-9 relative, or to 1e-12 absolute in their
   own units, whichever is looser. This is fixed now, before the run, following
   the phase 1 lesson.
5. **Excluded fields.** Wall times (`seconds`, `seconds_total`), paths,
   manifest digests of MS trees, `data_backup_sha256`, MS-specific audit
   flags and the archive-only fields (`artifact_directory`,
   `implementation_provenance`, `measured_summary`) are not compared, as in
   STATE.md's reproduction tables. `post_selection_candidate_recovery` is
   compared under criteria 2 and 3.
6. **Margins.** The receipt reports, for every candidate, its objective minus
   the best objective before it, so that any decision difference can be
   traced. Reported, not gated.
7. **No side effects.** The prepared inputs and the tracked tree are
   unchanged; the run writes only into its fresh `outputs/` directory.
8. **Cost (reported, not gated).** Wall time and peak RSS of the core
   campaign with `/usr/bin/time`, logged in `tool-timings.md` next to the
   296 s host reproduction.

A failure is recorded here with its numbers and is not hidden. The phase is
reported as passed only if criteria 1–5 and 7 pass as frozen.

## Measured result of the frozen run (2026-10-29)

Run `outputs/core-phase3-20261029-01` with the driver and comparator as first
written. The comparator was written after this protocol was frozen and before
the run; it had not been committed. Every compared field passed:

| Class | Compared | Worst relative difference |
| --- | ---: | ---: |
| exact decisions and counts (criterion 2) | 858 | 0 |
| well-posed floats (criterion 3) | 928 | 1.3e-14 |
| injection metadata floats (criterion 1) | 24 | 0 |
| distances to clean (criterion 4) | 54 | 1.5e-14 |

All six regenerated injections equal the saved masks, deltas, DATA arrays and
metadata, and all six selected policies equal the archive (no change in every
case, as archived). The side-effect audit passed: 3978
prepared files and `git status` were unchanged, and only `result.json` was
written.

The comparator nevertheless exited with 18 failures, all of one kind: three
per-case fields of the archive (`diagnostic_oracle_objective`,
`no_change_objective`, `oracle_was_used_for_selection`) were missing from the
core result. They are archive-only summaries. The frozen `run()` never writes
them, the host reproduction's `result.json` lacks them, and no code in the
repository produces them. Criterion 5 excludes archive-only fields "as in
STATE.md's reproduction tables" but enumerated only three top-level ones, so
the comparator's exclusion list was incomplete. This is recorded as a gap in
the frozen comparator, not hidden.

## Post-hoc extension (after the frozen run)

The core driver now also writes the three fields, with these definitions: the
no-change objective is the baseline objective (always 1.25); the diagnostic
oracle objective is the selection objective of the injected-mask oracle solve
on the contaminated support; the oracle is never used for selection. The
comparator treats the two objectives under criterion 3 and reads candidate
recovery from a campaign's sibling `candidate-recovery.json`, so the host
reproduction can be compared too. Both changes are labelled post-hoc in the
code.

Run `outputs/core-phase3-20261029-02` with the committed code. Archive:
[core-phase3.json](results/core-phase3.json).

- Against the archive: 0 failures; 864 exact
  fields, 940 floats (worst
  1.3e-14), 54
  distances (worst 1.5e-14). The oracle
  objectives match the archive within 1e-9, which confirms their definition.
- Against the host reproduction: 0 failures.
- Margins: of 36 policy trials, 16 were admissible;
  the closest lost to the incumbent by 5.2e-03, eleven orders of
  magnitude above the agreement level. The other 20
  were rejected by the validation guard or lost support.
- Side effects: as in the frozen run.

**Cost (reported).** The whole campaign, 49 solves, ran in one process with no
Measurement Set and no container in 25.9 s (frozen run) and 24.6 s (post-hoc
run), peaking at 708 MB and 738 MB. The host reproduction of the same stage,
through Stimela, containers and 49 QuartiCal subprocesses, took 296 s. Peak
memory is high because the driver keeps every trial's diagnostics of a case
in memory; it can be cut by keeping only the selected one.

Phase 3 is reported as "implemented; measured: the frozen comparator reported
18 archive-only fields as missing and every compared field passed; post-hoc,
with those fields, it passes against the archive and the host reproduction".
