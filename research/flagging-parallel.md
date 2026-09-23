# Parallel MeerKAT L-band flagging diagnostics

The user authorized four parallel workstreams on 2026-09-23. The baseline
implementation and negative pilot findings were committed as `35e763b` after
full local checks and a fresh complete Stimela2 replay. No push was requested.

[The suite recipe](../recipes/tv-flagging-parallel.yaml) initializes an exclusive
output root, scatters four independent branches with native Stimela2
`for_loop.scatter=4`, then gathers their statuses and compact results. Each
branch owns its writable MS copies, snapshots and Numba cache. No worker writes
the raw fixture, another branch's data or immutable `original.ms`. All original
cell and row flags remain lower bounds; only additional flags may decrease.
Branch failures are archived without stopping the other workers; the gather
step reports failure after retaining their checkpoints. The experimental
functions run actual QuartiCal complex 2x2 inner solves.

The workstreams are:

- [Seeded injection/oracle controls](flagging-injections.md): compare clean,
  contaminated, injection-only oracle and TV-policy solves without using
  injection truth/oracle to train the policy.
- [Calibrator sky comparison](flagging-sky.md): verified prediction of SARAO's
  full apparent-scale L-band catalog, keeping special pointing-scan limitations.
- [Established flagger comparisons](flagging-comparators.md): native QuartiCal
  residual MAD and the genuine Tricolour SumThreshold kernel, frozen masks and
  matched calibration settings. This is not the full production Tricolour strategy.
- [Measured patch-action learning](flagging-actions.md): fit a small TV-change
  predictor to counterfactual full-Jones solves, with withheld action labels.

Their code can develop and run concurrently. Scientific assessment of the
learned policy depends on the injection/oracle controls; independent-scanning,
image-quality and faint-source recovery validation remain later work.

## Environment and inputs

Build images in dependency order using the checked-in Dockerfiles:

```sh
docker build --platform linux/amd64 -f tools/flagging/Dockerfile -t rang-flagging:local .
docker build --platform linux/amd64 -f tools/flagging/sky/Dockerfile -t rang-flagging-sky:local .
docker build --platform linux/amd64 -f tools/flagging/comparators/Dockerfile -t rang-flagging-comparators:local .
docker build --platform linux/amd64 -f tools/flagging/parallel/Dockerfile -t rang-flagging-parallel:local .
```

QuartiCal/Stimela stay in the original pinned Python3.12 environment. Crystalball
is isolated under `/opt/sky` because its psutil requirement conflicts with
Stimela2.1.4; Tricolour is isolated under `/opt/tricolour` because it requires
Numba0.60 rather than the calibration environment's Numba0.67. All packages use
public PyPI; no tool silently downgrades the shared solver. Runtime has no
network access, the checkout is read-only and generated outputs alone are
writable. amd64 emulation on this ARM Mac is not a native performance benchmark.

Inputs must already be downloaded and verified: the original pinned
`outputs/ska-pointing/outer_scans.zip` and the official apparent-scale
`outputs/flagging-sky-inputs/fitted.PKS1934.LBand.wsclean.cat.txt`.
Their SHA256s are verified before output creation. Model provenance and
prediction conventions are documented in the sky report; no primary-beam
correction is silently applied to this already apparent-scale catalog.

```sh
bash tools/flagging/run-parallel.sh outputs/tv-parallel-new \
  outputs/flagging-sky-inputs/fitted.PKS1934.LBand.wsclean.cat.txt
```

Choose a new run directory every time. The suite records configuration, input
hashes, branch status and branch result JSON; detailed solver outputs stay in
each branch. Individual recipes remain available for debugging or a smaller
experiment. The concurrent suite is a diagnostics recipe, not a trained model
validated for deployment to arbitrary observations.

## Completed concurrent pilot

`outputs/tv-flagging-parallel-01/` passed the full Stimela2.1.4 recipe. All four
workers started at 18:21:30 UTC on 2026-09-23; sky, actions, comparators and
injections finished at 18:23:32, 18:24:17, 18:24:47 and 18:28:32 respectively.
The gather reported all four complete, with no failures. This demonstrates
actual overlap, not merely parallel schema validation. Total elapsed time was
422.8 seconds under amd64 emulation; it is not a matched-cost speedup claim.

The concurrent replay reproduced the individual pilots' main findings:

- Injection-only oracle removal benefits the guarded objective for the strong
  time-burst case, but the actual TV policy selects no-change in all six cases.
- The full SARAO catalog improves validation/test MSE about 1.20%/0.98% relative
  to its primary-only control while slightly increasing TV. Prediction was
  independently verified; physical pointing-scan beam applicability was not.
- Genuine MAD/SumThreshold proposals sometimes lower TV while worsening
  held-out prediction, exceeding the flag budget or losing fixed TV support.
  The clean comparison selects no-change; packaged dilation's sparse-holdout
  failure remains an explicit negative control, not a production-tool verdict.
- The small patch-action ridge learner does not beat its constant control on
  the 16-action clean or contaminated pilot and selects no additional flags.

Compact configuration, timings and measured branch results are archived in
[gain-tv-parallel.json](results/gain-tv-parallel.json). These results do not
establish imaging quality, independent-scan transfer or state-of-the-art gains.

## Preservation and final verification

Prepared-input validation now checks the actual immutable original MS, rather
than trusting saved flags alone: original cell/row flags, native weights,
working DATA/model, MeerKAT L-band metadata, coordinates, disjoint eligible
splits and manifest channel/count/grid coherence. Nested input/output paths
are rejected before output creation. Recorded injections may change working
DATA, never authoritative original flags or weights.

The full concurrent pilot preceded these guard additions. Separate fresh gated
action/comparator Stimela smokes passed; their configuration records the
initial helper version. A subsequent entirely read-only, network-disabled audit
with final helper SHA256
`8c1878cdaa3259ca2e5416b78df2a89544a87cea86aa1b47099eaf4b3d96e8ab`
validated 24 completed prepared inputs, including every concurrent branch and
injection case. Original/source digests, exported DATA/native weights and
protected flags passed. Deliberate in-memory saved-flag tampering was rejected;
no actual MS was altered. This final audit is not a retrospective solver rerun.

Full local checks passed release build, 14 Rust and 171 Python tests, Clippy,
Rust/Ruff formatting, Ruff lint, byte compilation, shell syntax and result-JSON
validation. Container builds, dependency checks and actual Stimela executions
were performed locally; all six final recipe schemas passed Stimela dry-runs
with logs confined to disposable container tmpfs. Code/results and the independent
preservation audit
are backed up under `outputs/flagging-backups/20260923-parallel-final/`.

Parallel-loop semantics follow the installed schema and
[Stimela2 documentation](https://stimela.readthedocs.io/en/latest/fundamentals/anatomy.html).
