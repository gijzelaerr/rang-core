# history/: frozen campaign files the core no longer needs

Moved here on 2026-10-30 by big plan task P8
([research/p8-history.md](../research/p8-history.md), proposal in
[research/simplification-review.md](../research/simplification-review.md)
section 3 "P8"). Nothing here runs in a live chain: the Rust core
(`core/`, `rangtoy._core`, `python/rangtoy/core_*.py`, `recipes/core-*.yaml`
driven by `rang-core`) reproduces every archive these files produced, and
S1 re-ran each of those comparators before the move. Every file was moved
with `git mv` and is byte-identical to its last live version, so
`git log --follow history/<path>` shows its full history and the sha256 in
each campaign receipt still matches.

## What is here

| Directory | Was | Contents |
| --- | --- | --- |
| `recipes/` | `recipes/` | the 23 frozen Stimela2 recipes `tv-flagging*.yaml` |
| `tools/flagging/` | `tools/flagging/` | 8 Dockerfiles of the pinned `rang-flagging*:local` images, 3 `requirements.lock`, 16 `run-*.sh` wrappers, 4 `fetch-luno-*.sh`, `preflight.py`, `sky/verify_prediction.py` |
| `python/` | `python/rangtoy/` | the six recipe-only modules `flagging_{concurrent,parallel,provenance,public,transfer,uncertainty}.py` (they used package-relative imports as `rangtoy.*` submodules; here they are on no import path) |
| `tests/` | `tests/` | the tests of those six modules, `test_flagging_preflight.py`, and three test functions cut verbatim from live test files (each file names its origin) |

Not collected by pytest (`testpaths = ["tests"]`) and excluded from ruff
(`pyproject.toml`): the files are frozen and hashed, and the tests import
modules that are no longer in the package.

## Which archive each item produced

| Item | Research note | Archive (`research/results/`) |
| --- | --- | --- |
| `tv-flagging.yaml`, `run-pilot.sh`, base `Dockerfile` and lock | [flagging.md](../research/flagging.md) | `gain-tv-flagging.json` |
| `tv-flagging-injections.yaml`, `run-injections.sh` | [flagging-injections.md](../research/flagging-injections.md) | `gain-tv-injections.json` |
| `tv-flagging-sky.yaml`, `sky/` | [flagging-sky.md](../research/flagging-sky.md) | `gain-tv-sky.json` |
| `tv-flagging-comparators.yaml`, `comparators/` | [flagging-comparators.md](../research/flagging-comparators.md) | `gain-tv-comparators.json` |
| `tv-flagging-actions.yaml` | [flagging-actions.md](../research/flagging-actions.md) | `gain-tv-actions.json`, `gain-tv-actions-injected.json` |
| `tv-flagging-parallel.yaml`, `parallel/`, `run-parallel.sh`, `flagging_parallel.py` | [flagging-parallel.md](../research/flagging-parallel.md) | `gain-tv-parallel.json` |
| `tv-flagging-caracal.yaml`, `run-caracal.sh` | [flagging-caracal.md](../research/flagging-caracal.md) | `gain-tv-caracal.json` |
| `tv-flagging-structured.yaml`, `run-structured.sh` | [flagging-structured.md](../research/flagging-structured.md) | `gain-tv-structured.json` |
| `tv-flagging-balanced.yaml`, `run-balanced.sh` | [flagging-balanced.md](../research/flagging-balanced.md) | `gain-tv-balanced.json` |
| `tv-flagging-uncertainty.yaml`, `flagging_uncertainty.py` | [flagging-uncertainty.md](../research/flagging-uncertainty.md) | `gain-tv-uncertainty.json` |
| `tv-flagging-public.yaml`, `run-public.sh`, `flagging_public.py` | [flagging-public-ingestion.md](../research/flagging-public-ingestion.md) | `meerkat-public-ingestion.json`, `meerkat-public-pilot.json` |
| `tv-flagging-signal.yaml`, `run-signal.sh` | [flagging-signal.md](../research/flagging-signal.md) | `gain-tv-signal.json` |
| `tv-flagging-transfer.yaml`, `flagging_transfer.py` | [flagging-transfer.md](../research/flagging-transfer.md) | `gain-tv-transfer.json` |
| `tv-flagging-concurrent.yaml`, `run-concurrent.sh`, `flagging_concurrent.py` | [flagging-concurrent.md](../research/flagging-concurrent.md) | `gain-tv-concurrent.json`, `-audit.json` |
| `tv-flagging-influence.yaml`, `run-influence.sh` | [flagging-influence.md](../research/flagging-influence.md) | `gain-tv-influence.json`, `-audit.json` |
| `tv-flagging-response.yaml`, `response/`, `run-response.sh` | [flagging-response.md](../research/flagging-response.md) | `gain-tv-response.json`, `-audit.json` |
| `tv-flagging-equivariance.yaml`, `run-equivariance.sh` | [flagging-equivariance.md](../research/flagging-equivariance.md) | `gain-tv-equivariance.json`, `-audit.json` |
| `tv-flagging-next.yaml`, `next/`, `run-next.sh` | [flagging-next-results.md](../research/flagging-next-results.md), [flagging-next-summary.md](../research/flagging-next-summary.md) | `gain-tv-next.json`, `gain-tv-next-runtime.json` and the track archives below |
| `tv-flagging-trend.yaml` | [flagging-trend.md](../research/flagging-trend.md) | `gain-tv-next-trend.json` |
| `tv-flagging-prospective.yaml` | [flagging-next-prospective-verification.md](../research/flagging-next-prospective-verification.md) | `gain-tv-next-prospective.json` |
| `tv-flagging-signal-guard.yaml` | [flagging-next-signal-verification.md](../research/flagging-next-signal-verification.md) | `gain-tv-next-signal.json` |
| `tv-flagging-provenance.yaml`, `flagging_provenance.py` | [flagging-supported-provenance.md](../research/flagging-supported-provenance.md) | `gain-tv-next-provenance.json` |
| `tv-flagging-imaging.yaml`, `imaging/`, `next-imaging/`, `run-imaging.sh` | [flagging-imaging.md](../research/flagging-imaging.md) | `gain-tv-next-imaging.json`, `-invalid-basis.json`, `-audit.json` |
| `fetch-luno-probe.sh`, `fetch-luno-text.sh` | [flagging-luno-candidate.md](../research/flagging-luno-candidate.md) | `meerkat-luno-candidate.json` |
| `fetch-luno-support.sh` | [flagging-luno-support.md](../research/flagging-luno-support.md) | `meerkat-luno-support.json` (live replacement: `core_fetch`, task G) |
| `fetch-luno-solve.sh`, `run-luno-solve.sh` | [flagging-luno-solved.md](../research/flagging-luno-solved.md) | `meerkat-luno-solved.json` |

The core replacement and comparator of each superseded stage are in
`simplification-review.md` section 1.4.

## Re-running a frozen campaign

Do not run anything from `history/`: the receipts hash files at their
original paths, and three frozen modules that stay in the package still name
those paths (`flagging_workflow.py` hashes `recipes/tv-flagging.yaml` and
`tools/flagging/{Dockerfile,requirements.lock}`; `flagging_next.py` globs
`recipes/tv-flagging*.yaml` and `tools/flagging/` in `source_receipts()` and
imports `rangtoy.flagging_provenance` for its provenance track;
`flagging_sky.py` runs `tools/flagging/sky/verify_prediction.py`). Instead:

1. Check out the commit the campaign's receipt records, or `43dc3c7`, the
   last commit with every file in place:
   `git worktree add ~/Worktrees/rang/history-rerun 43dc3c7`.
2. Use the pinned images, built from `tools/flagging/` there:
   `rang-flagging:local` (base: Rust 1.93 kernels and Python 3.12 with the
   lock), then `rang-flagging-comparators`, `-sky`, `-response`, `-next`,
   `-imaging`, `-next-imaging` and `-parallel` (each Dockerfile's `FROM`
   line names its parent; rebuild in that order). The frozen campaigns ran in
   exactly the local builds; a rebuild re-resolves nothing beyond the locks but
   is a new image ID, which the receipt records.
3. Run the campaign's `tools/flagging/run-*.sh` wrapper as its research note
   says (each wrapper runs `preflight.py` first and needs a fresh
   `outputs/` run directory). Recipes driven on the host need Stimela in a
   Python 3.13 venv (task I, [core-i-imaging-replay.md](../research/core-i-imaging-replay.md));
   the host's Python 3.14 runs the core only.
4. To run the moved tests, run `pytest` in that checkout; they passed there
   (739 tests, S1).
