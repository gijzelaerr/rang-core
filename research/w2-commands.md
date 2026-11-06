# W2: the command line for a user's own Measurement Set

Task W2 of [finish-plan.md](finish-plan.md): one configuration schema and the
commands `rang-core flag`, `calibrate`, `image`, `selfcal` and `run` for a
Measurement Set (MS) outside the repository, with resume and receipts. The
research stages move under `rang-core research`. Branch `fp-w2-commands` from
main `d099bb3`. The write-back underneath is W1's `rang.core_writeback`
([w1-writeback.md](w1-writeback.md)).

Status: **implemented and measured** (code `36af4ab`, frozen run
`/mnt/d/rang/outputs/fp-w2-20261106/run-01`). All six criteria of section 2
pass as frozen: `flag` gives the port's FLAG in every cell (0 of 3,194,880
cells differ, with and without seeded input flags), `calibrate`'s gain store is
byte-identical to the direct `core.solve_complex` path (80 of 80 files), the
resumed `run` reran only the failed stage, and the SIGKILL, refusal and schema
tests pass. What runs and what is refused is in section 3. The criteria were
committed (`6d5b053`) before any run. check-all at the head passes except
`test_every_note_is_in_the_research_index`, which needs the index line in "For
the coordinator". No novelty claim: this is an interface.

## 1. Design (proposed in `6d5b053`; implemented in `36af4ab`)

- `python/rang/core_config.py`: the schema `rang-config`, version 1. Every key
  has a default written in the code and printed by `rang-core config
  defaults`. Validation reports every problem at once, in two classes:
  - **schema errors**: unknown keys, wrong types, values outside their
    choices, a missing required key;
  - **not yet implemented**: a value the schema can express but rang cannot
    run yet. Each such refusal names the finish-plan task that adds it.
  `rang-core run` validates every stage it will run before the first write.
- `python/rang/core_pipeline.py`: the run directory, its state file and the
  stages. `core_cli` only dispatches.
- The schema can express C1's frozen chain ([c1-calibration-chain.md](c1-calibration-chain.md),
  1.2 and 1.3): field roles, terms in order, `solint`, `combine`, `refant`,
  `uvrange`, `minsnr`, `minblperant`, `interp`, pre-applied tables and apply
  targets, polarisation terms and self-calibration. A0's E2-A and E2-B settings
  ([a0-acceptance.md](a0-acceptance.md), 6.3) are written as test fixtures.
- **What runs in W2:**
  - `flag`: the Tricolour port (`core_flag.flag_rows`) per field, data
    description and scan group, as Tricolour groups rows. FLAG is assembled
    for the whole MS and written in chunks through `core_writeback`.
  - `calibrate`: the `complex` term only (`core.solve_complex`), one solve per
    field and scan, with QuartiCal-style intervals. The gains are written as a
    QuartiCal gain store (`formats.quartical_store`), because CASA's table
    types have no full 2×2 gain.
  - `image`: `gemclean` on a data column, one image per field.
  - `apply` and `selfcal`: validated and refused, naming C4 and C5 (and G6).
- **Flag backups (decided by the coordinator):** `rang_original` is saved
  before the first write ever made to the MS. In addition each writing stage
  saves one CASA flag version, `rang_<stage>_<UTC time>`, before it writes, so
  any stage can be undone with `flagmanager` or `restore_flags`.
- **Resume:** a run directory (default `<ms>.rang-run` beside the MS) holds
  `state.json`. Each stage records its status, the hash of the configuration
  it depends on, its flag version, outputs and any error. A finished stage
  with the same hash is skipped; one whose configuration changed is refused
  unless forced; a failed or interrupted one runs again. A forced or resumed
  `flag` first restores the flags saved before its earlier attempt.
- **Refused data:** an MS whose DATA cells differ in shape, more than one
  data description in use, and anything but four linear correlations. Each
  refusal names W4.

## 2. Oracles and criteria (frozen before the first run)

There is no numerical oracle beyond what exists. The criteria:

1. **Runs outside the repository.** A copy of A1's small MS
   (`/mnt/d/rang/outputs/fp-a1-20261106-simtruth/small/a1-small.ms`) is made
   under `/mnt/d/rang/outputs/fp-w2-20261106/`. `rang-core flag`,
   `calibrate`, `image` and `run`, each given `config.yaml` and that MS, exit
   0 and write a `rang.receipt`. `rang-core selfcal` and an `apply` stage exit
   non-zero with a message naming C5 and C4. Pass: as stated.
2. **flag = the port's FLAG.** The examples script `run_core_flags.py` cannot
   run on an MS: it reads exported `arrays.npz` and a host run's `state.npz`.
   So the oracle is the same call it makes. Arrays are read independently
   with casacure (python-casacore's API, a different reader from rang's) from
   a **pristine copy** of the input. For each (FIELD_ID, DATA_DESC_ID,
   SCAN_NUMBER) group, `core_flag.flag_rows` runs with the strategy parsed by
   `parse_strategy` and the masks loaded by `load_static_mask`, as
   `run_core_flags.py` does. The strategy is CARACal's
   `mk_rfi_flagging_calibrator_fields_firstpass.yaml` at `8f7bb363`, from
   `outputs/caracal-strategy-inputs-8f7bb363`. Pass:
   - (a) the FLAG written by `rang-core flag` equals that FLAG in every cell;
   - (b) FLAG_ROW and every other column, except FLAG, are unchanged (SHA-256);
   - (c) flag version `rang_original` equals the pristine FLAG and FLAG_ROW.
   A1's FLAG is all false, so a second case seeds input flags (10 % of cells,
   seed 20261106) and FLAG_ROW (5 % of rows) into another copy before both
   arms run. The same three conditions must hold there.
3. **calibrate = `core.solve_complex`.** On the flagged copy, the oracle reads
   the arrays with casacure, groups and sorts them as specified (stable sort by
   TIME within each field and scan), builds the same bins, calls
   `core.solve_complex` and writes the store with `quartical_store`. Pass:
   gains and gain flags **bit-identical** to those of `rang-core calibrate`,
   and every file of the two stores byte-identical.
4. **Resume after a forced failure.** `rang-core run` is started with an
   `image.gemclean` path that does not exist. Pass:
   - it exits non-zero with `image` marked failed, and flag and calibrate done;
   - after the path is fixed, the second `run` skips flag and calibrate and
     runs image to the end;
   - FLAG, the flag-version list and the gain store hashes are the same
     before and after the second run, and no new flag version is written.
5. **Interrupted flag write** (pytest, synthetic MS). A `flag` process is
   killed with SIGKILL after its first flushed FLAG chunk. Pass: the next
   `flag` restores the flags saved before the killed attempt and gives the
   same FLAG as an uninterrupted run, and `rang_original` equals the input.
6. **Refusals** (pytest). The E2-A and E2-B configurations parse with no
   schema error, and their not-yet-implemented refusals name exactly the
   expected tasks. A schema error, such as an unknown key, names the key's
   path. An MS with two spectral windows of different widths is refused,
   naming W4.

A failure is reported as measured and not reworded.

## 3. What each command runs and refuses (implemented, `36af4ab`)

`rang-core COMMAND CONFIG MS [--run-dir DIR] [--force]` (`run`: `--force STAGE`,
repeatable, or `all`). Exit 0: ran or skipped; 1: a stage failed (the state
says which); 2: refused before anything was written. `rang-core config defaults`
prints every key with its default and comment (also in `docs/cli.md`);
`rang-core config check CONFIG [MS] [--stage S] [--all]` validates without
running.

| Command | Runs | Refuses (task named in the message) |
| --- | --- | --- |
| `flag` | The Tricolour port per (FIELD_ID, DATA_DESC_ID, SCAN_NUMBER) group in row order, on `flag.column` (default DATA), with the two Tricolour 0.2.1 static masks. Input flags are FLAG only, as `examples/oracle_tricolour.py` reproduces Tricolour's app; FLAG becomes the strategy's flags (`flag.write: replace`, as Tricolour) or their OR with FLAG (`or`). FLAG_ROW is neither read nor written. Selection: `flag.fields` (default all), `data.scans`. | No `flag.strategy` (required; no strategy is shipped, see section 7). |
| `calibrate` | The `complex` term (`core.solve_complex`, QuartiCal 0.2.7's solve) for each term of `calibrate.primary`, `secondary` and `polcal`, one solve per field and scan, rows sorted stably by TIME. `solint`: `inf`, `int` or N integrations; `freqint`: `inf` or N channels. Weights: WEIGHT_SPECTRUM, else WEIGHT per channel (`data.weights: as_is`), or 1 (`uniform`, in memory). Model: a 1 Jy point (`unity`, the solver's scalar model) or an existing column (`column`). Written to `<run>/calibrate/<name>.qc`, a QuartiCal gain store (`complex_partition`, one partition per field and scan). A partition with no valid solution fails the stage, as C1 requires. | K (C2b), G (C2a), B (C2c), A and F (C2d), Gpol, KCROSS, Xf and `extendflags` (C6b), Df (C6c), `feed_angle_rotation` (C6a); models `setjy`, `manual`, `lsm` (C3a); on `complex`: `solint` in seconds, `combine`, `refant`, `uvrange`, `minsnr`, `minblperant`, `refantmode` (C2a) and `preapply` (C4a). |
| `apply` | Nothing. | Always (C4); `apply.parang` (C6a). |
| `image` | `gemclean` once per field of `image.fields` (default the target role), into `<run>/image/<field>/`. The binary: `image.gemclean`, else `gemclean` on PATH, else the checkout's `core/target/{release,gemclean}/gemclean`; its SHA-256 is recorded. `image.column: auto` is CORRECTED_DATA once this run's apply finished, else DATA, and is always passed with `-data-column`. Size, scale, weighting, `niter`, thresholds, gains, `nmiter`, threads, gridder accuracy and `extra_args` are passed through. | `size`, `scale` missing; `channels_out`, `join_channels`, `fit_spectral_pol`, `average_channels` (G3); `auto_mask`, `fits_mask`, `taper_gaussian`, `uvrange` (G4); `multiscale` (G5); `write_model` (G6); `pol` other than I, `join_polarizations` (G9); `data.weights: uniform` (C4: the imager reads the MS weights, so they would have to be written). A missing binary fails the stage (G8). |
| `selfcal` | Nothing. | Always (C5a, G6); Sd terms (C5b). |
| `run` | `run.stages` (default flag, calibrate, image) in the order flag, calibrate, apply, image, selfcal. | Anything above for any listed stage, all before the first stage runs; a finished stage whose configuration sections changed, unless forced. |

Every command also refuses, naming W4: an MS whose data descriptions differ in
cell shape (`core_writeback.layout`), more than one data description in use,
and correlations other than XX, XY, YX, YY. Unknown field names and roles
without fields are refused before anything is written.

**Research stages.** Every stage of the former `rang-core STAGE VERB` is now
`rang-core research STAGE VERB`, with the legacy forms (`research compare`,
`research trend-mirror`, `research injections RUN PREPARED`). The stage
functions keep their names and signatures, so the Stimela cabs in
`recipes/core-*.yaml` are unchanged. The old top-level forms exit with the
new command line. Tests, `docs/index.md`, `docs/concepts/imaging.md`, the
README table and the comments of `examples/compare_core_*.py` were updated;
`research/` reports and `history/` keep the old forms as records.

**Receipts.** Each command writes a `rang.receipt` (version 4, fields
unchanged) into `<run>/receipts/<command>-<UTC time>.rang-receipt.json`, or to
`--receipt PATH`. The paths recorded are the configuration, the MS, its
`.flagversions` and the run directory; a modified MS is content-hashed in full.
A refusal before the run directory exists writes no receipt. Stage details
(strategy hash, groups, gains hashes, gemclean arguments and output hashes)
are in `<run>/<stage>/summary.json` and `state.json`.

## 4. Results (frozen run `-01`, code `36af4ab`)

Run `bash tools/oracles/w2/run.sh /mnt/d/rang/outputs/fp-w2-20261106/run-01`,
114 s, on copies of A1's small MS (12,480 rows, 64 channels, 16 antennas, 4
fields, 23 scans; FLAG all false). Configuration: `fcal: [J1939-6342]`,
`target: [SIM-TARGET]`, strategy CARACal's
`mk_rfi_flagging_calibrator_fields_firstpass.yaml` (SHA-256 `ce9ac66a…`, 12
steps), primary term `{type: complex, solint: int, freqint: 16}`, image 512 ×
512 at 2″, Briggs 0, `niter` 2000, 2 threads. The trial run `-00-trial`, the
same harness before three fixes (exit status 2 for refusals, the conflict check
moved before the first stage, the timing parse), gave the same verdicts.

| # | Criterion | Measured | Verdict |
| --- | --- | --- | --- |
| 1 | Commands exit 0 and write receipts; selfcal and apply refused naming C5a and C4 | flag 0 (20.0 s), calibrate 0 (3.3 s), image 0 (4.7 s), run 0; selfcal 2 (C5a, G6), apply 2 (C4), `run` with selfcal or apply in its stages 2, nothing written; one receipt per call in `<run>/receipts/`, the flag receipt with `commit` `36af4ab` clean and the MS listed as modified | pass |
| 2a | FLAG = the port's FLAG (casacure read of a pristine copy) | 0 of 3,194,880 cells differ; 31.40 % flagged by both | pass |
| 2b | Every other column unchanged | casacure SHA-256 of every column: only FLAG changed | pass |
| 2c | `rang_original` = pristine FLAG and FLAG_ROW | equal, equal | pass |
| 2, seeded | The same with 10 % FLAG and 5 % FLAG_ROW seeded (seed 20261106) | 0 cells differ; 54.98 % flagged; only FLAG changed; `rang_original` equal | pass |
| 3 | Store = `core.solve_complex` + `quartical_store` (casacure read) | 80 of 80 files byte-identical; 2 partitions (scans 1 and 23); gains bit-identical, gain flags equal | pass |
| 4 | Resume after a missing gemclean | first `run` exit 1: flag done, calibrate done, image failed; second `run` skipped flag and calibrate (one attempt each, same start times) and ran image (attempt 2) to the end; every column hash, the flag-version list (2 versions) and the store's files unchanged | pass |
| 5 | SIGKILL after a flushed FLAG chunk (pytest) | the journal is left open and FLAG half written; the next `flag` restores `rang_flag_<time>` of the killed attempt and gives the uninterrupted run's FLAG; `rang_original` equals the input | pass |
| 6 | Refusals (pytest) | E2-A: C2a, C2b, C2c, C2d, C3a, C4, C5a, G3, G4, G6; E2-B: C2a, C2b, C2c, C2d, C3a, C4, C6a, C6b, C6c, G3, G9; no schema error in either. Unknown keys reported with their paths, all at once. Two spectral windows of 16 and 8 channels refused naming W4, with no flag version written | pass |

Reported, not gated:

- **The solves did not converge.** Both partitions ran the 50 iterations
  with a converged fraction of 0.0, and every solution is valid. The model is a 1 Jy
  point on a calibrator of about 15 Jy, with A1's gains and 31 % of cells
  flagged. Bit-identity holds whatever the convergence; calibration quality
  belongs to C2 and E1.
- **The image is of uncalibrated DATA**, since nothing is applied until C4:
  654 components, 4 major cycles, 1.34 s in gemclean.
- **Also run:** `flag` again on a finished MS was skipped with no new flag
  version; `run` again after the resume skipped all three stages; a changed
  `calibrate` and `image` section was refused (exit 2) before any stage ran,
  naming both stages and `--force`.
- **Criterion 6 test, corrected before this record.** The first version of
  the pytest at `36af4ab` refused two data descriptions on the same window and
  a two-correlation MS, but not two windows of different widths as frozen.
  The case was added in the commit after `36af4ab`, and it passes.
- **Where the flag stage's 20 s go** (one cProfile run, not a timing
  measurement): 18.5 s in the core writer's `ms_create_table` for the two flag
  versions (`flagversions._create`, 9.2 s each) on `/mnt/d`, and 0.9 s in the
  Tricolour port. The cause, for example drvfs and the fsyncs, was not
  established. It is W1's writer, so it is left for W3.

## 5. Limits and what was not checked

- **Memory.** Each stage reads whole columns (DATA, FLAG and the rest) into
  memory and writes FLAG in chunks. Chunking by time and row is W3; until
  then, an MS's DATA must fit in memory.
- **Receipts at scale.** A modified MS is content-hashed in full by the
  receipt (as every receipt does). At E2's size that is a W3 matter.
- **Not CASA-readable gains.** The `complex` term has no CASA table type. The
  store is QuartiCal's format (F2's reader and writer). CASA tables begin with
  C2's diagonal terms.
- **Intervals.** QuartiCal's integer intervals, not CASA's seconds bins (C2a).
- **FLAG_ROW** is ignored by `flag`, as the oracle replica of Tricolour does.
  Rows flagged only in FLAG_ROW are flagged by the strategy as their FLAG says.
- **Not checked:**
  - Tricolour itself on this MS: that is gate 3a of E2.
  - The `or` write mode and `static_masks: none` against an oracle.
  - `model.source: column`: tested only by validation.
  - Windows and macOS: the run directory lock is fcntl only (no lock on
    Windows), and the SIGKILL and fake-gemclean tests skip off POSIX.
  - An installed wheel: `image.gemclean: auto` finds no binary there (G8).
  - Two commands on the same run directory at once: the lock refuses the
    second, but this was not tested.
  - MSs larger than 40 MB.
  - The Stimela recipes calling the new commands: that is W5.

## 6. Timings

Rows added to [tool-timings.md](tool-timings.md). Wall and peak RSS of every
step are in `run-01/timing/` (`/usr/bin/time`); the host was shared, so these
are not timing measurements.

## 7. Owner decisions

- **A default Tricolour strategy.** None is shipped; `flag.strategy` is
  required. Shipping one of CARACal's strategy files needs a licence check;
  CARACal's licence was not checked here.
- **PyYAML** is now a runtime dependency (`pyyaml>=6`), for the configuration.
- **Defaults to confirm:**
  - `data.weights: as_is`; A0 uses `uniform` for E2 and E3.
  - `image.weight: briggs`, `robust: 0`, `niter: 100000`, `auto_threshold: 3`;
    `gain`, `mgain` and `nmiter` are left to gemclean.
  - The run directory beside the MS (`<ms>.rang-run`).
  - A finished stage whose configuration changed is refused, not rerun.

## For the coordinator

- **research/README.md**, after the W1 line:
  `- [W2, the command line](w2-commands.md): rang-core flag, calibrate, image and run on a user's Measurement Set from one versioned YAML configuration, with resume, receipts and a flag version before each write; unimplemented terms are refused, naming their task; the research stages are now rang-core research.`
  This line also makes `test_every_note_is_in_the_research_index` pass. It is
  the only check-all failure at the branch head.
- **research/STATE.md**, log, newest first:
  `W2, 2026-11-06 (implemented and measured; [w2-commands.md](w2-commands.md)). rang-core flag, calibrate, apply, image, selfcal and run take a config.yaml (schema rang-config, version 1, every default printed by rang-core config defaults) and an MS. flag runs the Tricolour port per field and scan and writes FLAG, calibrate solves the complex term and writes a QuartiCal gain store, and image runs gemclean. apply and selfcal are refused (C4, C5a, G6). The whole of C1's chain and A0's E2-A and E2-B settings can be written in the schema and are refused term by term, naming C2a to C6c, G3, G4 and G9. A run directory holds the state: run skips finished stages, resumes at a failed one and refuses a changed configuration unless forced. Before the first write the flags are saved as rang_original, and before each writing stage as rang_<stage>_<time>. On A1's small MS: FLAG equals the port's call in every cell (with and without seeded input flags), the gain store is byte-identical to core.solve_complex, and a resumed run reran only the failed image stage. The research stages moved under rang-core research. No novelty claim.`
  In "Current status", Running: `Done: A0, A1, C1, G1, W1, W2.` (as it stands
  after C4a and C3a merge).
- **research/finish-plan.md**, row W2: `**Done 2026-11-06** ([w2-commands.md](w2-commands.md)).` before the task text. Section 2, row "Command line": the missing part is now chunking (W3) and the stages C2 to C7 and G3 to G9 add.
- **After merging C3a or C4a:** regenerate `docs/cli.md`
  (`python docs/gen_cli.py`), because it carries the environment-variable
  section and the refusal texts. When C3a adds `setjy` or C4 adds apply, the
  matching refusal in `rang.core_config.refusals` must be removed, and the
  E2-A and E2-B expectations in `tests/test_w2_commands.py` change with it.
- **Shared files changed:** `python/rang/core_cli.py` (dispatch;
  `TOP_LEVEL` is split into `TOP_LEVEL`, `RESEARCH_TOP_LEVEL` and
  `USER_COMMANDS`), `docs/gen_cli.py`, `pyproject.toml` (PyYAML),
  `tests/test_core_cli.py`, `tests/test_d1_docs.py` and
  `tests/test_df2c_campaign_gridder.py` (the `research` prefix). A branch that
  adds a research stage or calls `core_cli.main([STAGE, ...])` must add
  `research`.
- **Not removed:** `/mnt/d/rang/outputs/fp-w2-20261106/` (the runs, 486 MB,
  mostly MS copies; can go after merge). The worktree's `core/target` holds the
  gemclean build used by the run.
