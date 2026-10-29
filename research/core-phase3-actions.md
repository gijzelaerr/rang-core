# Rang core, phase 3: the actions stage on the core

Protocol frozen 2026-10-29 in `87044be`, before any actions driver or
comparator code was written. Status: **implemented; measured: passes as
frozen against the archive; a labelled post-hoc comparator rule is needed
for the host reproduction**. Part of phase 3 of the port plan
([stack-consolidation-feasibility.md](stack-consolidation-feasibility.md)
section 9.4), after the injection campaign ([core-phase3.md](core-phase3.md))
and the prospective track ([core-phase3b.md](core-phase3b.md)). A
reimplementation; under AGENTS.md not a scientific contribution, and no
archived result may change because of it.

## Question

Can the patch-removal actions stage ([flagging-actions.md](flagging-actions.md),
archive [gain-tv-actions.json](results/gain-tv-actions.json)) run on the Rust
core with no Measurement Set or container and reproduce the archive? The stage
solves a baseline, removes 16 seeded candidate patches one at a time (16
solves), fits a ridge predictor of the normalised TV change and, if the model
proposes a mask, solves it once more.

## Design

`python/rangtoy/core_actions.py` replays `flagging_actions.run` with
`core_workflow.core_solve`. It reuses `candidate_patches`, `split_actions`,
`fit_action_model` and `proposal_from_model` unchanged and keeps the order and
arithmetic of the targets, the model fit, the proposal and the objective. It
reads the prepared state and manifest instead of unpacking the archive and
copying Measurement Sets, and replaces the flagged-MS audit with array checks.
`examples/compare_core_actions.py` compares with the archive using
`rangtoy.core_compare`; `examples/run_core_campaign.py` gains an `actions`
track.

## Inputs (frozen)

- `outputs/tv-flagging-actions-wsl-20261029-01/state.npz` and
  `manifest.json`: the host reproduction's seed-7 preparation of the SKA
  fixture (the archive path the reproduction used). Read only.
- Primary oracle: `research/results/gain-tv-actions.json`. Secondary oracle:
  the host reproduction's `result.json` and `model.json`.

## Acceptance criteria (frozen)

1. **Decisions and counts, exact.** `action_split`, every trial name,
   `selected` trial, `ridge_penalty`, `missing_labels`,
   `selected_training_actions`, `proposal_accepted`, `no_change`,
   `invalid_predictions`, `added_count` and non-float action metadata.
2. **Well-posed floats, 1e-9 relative** (absolute where the oracle is zero):
   baseline and action metrics (TV values, `fixed_support_tv`, scale, valid
   fraction, losses, `added_fraction`), the model's feature `center` and
   `scale`, and any `objective`.
3. **Differences, 1e-9 relative or 1e-12 absolute:** `normalized_tv_change`
   (a difference of nearly equal TVs, 7.6e-11 relative in the host
   reproduction), and everything fitted to it: `coefficients`,
   `predicted_changes`, `tuning` values, `validation_action_mse`,
   `test_action_mse` and `constant_predictor_test_mse`.
4. **Excluded:** wall times, paths, `date`, `run`, `provenance`, `audit`,
   `assessment`, `limitations` and configuration text. The configuration's
   `seed`, `action_count`, `iterations` and `ridge_penalties` must be equal.
5. **No side effects.** Inputs and the tracked tree unchanged; only the run
   directory is written.
6. **Cost (reported).** Wall time and peak RSS with `/usr/bin/time`, logged in
   `tool-timings.md`, next to the host reproduction's measured time (about
   6 min, STATE.md).

The stage is reported as passed only if criteria 1–5 pass as frozen; any
failure is recorded with its numbers.

## Measured result (2026-10-29)

Run `outputs/core-phase3-actions-20261029-01`, the first and only run of the
stage. The prepared `state.npz` and `manifest.json` were copied
byte-identically (SHA256 `84c26f85…`) into
`outputs/core-phase3-actions-inputs-20261029-01`, so that the side-effect
audit covers exactly the two inputs. Archive:
[core-phase3-actions.json](results/core-phase3-actions.json).

- **Against the archive, as frozen: pass.** 61
  exact fields equal, 102 floats within
  6.6e-15, 24
  differences within 1.8e-11 relative.
  The selection is the baseline (no change) as archived; the ridge model
  proposed no mask, so the stage made 17 solves.
- **Against the host reproduction, as frozen: 14 failures.** All are
  `actions[*].action.score`, a float in each action's metadata that the
  reproduction stores and the archive does not. The comparator classed it as
  exact, although criterion 1 covers only non-float metadata. The values agree
  to about 1.6e-14 relative.
- **Post-hoc** (labelled in the comparator): treating that float metadata as a
  float, the comparison against the host reproduction passes with
  206 exact fields, 214
  floats (worst 1.6e-14) and
  24 differences (worst
  5.8e-11). No solve was rerun; only the
  comparison.
- **Side effects:** inputs and `git status` unchanged; only `result.json`
  written.
- **Cost (reported):** 9.2 s and 234 MB in one process, against about 6 min
  for the host reproduction of the stage (STATE.md).
