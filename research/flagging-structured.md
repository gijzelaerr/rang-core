# Structured gain-TV action search

Measured 2026-09-23 on the unmodified real fixture and all six archived artificial
RFI cases. Seven completed runs, 101 actual QuartiCal solves including baselines.
[Compact archive](results/gain-tv-structured.json) records every evaluated action,
frozen rankings, configuration/source hashes, selections, audits and post-selection
injection diagnostics. This is counterfactual selection, not a fitted transfer model.

Paths (2026-10-30, task P8): the frozen `tv-flagging*` recipes,
`tools/flagging/` and the recipe-only modules named here now live under
[`history/`](../history/README.md); this text keeps the paths it was written
with.

## Frozen matched experiment

Implemented [proposal generator](../python/rangtoy/flagging_structured_proposals.py),
[actual-solve runner](../python/rangtoy/flagging_structured.py) and
[Stimela2 recipe](../recipes/tv-flagging-structured.yaml). For example:

```sh
bash tools/flagging/run-structured.sh outputs/tv-structured-new outputs/tv-flagging-actions-01
```

Before any run, freeze one/all integration times, aligned 16/32/64/128-channel
tiles, global/antenna-star/single-baseline groups, eight minimum TRAIN samples,
and the 2% training flag budget. Whole eligible rectangles preserve original
and held-out holes; reject oversized masks, never trim them. Both rankings use
the identical 23,329-mask family: 39,600 geometries, 15,687 under-minimum and
179 over-budget rejections, 405 duplicate aliases. Scores use training values only:

- Residual: mean positive robust, whitened residual z.
- TV-conditioned: mean positive z multiplied by
  `1+clip(TV/median_positive_training_TV,0,5)`.

Each ranking gets eight candidates with deterministic hash ties. Shared masks
reuse one actual solve; evaluate 11–16 distinct actions per case. Both methods
select with the same full2×2 complex gain-TV objective, not test loss:
`TV_fixed/TV0 +2*added_fraction +.25*validation_MSE/MSE0`.
Retain baseline scale/support, original weights, fixed gain grid and identity
initialization. Require retained TV edges, ≤2% additions and ≤1% validation
degradation. Include no-change; accept only a strict objective improvement.
Never combine rectangles or use injection truth to rank/select/tune.

## Results and limits

Both rankings choose no-change for the unmodified scan, both narrowband cases,
weak time burst and weak antenna-local case. Two small changes are selected:

| Case / ranking | Added TRAIN samples | Known injection recovery | Objective | TV change | Validation MSE change | Test MSE change |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Strong time burst / residual | 11 | 11/380 (2.89%) | 1.249904895 | −0.03272% | −0.02655% | −0.01985% |
| Strong antenna-local / TV | 8 | 0, all outside known injection | 1.249931062 | −0.03115% | +0.01021% | −0.00949% |

No-change objective is 1.25. Other ranking in each row chooses no-change. The
time-burst beneficial action is absent from the TV-conditioned top eight. The
antenna-local TV choice improves the objective but recovers none of its known
injection; outside-injection samples may contain pre-existing real corruption
and are not proven false positives. Tiny within-scan prediction changes with
one injection seed establish neither significance nor signal/image improvement.

All 112 ranked slots across the two methods/seven cases are single-baseline
actions. Global and antenna-star proposals exist but the mean-score ranking
never tests them. This is a measured proposal-selection limitation, not proof
that shared morphology is ineffective. The original strong time-burst oracle
opportunity is mostly still missed. Larger geometry alone and this multiplicative
TV-map heuristic do not demonstrate reliable RFI recovery or a TV-guidance advantage.

All original flags/rows, source digests, DATA, native weights and TRAIN-only export
audits pass. Each method exports its own copied flagged MS; the main work copy
ends at the TV choice, never changes an original observation. Test losses are
reported after selection and never affect it. Post-selection diagnostics alone
decode injection labels; source-integrity digests also hash their raw file bytes.

## Reproducibility and integration findings

Measured module source is exactly reconstructible from the committed runner by
the single audit-key replacement recorded in the archive and verified against
every run's source hash. After measurements, rename `no_truth_read` to
`no_truth_decoded_or_used_for_selection`: hashing a label file is a byte read,
but not decoded truth or a training/selection input. Raw measured audits remain
preserved and annotated rather than silently rewritten.

The first two runs shared outer Stimela logs/profiling because a fixed recipe
log directory overrode the wrapper setting. Actual MS, config, QC logs, masks,
checkpoints and exports were isolated. Shared outer logs are backed up; only
the recipe log-dir default was removed, and fresh dry-runs plus the remaining
five executions confirm unique wrapper-selected log paths. Do not use the
shared profiling or amd64 emulation for performance claims.

Post-publication hardening: wrappers now perform read-only resolved-path
preflight before any logs/cache/Docker startup and reserve a fresh log directory
exclusively. Nested sources, symlink escapes and existing/dangling log paths
reject without modifying inputs. Nonfinite/negative diagnostic inputs cannot
pass objective guards; all 98 recorded action/native scores are unchanged.
The [separate artifact check](results/gain-tv-artifact-audit.json) verifies all
seven structured controls and all present DATA/weight/SIGMA columns, not just
self-reported flags. No new scientific run is claimed for these edge-case fixes.

Next discriminating tests: calibrated aggregate/coherence evidence or frozen
group-balanced search budgets, uncertainty-aware TV and science-signal controls,
then [normal primary-calibrator transfer](flagging-public-data.md). Freeze new
settings before new seeds/scans; these results must not become their test set.
No independent-observation transfer, imaging/flux validation or SOTA advantage.

Paths: the frozen modules named here moved to [`history/`](../history/README.md)
on 2026-10-30 (task P11); their live definitions are in the `core_*` extracts
of [p11-extract.md](p11-extract.md).
