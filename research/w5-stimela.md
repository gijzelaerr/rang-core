# W5: the Stimela recipes call the commands

Task W5 of [finish-plan.md](finish-plan.md): "The Stimela recipes call the new
commands"; gate "One recipe runs the chain; research recipes are marked as
such". Branch `fp-w5-stimela` from main `02024bd`. The commands are W2's
`rang-core flag`, `calibrate`, `apply` and `image`
([w2-commands.md](w2-commands.md)), with C2e's K, G, B, A and F terms
([c2e-calibrate.md](c2e-calibrate.md)) and W3's chunking
([w3-chunking.md](w3-chunking.md)).

Status: **implemented and measured** (protocol and code `5658677`, committed
before any run; frozen run `/mnt/d/rang/outputs/w5-20261106-01`). The chain
recipe ran end to end under Stimela 2.1.4 on A1 small and on the O-CASA slice.
Its FLAG, every other MS column, every calibration table (byte for byte), the
flag versions and every FITS pixel are bit-identical to the four commands run
by hand. All nine recipe files pass `stimela doc`, and the research marker test
fails when a marker is removed. One frozen condition is **not met as
written**: Stimela passes the MS to each command as a path relative to its
working directory (`a1-small.ms`), where arm H passed it absolute (section
5). Gates 2, 3 and 4 are met. No novelty claim: this is an interface.

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

## 5. Results (frozen run `-01`, code `5658677`)

Run `flock ~/.rang-heavy.lock bash tools/oracles/w5/run.sh
/mnt/d/rang/outputs/w5-20261106-01` (log `w5-20261106-01.log` beside it),
`.code/` with `head.txt` `5658677` and an empty `diff.patch`. Environment
(`out/environment.txt`): `.venv313`, Python 3.13.16, Stimela 2.1.4, rang-core
0.1.0 editable at the worktree; gemclean and the strategy hashed in
`out/inputs.sha256`. Both configurations passed `rang-core config check` with
no refusal (exit 0) before anything ran. Comparator output:
`out/compare-A.json`, `out/compare-O.json`.

| Gate | Case A (A1 small) | Case O (O-CASA slice) | Verdict |
| --- | --- | --- | --- |
| 1: Stimela runs the chain | `stimela run` exit 0; flag, calibrate, apply, image `done` in `state.json`; one receipt per stage, exit 0 | the same | met |
| 1: each step's argv = arm H's | Stimela logged and ran `rang-core flag <run>/A.yaml a1-small.ms` (and the same for the other three verbs); arm H ran `... <run>/A/H/a1-small.ms` | the same, `work.ms` | **not met as written**: the MS path is relative to Stimela's working directory (the step's cwd, `<run>/A/S`), the same file; the verb, the configuration path and the argument order are equal |
| 2a: every MS column | all 25 columns' SHA-256 equal (FLAG, FLAG_ROW, DATA, MODEL_DATA, CORRECTED_DATA, WEIGHT, WEIGHT_SPECTRUM, SIGMA and the rest) | all 26 columns, SIGMA_SPECTRUM included | met |
| 2b: calibration tables | K, G, B, Gsec, F (and `F.append`): every cell, keyword and subtable cell equal; every file byte-identical | K0, G0, B0, K1, G1, B1: the same | met |
| 2c: image pixels | 5 FITS files, data arrays bitwise equal, no header difference | 5 FITS files, the same | met |
| 2d: flag versions | `rang_original`, `rang_flag_…`, `rang_calibrate_…`, `rang_apply_…`: FLAG and FLAG_ROW equal in order | the same | met |
| 3: `stimela doc` | all nine files in `recipes/` exit 0 (`logs/doc-*.log`) | – | met |
| 4: marker test | `tests/test_w5_recipes.py` passes; with the marker line of `core-signal.yaml` removed, or the `Research recipe:` prefix of `core-trend.yaml`, it fails (`out/gate4.txt`); restored, it passes | – | met |

Reported, not gated:

- **Summaries and state** with times and arm paths removed are equal, except
  `image/summary.json`'s hash of gemclean's `image-report.json`. That report
  holds gemclean's argv, with the arm's MS and output prefix (2 leaves), and
  per-phase RSS and timings, which differ between any two runs.
- **Why gate 1's argv differs.** Stimela 2.1.4 gives a path input that lies
  under the step's working directory to the command relative to it. The
  configuration file, outside that directory, stayed absolute. The command
  resolves the MS against its own working directory, the one Stimela ran it
  in, so the run directory (`a1-small.ms.rang-run`) and every output are where
  arm H put them. The gate was written for an absolute path in both arms; it
  stays not met as frozen, and nothing was changed after the result.
- **Wall times** (shared host, not timing measurements): case A arm S 80 s,
  arm H 19.5 + 27.4 + 25.5 + 6.3 s; case O arm S 33 s, arm H 2.3 + 13.4 + 11.3 +
  5.2 s; `stimela doc` 0.4-0.6 s per file.

## 6. Limits and what was not checked

- The cabs need `rang-core` on `PATH`, from an environment with Stimela 2.1.4
  on Python 3.13. They run the native backend only; no container image of rang
  exists, so the singularity and kubernetes backends were not tried.
- `force` and `run-dir` were checked by `stimela doc` and the static test, not
  in a run: the frozen runs used the default run directory.
- Resume through Stimela (rerunning the recipe after a failed stage) was not
  run; it is the commands' own behaviour, tested in W2.
- Polarisation terms, self-calibration and `data.weights: uniform` for imaging
  were left out by design (C6w, C5, W6).
- The research recipes were not rerun; their steps are unchanged.

## 7. Timings

Rows added to [tool-timings.md](tool-timings.md).

## 8. Owner decisions

- **Which recipes are research.** All seven `core-*.yaml` files are marked
  research, `core-actions` and `core-imaging` included: they replay frozen
  campaigns against archives (section 0). The owner may want different names
  (for example moving them to `recipes/research/`), which would change the
  tests and docs that glob `recipes/core-*.yaml`.
- **Gate 1's relative MS path** (section 5): accept it as Stimela's documented
  behaviour, or have the cabs resolve paths absolute (a Stimela path policy),
  which was not tried.

## For the coordinator

- **research/README.md**, after the W3 line:
  `- [W5, Stimela recipes](w5-stimela.md): recipes/rang-chain.yaml runs rang-core flag, calibrate, apply and image under Stimela 2.1.4, bit-identical to the commands by hand on A1 small and the O-CASA slice; the core-*.yaml recipes are marked research and a test checks the marker.`
  This line also makes `test_every_note_is_in_the_research_index` pass, the
  only check-all failure at the branch head.
- **research/STATE.md**, log, newest first:
  `W5, 2026-11-06 (implemented and measured; [w5-stimela.md](w5-stimela.md)). New recipes/rang-cabs.yaml (binary cabs rang-flag, rang-calibrate, rang-apply, rang-image running the rang-core console script) and recipes/rang-chain.yaml (flag, calibrate, apply, image on one configuration and MS). Under Stimela 2.1.4 (Python 3.13) on A1 small with the C2e K, G, B, A, F chain and on the O-CASA slice with KGBAKGB, every MS column, every calibration table file, the flag versions and every FITS pixel equal the four commands run by hand. Stimela hands the MS over as a path relative to the step's directory, so the frozen argv condition is not met as written. All nine recipe files pass stimela doc. The seven core-*.yaml recipes replay frozen campaigns; they start with "# rang-recipe: research" and their info with "Research recipe:", which tests/test_w5_recipes.py checks. No novelty claim.`
  In "Current status", add W5 to the Done list.
- **research/finish-plan.md**, row W5: `**Done 2026-11-06** ([w5-stimela.md](w5-stimela.md)).`
  before the task text. The brief named `core-actions` and `core-imaging` among
  the recipes to move to the commands; both are archive replays and stay as
  research recipes (section 0).
- **Shared files changed:** `docs/gen_cli.py` and `docs/cli.md` (regenerated),
  `docs/installation.md`, `README.md`, the header and `info:` of each
  `recipes/core-*.yaml`. No Python or Rust code changed. A branch that adds a
  recipe must start it with `# rang-recipe: research` or `user`.
- **Not removed:** `/mnt/d/rang/outputs/w5-20261106-01` (305 MB, mostly the
  four MS copies; can go after merge). The worktree holds `.venv` (3.14),
  `.venv313` (3.13 with Stimela) and `core/target`.
