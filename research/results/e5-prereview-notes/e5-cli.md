# E5 pre-review: command line and configuration (CLI-nn)

Reviewed at 3eab67c in <worktree>. During the review the
worktree moved to 2bac745 ("E5: lock the run directory on Windows too (msvcrt)"), which
touches only core_pipeline.py and tests/test_w2_commands.py. core_pipeline.py line numbers
below are at 2bac745. core_cli.py, core_config.py, README.md and docs/cli.md are unchanged.
CLI-01 was re-run at 2bac745 and still fails.

Python: <main checkout>\.venv\Scripts\python.exe with
PYTHONPATH=<worktree>\python. The synthetic MS is `tests/test_w2_commands.make_ms`, the
W2 fixture with 240 rows, 4 antennas, fields CAL and TGT, and 16 channels.

Counts: release-blocking 2, should-fix 5, later 6.

---

## CLI-01: release-blocking. Rerunning a stale stage restores the flags of the old upstream run

- **Where:** python/rang/core_pipeline.py:2460 (`attempt["flag_version"] = entry["flag_version"]`),
  :2493-2498 (the stale marking), :805-823 (`restore_before`). Every writing stage calls
  `restore_before(ms, ctx["entry"])` (flag, the calibrate chain, calibrate, apply, selfcal).
- **What is wrong:** suppose an upstream stage is rerun (`--force flag`, as the conflict message
  and the CHANGELOG prescribe). The later stages are marked `stale`, but they keep the
  `flag_version` of their previous attempt. When a stale stage reruns, `restore_before` puts
  back the flags saved before its previous attempt. Those are the **old** upstream output, so
  the new flag run's FLAG is silently overwritten. The stage then saves the reverted flags as its
  own version, so the new flags are kept nowhere. state.json shows every stage `done`, and the
  exit code is 0.
- **Evidence:** `rang-core run` only, with documented flags (scratch script
  `repro_run.py`, core of it):
  ```python
  ms1 = t.make_ms(tmp/"one.ms"); ms2 = t.make_ms(tmp/"two.ms")
  a = t.write_config(tmp, "run: {stages: [flag, calibrate, apply]}\n", name="a.yaml")
  b = tmp/"b.yaml"; b.write_text(a.read_text().replace(
      "flag: {strategy: strategy.yaml}", "flag: {strategy: strategy.yaml, fields: [CAL]}"))
  t.cli("run", a, ms1)
  t.cli("--no-receipt", "run", b, ms1, "--force", "flag")   # change flagging, rerun
  t.cli("--no-receipt", "run", b, ms2)                      # fresh run with b
  ```
  Output (at 3eab67c and again at 2bac745):
  ```
  {'apply': ('done', 'rang_apply_...Z'), 'calibrate': ('done', None), 'flag': ('done', 'rang_flag_...Z')}
  FLAG one==two(fresh b): False flagged 5232 3387
  ```
  5232 is config a's flag count, and the forced rerun should have left 3387. Apply corrects
  CAL only, so TGT keeps the flags of the strategy the user replaced. The same happens with
  `rang-core flag --force` followed by `rang-core calibrate`, when calibrate writes a model
  (`flag_version` set). In that two-command form FLAG equalled config a's flags, not b's.
  tests/test_w2_commands.py::test_a_changed_configuration_is_refused_and_force_restores_first
  asserts only that calibrate becomes `stale`, never what it restores.
- **Fix:** in `execute`, when a stage finishes, take `flag_version` out of the entry of every
  later stage, whatever its status. Then a stage whose input changed starts from the current
  flags:
  ```python
  for other in later:
      e = state["stages"].get(other)
      if not e:
          continue
      e.pop("flag_version", None)  # its input changed: never restore the old one
      if e.get("status") == "done":
          e["status"] = "stale"
          e["stale_since"] = f"{stage} {attempt['finished']}"
  ```
  This drops the flag version from failed later stages too, which is wanted. A failed
  calibrate whose upstream flag is then rerun must not restore the old flags either.
  A forced rerun of a stage whose upstream did not run keeps its restore, as designed. That
  limit is a design choice: write it in the module docstring. A pending write-back of a later
  stage cannot be lost, because the upstream `restore_before` already refuses an unfinished
  journal it did not make. Add the repro above as a test: FLAG after `run b --force flag`
  must equal a fresh `run b`.
- **Small and unambiguous:** yes (about 8 lines, plus a test of about 25 lines).

## CLI-02: release-blocking. The README states false things about the command line and the wheel

- **Where:** README.md:24-27 and README.md:91.
- **What is wrong:**
  - Lines 24-27 say gemclean "is not in the wheels" and give a cargo build line. The CHANGELOG
    Unreleased section (G8) says `gemclean` is in the wheel as a console script and
    `python -m rang.gemclean`, and `image.gemclean: auto` uses it (core_pipeline.py:1888-1906).
  - Line 91 says calibrate solves "`complex` only so far". K, G, B, A and F, the polcal terms
    (C2e, C6w) and selfcal (C5) all run.
  - The same table lists `flag`, `calibrate`, `image` and `run`, but not `apply` or `selfcal`.
- **Evidence:** `README.md:26: It is not in` / `:27: the wheels: cargo build ... --bin gemclean`;
  `README.md:91: ... solve (complex only so far) ...`. The CHANGELOG has "New: `gemclean` is
  in the wheel (task G8 ...)".
- **Fix:**
  - Lines 24-27: "`gemclean` (also `python -m rang.gemclean`) is installed with the wheel."
    Keep the cargo line only as the source build.
  - Line 91: list `flag | calibrate | apply | image | selfcal | run`. Describe calibrate as
    "complex, or CARACal's K, G, B, A, F and polarisation terms".
  - This may overlap with a docs reviewer.
- **Small and unambiguous:** yes.

## CLI-03: should-fix. Every writing command SHA-256s the whole Measurement Set for its receipt

- **Where:** python/rang/core_cli.py:702-715 (`Receipt.record`) and :1269-1281 (`_pipeline`
  passes `ms`, `ms.flagversions` and the run dir as paths).
- **What is wrong:** an input whose listing changed is recorded again with
  `_path_record(p, content=True)`, which reads and hashes every file of the MS. Flag, a
  calibrate that writes a model or A steps, apply and selfcal all modify the MS. Each of them,
  after the stage has finished and also on failure (`finish(1)`), reads the whole MS again.
  For a MeerKAT MS of hundreds of GB, that is minutes to tens of minutes of I/O per command.
  The CLI docs do not mention it. The content of what a stage wrote is already identified in
  its summary (`flag_sha256`, `gains_sha256`, image file hashes).
- **Evidence:** the `run` receipt in the repro (`one.ms.rang-run/receipts/run-*.json`):
  ```
  OUT {'path': '.../one.ms', 'kind': 'directory', 'files': 65, 'bytes': 621576, 'tree_sha256': '6ef1...', 'modified': True}
  OUT {'path': '.../one.ms.flagversions', 'kind': 'directory', ..., 'tree_sha256': '8dec...'}
  ```
  Code: `outputs.append({**_path_record(p, content=True), "modified": True})`.
- **Fix:** give `Receipt` a set `listing_only` of paths, recorded with `content=False` before
  and after (`listing_sha256` plus `modified`). `_pipeline` passes `{str(ms),
  str(ms) + ".flagversions"}`. The run dir stays content-hashed, since it is small. Add a
  test that the receipt's MS output has `listing_sha256`, not `tree_sha256`. Write the
  choice in docs/cli.md: the receipt names the MS, and the stage summaries name what was
  written.
- **Small and unambiguous:** yes (about 10 lines plus a test).

## CLI-04: should-fix. An edited strategy, sky model or mask file does not make its stage rerun

- **Where:** python/rang/core_config.py:1731 (`stage_hash`) and :586 (`STAGE_SECTIONS`).
- **What is wrong:** the stage hash covers configuration values only. `flag.strategy`, an A
  term's `strategy`, `calibrate.model.lsm`, `image.fits_mask` and selfcal's FITS
  `cleanmask_method` are hashed by **path**. A user who edits the strategy YAML in place and
  reruns gets `done ..., skipped` with exit 0, and FLAG stays the old strategy's. The run
  directory then shows a result that the files beside it did not make. The flag summary
  records `strategy_sha256`, but nothing compares it.
- **Evidence:**
  ```
  $ (append a step to strategy.yaml)
  $ rang-core --no-receipt flag b.yaml two.ms
  rang-core: flag: done 2026-11-11T11:51:41+00:00, skipped      exit=0
  ```
- **Fix:** add `config_path` to `stage_hash(config, stage, config_path=None)`. Add to `part`
  a `files` map from each referenced path to the SHA-256 of its content, with paths resolved
  as the stages resolve them: `core_pipeline._resolve_path` for strategy and lsm, and as
  CLI-10 proposes for masks. A missing file hashes to null, and the stage then fails as it
  does now. `execute` passes `config_path`.
  Every existing stage hash changes once. Say so in the CHANGELOG with `--force`, as G7 did.
  Add a test: edit strategy.yaml, then `flag` is refused as changed, and `--force` reruns it.
- **Small and unambiguous:** mostly (about 25 lines plus a test). The one choice is the
  list of file-valued keys.

## CLI-05: should-fix. The conflict message gives a flag that the single-stage commands reject

- **Where:** python/rang/core_pipeline.py:2430 and python/rang/core_cli.py:1248-1263.
- **What is wrong:** the refusal says "pass --force flag", but `rang-core flag` takes a bare
  `--force`. Following the message gives an argparse error.
- **Evidence:**
  ```
  $ rang-core --no-receipt flag a.yaml two.ms
  rang-core flag: refused
  flag finished with a different configuration (sections fields, data, flag); pass --force flag to run it again, which first restores the flags saved before it
  exit=2
  $ rang-core --no-receipt flag a.yaml two.ms --force flag
  rang-core flag: error: unrecognized arguments: flag
  exit=2
  ```
- **Fix:** the simplest is to make the single-stage `--force` accept the stage name
  optionally: `p.add_argument("--force", nargs="?", const=name, choices=[name])`, normalised
  to a bool in `_pipeline`. The other way is to change the message to "pass --force (with
  rang-core run: --force flag)". Add a test that runs the printed hint.
- **Small and unambiguous:** yes.

## CLI-06: should-fix. Malformed configuration values crash with a TypeError traceback

- **Where:** python/rang/core_config.py:652-670 (`_check`: the null branch and `bad()` return
  the refused value) and the consumers in `resolve` and `_selfcal_errors` (for example :936).
- **What is wrong:** after recording a schema error, `_check` keeps the bad value, and
  `resolve` goes on to iterate or hash it. A brute-force pass over every leaf of `SCHEMA`,
  `TERM_KEYS` and `TARGET_KEYS`, with values None, True, 3, 1.5, "x", [], [1], {}, found 11
  distinct non-`ConfigError` exceptions. Plausible user forms:
  - `terms:` with nothing after it, which YAML reads as null;
  - a scalar `selfcal.clean_cutoff: 3`;
  - `interp: linear` as a string instead of a list;
  - a list as a term `name`;
  - a list as `selfcal.input_column`.
  `config check` and every pipeline command end in a traceback with exit 1, not the exit 2
  report.
- **Evidence:**
  ```
  $ printf 'version: 1\ncalibrate:\n  secondary:\n    terms:\n' > c5.yaml; rang-core config check c5.yaml
  TypeError: 'NoneType' object is not iterable          exit=1
  $ printf 'version: 1\nselfcal: {clean_cutoff: 3}\n' > c6.yaml; rang-core config check c6.yaml
  TypeError: 'int' object is not iterable               exit=1
  ```
  The other cases: `TypeError: cannot use 'list' as a set element` for
  `selfcal.input_column=[]`, `cannot use 'list' as a dict key` for a term `name=[]`, and
  `object of type 'bool' has no len()` for a term `interp=True`.
- **Fix:** when `_check` records an error, return the key's default and go on. For kinds
  `terms` and `targets`, return the default normalised through `_check`. I checked this by
  wrapping `_check` with it; the same brute-force pass then gives 0 crashes:
  ```python
  n = len(errors); out = ...existing body...
  if len(errors) > n:
      d = copy.deepcopy(key.default)
      return _check(path, key, d, []) if key.kind in ("terms", "targets") else d
  ```
  This is easiest as a wrapper around the existing body. Add a parametrised test that
  resolves every leaf with those values and allows only `ConfigError`.
- **Small and unambiguous:** yes (about 6 lines plus a test of about 25 lines).

## CLI-07: should-fix. User-facing messages and help name stale task IDs and internal notes

- **Where and what:**
  - core_pipeline.py:135: `UNSUPPORTED = "(unsupported data, task W4: research/w4-unsupported.md)"`
    is appended to every data refusal. A wheel user has no `research/`.
  - core_pipeline.py:483: "MODEL_DATA from the imager is task G6". G6 is done and
    `image.write_model: true` exists, so the message says that a feature which exists does
    not. **This one is false, not only jargon.**
  - core_pipeline.py:304: "(task G9)". :474: "(research/c4b-apply-ms.md, owner decision 2)".
    :1902: "(built before task G8)".
  - core_config.py:353: `wgridder_accuracy` doc "task G7". :270: "C6's provisional owner
    decision 1". :1795: the footer of `config defaults`, "(C2e) ... (C6w) ... (C5)". All of
    these are printed by `rang-core config defaults` and in docs/cli.md:273, :299 and :369.
  - Dead task plumbing:
    - No `Refusal` has a task any more. `TASKS` holds only C7a, which nothing uses.
    - `ConfigError.report`'s "not implemented yet (task ...)" branch never runs.
    - `core_pipeline._refused_stage` (:2365) is unused.
    - docs/cli.md:10 still promises refusals "naming the task that adds it", and so does
      the core_config.py:13 docstring.
  - core_cli.py:1002: `apply`'s one-line help says "apply the complex solutions". It applies
    CASA tables too. The line is in `rang-core -h` and docs/cli.md.
  - Receipt version: the core_cli.py:27 and :567 docstrings say version 3. The code
    (`RECEIPT_VERSION = 4`) and docs/cli.md say 4.
- **Evidence:** the quoted lines. `rang-core config check tests/data/w2/e2b.yaml` prints
  "...is a follow-up of research/g9-stokes.md, not implemented".
- **Fix:**
  - Drop "task W4:" and point to the docs page that lists unsupported data, or drop the
    suffix.
  - Change :483 to "...; write a calibrator model with model.source setjy, manual or lsm, or
    MODEL_DATA from an image with image.write_model: true".
  - Strip the task and owner-decision references from the messages and key docs.
  - Delete `_refused_stage` and the dead `TASKS` branch, or keep the branch but fix the
    docs/cli.md:10 and docstring sentences.
  - Make `apply` "apply the solutions (complex or CASA tables), writing CORRECTED_DATA".
  - Regenerate docs/cli.md with docs/gen_cli.py. tests/test_w2_commands.py:660, :669 and :685
    (at 2bac745) match "W4" and need updating. tests/test_w4_unsupported.py may match too.
- **Small and unambiguous:** yes as text. It touches two tests and the generated page.

## CLI-08: later. Data from other telescopes is neither refused nor flagged as outside the tested scope

- **Where:** python/rang/core_pipeline.py:233 (`check_data`).
- **What is wrong:** only `cal_refant` reads `OBSERVATION.TELESCOPE_NAME`, and only for
  `refant: auto`. A 4-correlation linear-feed MS from ASKAP or LOFAR runs every stage with
  MeerKAT defaults, such as Tricolour's static masks and `feed_angle_rotation`. Nothing in the
  receipt, state or log says it is outside MeerKAT scope (AGENTS.md says "MeerKAT first").
  research/w4-unsupported.md's 28 cases do not include it.
- **Evidence:** `grep -rn TELESCOPE_NAME python/rang/core_pipeline.py python/rang/cal_*.py`
  gives cal_refant.py only.
- **Fix:** read TELESCOPE_NAME in `inspect_ms`. When it is not MeerKAT, print a log line,
  record `telescope` in the state and summaries, and make it a W4 table row. Do not refuse,
  so LOFAR can be kept in mind.
- **Small and unambiguous:** small. Warning versus refusal is the owner's choice.

## CLI-09: later. Small parsing and exit-code inconsistencies in core_cli

- **Where:** python/rang/core_cli.py:1090-1104 and :1384, with :1253 for `run --force`.
- **What is wrong:**
  - `rang-core --no-receipt --version` exits 1 with "unknown option --version" and the usage.
    `--version` is recognised only as the first argument.
  - A bare `--receipt` at the end of the line reports "unknown option --receipt".
  - An unknown command or option exits 1, while argparse errors and refusals exit 2.
  - `rang-core run CONFIG MS --force selfcal` is accepted and does nothing when selfcal is
    not in `run.stages`.
  - The `run` help does not say that `all` forces every stage *of run.stages*.
- **Evidence:** `rang-core --no-receipt --version`, then `exit=1` and the usage text. For
  the others, the code at the lines above.
- **Fix:**
  - Handle `--version` in `_global_options`.
  - Make the message "--receipt needs a PATH".
  - Use `SystemExit(2)` with the message on stderr for unknown commands and options.
  - In `_pipeline`, refuse (exit 2) a `--force` stage that is not in the stages being run.
- **Small and unambiguous:** yes.

## CLI-10: later. Mask paths resolve against the working directory, unlike strategy and lsm

- **Where:** python/rang/core_pipeline.py:1952 and :2222 pass `image.fits_mask` and selfcal
  FITS `cleanmask_method` to gemclean as given. :908 and :1248 resolve `flag.strategy` and
  `calibrate.model.lsm` against the configuration file (`_resolve_path`). The schema doc says
  "(relative to this file)" for the strategy only.
- **What is wrong:** a configuration that works from its own directory fails from another,
  late, with gemclean's error tail (exit 1). Nothing is written wrongly.
- **Fix:** resolve both with `_resolve_path(..., ctx["config_path"])` before building argv
  (`{field}` substitution first), check that they exist in `preflight`, and say "relative to
  this file" in the two key docs.
- **Small and unambiguous:** yes.

## CLI-11: later. Refusal wording a user has to decode

- **Where:** python/rang/core_config.py:1516-1549 (`COMPLEX_HAS_NO`, `_term_refusals`) and
  the `_terms` unknown key.
- **What is wrong:**
  - `refant: auto` with the default primary term (complex) gives "the complex term solves
    QuartiCal bins (solint inf, int or N integrations; freqint) with no CASA rules; use K, G
    and B terms for refant ['auto']". That message is a Python list repr, and the phrase "QuartiCal
    bins" is jargon.
  - The default `calibrate.primary.terms` is `[{type: complex}]`, so any `calibrate.refant`
    hits this refusal.
  - An unknown term key says only "unknown term key", while unknown section keys list the
    known keys.
- **Evidence:** `rang-core config check c2.yaml`, where c2 is `calibrate: {refant: auto}`
  and image is set.
- **Fix:**
  - Format the values as YAML, not repr.
  - Reword: "calibrate.refant is not used by a complex term (it has no reference antenna);
    remove it or solve K, G and B terms".
  - List the keys allowed for the term's type.
- **Small and unambiguous:** yes.

## CLI-12: later. The pipeline help overstates validation and understates the refusal

- **Where:** python/rang/core_cli.py:1276 and the generated docs/cli.md:81, :102, :144 and
  :185.
- **What is wrong:**
  - "Validates the configuration for every stage first": a single-stage command checks
    refusals for that stage only. Schema errors are checked everywhere.
  - "a finished stage is skipped unless forced" omits that a finished stage whose
    configuration changed is refused (exit 2) until it is forced.
- **Fix:** "Validates the configuration for the stages it runs first. A finished stage is
  skipped, or refused when its configuration changed, unless forced. A failed or stale one
  runs again." Then regenerate docs/cli.md.
- **Small and unambiguous:** yes.

## CLI-13: later. Duplicate YAML keys are accepted silently

- **Where:** python/rang/core_config.py `loads` (`yaml.safe_load`).
- **What is wrong:** PyYAML keeps the last of repeated keys. Two `image:` blocks give
  "image.size: required" for the block that was dropped. A repeated scalar such as `niter`
  gives no message at all.
- **Evidence:** `version: 1 / image: {size: 64, scale: 2asec} / image: {niter: 5}` gives
  "image.size: required, image.scale: required".
- **Fix:** use a `SafeLoader` subclass whose `construct_mapping` raises `ConfigError` on a
  duplicate key, naming the line (about 12 lines plus a test).
- **Small and unambiguous:** yes.

---

## Notes, not findings

- **Windows lock:** at 3eab67c, `RunDir.locked` had no lock on Windows, and `_alive` is
  always False there. 2bac745 adds an msvcrt lock during this review, so that one is handled.
- **Version:** `rang-core --version` prints 0.1.0, as in pyproject. The bump to 0.2.0 is a
  release step (tests/test_w4_5_release.py), not a finding.
- **`average_time`:** absent from the schema, `config defaults`, docs/cli.md and the
  CHANGELOG at both commits. If the other session adds it, it needs a key doc, a CHANGELOG
  line and a docs/cli.md regeneration.
- **Results not in the stage hash:** `RANG_SOLVE_OPTIONS` changes complex-solve results.
  It is recorded in the receipt (`environment.rang_environment`) but is not part of the
  stage hash, so changing it does not make a stage rerun. This is acceptable as it is
  documented.
- **Checked and fine:**
  - The receipt has the schema version, source (checkout, distribution version, extension
    SHA-256), every `RANG_*` variable, thread settings, the config file by SHA-256 and the
    MS by listing hash (size and mtime).
  - Unknown section keys list the known keys.
  - `version: 2` is refused clearly.
  - A missing config or MS gives exit 2 with a clear message.
  - The multi-data-description, circular, one-correlation, correlation-order, missing
    FLAG/FLAG_ROW, missing-weights and empty-selection refusals exist as research/w4-unsupported.md
    lists them, and the tests cover them.
  - The image, selfcal and calibrate refusals in tests/data/w2/e2a.yaml and e2b.yaml are
    reported in one pass.
- **Scratch files:**
  <scratch>\e5-cli\repro_run.py
  (CLI-01, CLI-03, CLI-04, CLI-05),
  <scratch>\e5-cli\fuzz.py
  and <scratch>\e5-cli\fuzzfix.py
  (CLI-06).
