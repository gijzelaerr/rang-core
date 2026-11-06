# W5: the Stimela recipes call the commands

Task W5 of [finish-plan.md](finish-plan.md): "The Stimela recipes call the new
commands"; gate "One recipe runs the chain; research recipes are marked as
such". Branch `fp-w5-stimela` from main `02024bd`. The commands are W2's
`rang-core flag`, `calibrate`, `apply` and `image`
([w2-commands.md](w2-commands.md)), with C2e's K, G, B, A and F terms
([c2e-calibrate.md](c2e-calibrate.md)) and W3's chunking
([w3-chunking.md](w3-chunking.md)).

Status: **proposed** (this protocol is committed before any run).

## 0. What the recipes were at `02024bd`

`recipes/` held seven files. None calls a `rang-core` command on a
Measurement Set (MS):

| File | What it runs |
| --- | --- |
| `core-cabs.yaml` | two shared cabs, `rang.core_cli.environment` and `rang.core_cli.compare` (the archive comparator) |
| `core-injections.yaml`, `core-actions.yaml`, `core-prospective.yaml`, `core-signal.yaml`, `core-trend.yaml` | the frozen phase 3 campaigns replayed on the Rust core from prepared states, with no MS, each compared with its archive |
| `core-imaging.yaml` | task I's fifteen archived dirty inversions from the archived checkpoints and backup MSs, compared with the archive |

All six stage recipes replay a frozen campaign against an archive, so all six
are research recipes, `core-actions` and `core-imaging` included. Rewriting
any of them to call `rang-core flag ... image` would break the comparison it
exists for. They stay as they are, marked as research (section 1). The brief
listed `core-actions` and `core-imaging` among the recipes to change; this is
recorded for the coordinator.

## 1. Design (proposed)

- **`recipes/rang-cabs.yaml`** (new): one cab per command, `rang-flag`,
  `rang-calibrate`, `rang-apply` and `rang-image`. Each is a binary cab whose
  command is the console script, `rang-core flag` and so on. Stimela therefore
  runs exactly the command a user types, with its receipt, thread pinning and
  exit status. A python-flavour cab calling `core_pipeline` in process would skip
  `core_cli.main`. Inputs: `config` and `ms`, positional, in that order;
  `run-dir` (`--run-dir`) and `force` (`--force`, a flag).
- **`recipes/rang-chain.yaml`** (new): recipe `rang-chain`, inputs `config`,
  `ms` and optional `run-dir`, steps `flag`, `calibrate`, `apply`, `image`, each
  one command on the same configuration, MS and run directory.
- **Research marker.** Every file in `recipes/` starts with a line
  `# rang-recipe: research` or `# rang-recipe: user`. The six stage recipes and
  `core-cabs.yaml` are research; their recipe `info:` also starts with
  `Research recipe:`. `rang-cabs.yaml` and `rang-chain.yaml` are user. A test
  checks the marker on every file, with no Stimela or YAML import (as the
  existing recipe tests), and checks that the user cabs' inputs match the
  arguments of the four commands.
- **Docs.** `docs/gen_cli.py` (and so `docs/cli.md`), `docs/installation.md`
  and the README say which recipes are research and how to run the chain recipe.
- **Not changed:** `python/rang/core_pipeline.py` and `core_config.py` (C6w is
  wiring the polarisation terms there), the research recipes' steps, every cab
  of `core-cabs.yaml`.

## 2. Environment

- `.venv` (Python 3.14, the check-all venv) and `.venv313` (uv-managed Python
  3.13.16, `-e .[recipes,casacure,imaging,test]`, so `stimela==2.1.4` from
  public PyPI).
  Stimela 2.1.4's native backend fails on Python 3.14
  ([core-i-imaging-replay.md](core-i-imaging-replay.md)); if Stimela does not
  install from public PyPI into the 3.13 venv, W5 stops and reports.
- Both arms of every case run from `.venv313`, with its `rang-core` first on
  `PATH`, and one gemclean binary (the worktree's `core/target/release/gemclean`,
  copied into the run directory, SHA-256 recorded).
- Runs under `/mnt/d/rang/outputs/w5-20261106-NN`, each with a `.code/`
  snapshot (`head.txt`, `diff.patch`, `untracked.tgz`), under
  `flock ~/.rang-heavy.lock`. No simulated data is generated, so no seed is used.

## 3. Cases (frozen)

| Case | Data | Configuration |
| --- | --- | --- |
| A | a copy of A1 small, `/mnt/d/rang/outputs/fp-a1-20261106-simtruth/small/a1-small.ms` (12,480 rows, 64 channels, 16 antennas, 4 fields) | fields fcal J1939-6342, gcal SIM-GCAL, target SIM-TARGET; flag with CARACal's `mk_rfi_flagging_calibrator_fields_firstpass.yaml` (`8f7bb363`, from `outputs/caracal-strategy-inputs-8f7bb363`); `model.source: setjy` (Stevens-Reynolds 2016), `refant: m000`, `uvrange: ">150"`; primary K, G (`inf`, K), B (`inf`, `combine: scan`, `fillgaps: 70`, K G), A; secondary Gsec (`60s`, K B), Asec, F (`inf`, K B); apply fcal K G B and gcal, target K F B with `gainfield [J1939-6342, nearest, J1939-6342]`; image SIM-TARGET 512 × 512 at 2″, Briggs 0, `niter` 2000, 1 thread; `data.weights: as_is` |
| O | a copy of O-CASA's slice, `~/Github/rang/outputs/o-casa-20261030-01/work.ms` (LUNO 1934-638, 4 stations, 2048 channels, field 1) | fcal field 1; the same strategy; `model.source: column`, `refant: m000`, `minblperant: 3`; primary K0, G0 (K0), B0 (`combine: scan`, `fillgaps: 70`, K0 G0), A0, K1 (`int`), G1 (`int`), B1, as C2e's I-slice; apply K1 G1 B1 to field 1; image field 1, 256 × 256 at 10″, Briggs 0, `niter` 500, 1 thread |

The configurations are written out in `tools/oracles/w5/run.sh`, with
`run.stages: [flag, calibrate, apply, image]` and `image.gemclean` the copied
binary. Before anything runs, each must pass `rang-core config check CONFIG MS`
(the stages of `run.stages`) with no refusal: they use no polarisation term, no self-calibration and not
`data.weights: uniform` (refused for imaging, W4 decision 1).

Each case has two arms, on two copies of the input with the same basename in
different directories (paths reach tables and FITS headers):

- **S (Stimela):** `stimela -s opts.log.dir=<run>/<case>/S/logs run
  recipes/rang-chain.yaml config=<config> ms=<S>/<name>.ms`, from `<run>/<case>/S`.
- **H (by hand):** `rang-core flag`, `calibrate`, `apply`, `image`, each
  `CONFIG MS`, in that order, from `<run>/<case>/H`.

Both arms use the default run directory `<ms>.rang-run` and the same
configuration file.

## 4. Gates (frozen)

1. **The chain recipe runs end to end under Stimela** on case A and on case O:
   `stimela run` exits 0, and the run directory's `state.json` has flag,
   calibrate, apply and image `done`. Each step's command line in Stimela's
   log is `rang-core <verb> <config> <ms>`, the argv of arm H.
2. **Bit-identical outputs, S against H**, per case:
   - (a) every column of the MS has equal SHA-256 over the whole column
     (casacure read, `tools/oracles/w2/oracle.py hashes`), in particular FLAG,
     FLAG_ROW, CORRECTED_DATA, MODEL_DATA, WEIGHT_SPECTRUM and DATA;
   - (b) every calibration table the calibrate stage lists in its summary has
     every main-table cell, keyword and subtable cell equal (`caltable.read`,
     as C2e's gate 1); whether the table directories are byte-identical as files
     is reported;
   - (c) every FITS file under `<run>/image/` has a bitwise equal data array;
     header differences are reported, not gated;
   - (d) the flag versions hold equal FLAG in the same order; their names
     carry UTC times and are not compared.
   Receipts, `state.json` and stage summaries carry times and paths; they are
   compared with times and run paths removed and reported, not gated.
3. **Every recipe passes `stimela doc`** (Stimela 2.1.4, `.venv313`): each
   file in `recipes/` exits 0 and lists its recipe or cabs.
4. **The research recipes carry a marker a test checks:** the pytest of
   section 1 passes, and fails if the marker is removed from any file (checked
   once by hand on a scratch copy).

A failure is reported as measured. Any change after a result is labelled post
hoc. Bit identity has no tolerance to tune, so no held-out case is needed
beyond case O, which is frozen here with case A.
