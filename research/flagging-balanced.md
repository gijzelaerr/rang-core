# Geometry-balanced search

Protocol frozen on 2026-09-24 before outcomes in
[the concurrent experiment plan](flagging-concurrent.md). Implementation and
pure tests are being checked; actual measurements are scheduled by the root
orchestrator and must not be inferred from this proposed protocol.

Use the exact existing whole-rectangle TRAIN family: 16/32/64/128 aligned native
channel tiles wholly inside the experiment window, one/all unique integration
times, global/antenna-star/physical-baseline groups, at least eight samples and
no more than 2% of TRAIN. Protected/held-out holes remain unfilled. Reject an
oversized rectangle, never trim it or form unions. Duplicate geometries use the
existing first canonical alias; group balancing uses that canonical group and
never counts the same mask twice.

Freeze three six-slot rankings: two global, two antenna-star, two baseline;
empty groups do not donate slots. Residual and TV scores are exactly the
previous frozen formulas. Random ranking consumes seed137 once in group order
global/star/baseline, drawing without replacement from hash-sorted group lists.
Thus random masks are invariant to family order and score values. Each ranking
includes no-change. Shared masks reuse the same actual solve.

QuartiCal solves retain complex full2×2 G, identity initialization, two-time/
32-channel grid, 50 iterations, original native weights and disabled automatic
flags. All counterfactuals compare the baseline's fixed TV scale and edges.
Objective remains `TVfixed/TV0 + 2*f + .25*MSEvalidation/MSE0`, with <=2% additions
and <=1% validation degradation. Test losses and injection truth never choose
the action. All flag writes receive original-preserving backups. Exports check
exact flags/rows, DATA and every present WEIGHT/SIGMA column.

## Interfaces and fresh controls

`balanced_rank(candidates, mode='residual'|'tv'|'random', per_group=2,
random_seed=137)` returns the frozen slots. `run(run_dir, prepared_dir,
iterations=50)` creates fresh MS copies, checks original-state boundaries,
freezes rankings before solving, and exports one selected mask/MS per ranking.
Outputs follow the existing structured result schema for transfer-model labels.

`make_case(run_dir, prepared_dir, pattern, strength=10, seed=101,
occupancy=.005)` constructs fresh backed-up TRAIN-only additive contamination.
It accepts only time-burst/antenna-local and seeds101/103/105. The input must be
pristine: state and working DATA equal the immutable original DATA. Existing
injection semantics remain unchanged, including inverse-weight strength units,
coherent four-correlation phasors and seeded jitter. Requested occupancy need
not equal actual occupancy; exact values are recorded.

Construction archives truth separately; ranking/training consumes only
state/manifest/MS files, not injection metadata. Seed101/103/105 are fixed
training/validation/test case groups for the separate transfer estimator. The
fixed rankers may be measured on all groups, but test-case action labels never
fit or tune that estimator. All groups reuse one short four-antenna MeerKAT
L-band pointing observation, so new-seed generalization is not observation
transfer, signal/image validation or a state-of-the-art advantage.

## Execution

```sh
bash tools/flagging/run-balanced.sh outputs/fresh-balanced outputs/prepared-case
```

The wrapper performs stdlib namespace preflight before creating logs/caches,
reserves a fresh isolated log directory, mounts the checkout read-only and
outputs writable, disables runtime network access and uses the pinned suite
image. Direct Stimela recipes expose both `tv-flagging-balanced` and the separate
simulation constructor `tv-balanced-make-case` in
[tv-flagging-balanced.yaml](../recipes/tv-flagging-balanced.yaml).

Maintain the concurrent plan's three-worker limit and 8GiB disk reserve. Raw
observations/gains and failed/null checkpoints remain ignored, not deleted.
No measurement or performance/novelty claim exists until actual results and
preservation audits are archived.
