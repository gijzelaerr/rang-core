# W2: the command line for a user's own Measurement Set

Task W2 of [finish-plan.md](finish-plan.md): one configuration schema and the
commands `rang-core flag`, `calibrate`, `image`, `selfcal` and `run` for a
Measurement Set (MS) outside the repository, with resume and receipts. The
research stages move under `rang-core research`. Branch `fp-w2-commands` from
main `d099bb3`. The write-back underneath is W1's `rang.core_writeback`
([w1-writeback.md](w1-writeback.md)).

Status: **proposed; the criteria below are frozen before any run.** Nothing in
this section is implemented or measured yet.

## 1. Design (proposed)

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

## For the coordinator

(Filled in after the runs.)
