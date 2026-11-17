# E5 final: review of the code new since the pre-review (353e620..b6e8b52)

Reviewer B, 2026-11-12, read-only. Scope: `git diff 353e620 HEAD -- python core src docs notebooks
examples README.md CHANGELOG.md pyproject.toml .github`, SPDX-only lines ignored.

**How things were run.** The main checkout's venv (`~\Github\rang\.venv`) has a stale
extension (NEW-01), so every command that reads an MS was run with
`~\Worktrees\rang\sliced-read\.venv\Scripts\python.exe`, whose `python/` differs from
b6e8b52 by one SPDX line (`git diff --stat` checked) and whose `_core.pyd` was built 13:05 today.
Test MS: `python -m rang.simtruth_ms generate small . --workers 2` (5.7 s, 41 MB), scratch only in
`<scratch>\agentB\`
(`fuzz.py`, `fuzz2.out`, `flagt/`). No cargo/maturin, nothing heavy, no E3 results opened.

Touch flag: **P** = the fix touches a protected file (core_config.py, core_pipeline.py, cal_*.py,
core_ms*.py, core_flag*.py, core_writeback.py or Rust): list it, don't fix it now. **D** = only
docs/tests/packaging (or another unprotected file, named).

## Summary

| # | Class | Touch | One line |
| --- | --- | --- | --- |
| NEW-01 | should-fix (env: urgent) | env + P | main venv's `_core.pyd` is older than the sliced-read Python: every MS read crashes |
| NEW-02 | should-fix (falls under E5-10, open until E6) | D | CHANGELOG Unreleased says selfcal `refant: auto` is refused; it now runs |
| NEW-03 | should-fix | D | Item 27 behaviour changes are not in the CHANGELOG (unset refant = auto; niter 100000 to 1000000) |
| NEW-04 | should-fix | D | tutorial says receipt version 4; the code writes 5 |
| NEW-05 | should-fix | P | flow-style or misspelt strategy: bare `KeyError: 'task'` traceback, exit 1; config check says valid |
| NEW-06 | should-fix | P | config check passes with a missing strategy file, a directory as strategy, a directory as fits_mask |
| NEW-07 | should-fix | P | unknown `calibrate.refant` name passes config check with the MS; calibrate gives a traceback |
| NEW-08 | should-fix | P | non-UTF-8 config: `UnicodeDecodeError` traceback, exit 1 |
| NEW-09 | note | P | an empty strategy (only comments) runs flag with zero steps, exit 0 |
| NEW-10 | note | P | `calibrate.average_freq` with a complex term is not refused (average_time is) |
| NEW-11 | note | P | `reader_slice` differs from NumPy past the end, and cuts the corr axis of 1-axis columns |
| NEW-12 | note | D | the sliced MS read (2.1-2.2x) is not in the CHANGELOG |
| NEW-13 | should-fix | D (simtruth_ms.py) | `simtruth_ms.git_facts` crashes without git, and records the wrong repo from a wheel |
| NEW-14 | note | D | small tutorial wording mismatches (flag versions per stage, what config check covers) |
| NEW-15 | note | D | `rang-core --version` prints 0.1.0 (version not bumped yet) |

Checked with no finding: the validation of the three new keys (strict bool), their presence in
`config defaults` and `docs/cli.md` (`python docs/gen_cli.py --check` gives rc 0), the off-by-default
paths as read in cal_chain, cal_gain, cal_pol, cal_chunks and core_pipeline (cal_delay's averaged
branch was not read), the windowed pre-apply (cal_apply.py, apply.rs), the stage-hash exclusion, the duplicate-key loader, the CLI exit codes (E5-40), the
flagversions completion-on-rerun change (E5-42), the Rust slice arithmetic for the tiled manager.

---

## NEW-01: the main checkout's venv has a stale extension; every MS read fails

- **Class:** should-fix for the release (a wheel user gets matching `.pyd` and `.py`). For the
  environment it is urgent: anything run from `~\Github\rang\.venv` today that opens
  an MS crashes, and that includes an acceptance test if it runs there.
- **Evidence:** `~\Github\rang\python\rang\_core.pyd` is dated 2026-11-12 07:04. Merge
  2899c23 (sliced-read) is dated 14:59. `core_ms.Table.getcol` now calls
  `self._table.read(name, start, count, cut)` (python/rang/core_ms.py, `getcol`), and the old
  extension takes 3 arguments. Main is at 2899c23, so its Python is the new code.
- **Reproducer:** `~\Github\rang\.venv\Scripts\python.exe -m rang.core_cli config check
  config.yaml a1-small.ms` on the tutorial config gives
  `TypeError: MsTable.read() takes 3 positional arguments but 4 were given`, exit 1. Of 46 configs in
  `fuzz.py`, 10 failed this way: every one that got past the schema to the MS.
- **Fix:** `maturin develop --release` in the main checkout (env). A guard would also help (P,
  core_ms.py / `rang/__init__`): compare an ABI or version stamp exported by `rang._core` with the
  Python package's, and say "the extension is older than the Python code: rebuild it" instead of a
  TypeError.

## NEW-02: the CHANGELOG says selfcal `refant: auto` is refused; since f11fdd1 it runs

- **Class:** should-fix. On its face this is release-blocking (the release notes state something
  false), but it is one more case of the known open item E5-10 (research/e5-prereview.md:60:
  "Unreleased ... states behaviour later entries undo", with `refant: auto` "refused" given as an
  example; an editorial rewrite at E6 is planned). Release-blocking if E6's rewrite does not happen
  before the tag.
- **Confirmed by running:** `config check sc_auto.yaml a1-small.ms` (the tutorial config with
  selfcal in `run.stages` and `selfcal: {refant: auto}`) gives "valid for flag, calibrate, apply,
  image, selfcal", exit 0.
- **Evidence:** CHANGELOG.md:173 (inside `## Unreleased`, the C5 entry) says "`complex`
  self-calibration terms and `refant: auto` in selfcal are refused." f11fdd1 ("Item 27") removed
  that refusal from `core_config.refusals` (diff: the `selfcal.refant` "auto is resolved by calibrate
  only" Refusal is gone). `core_pipeline` `_selfcal_refant` now resolves `auto` through
  `cal_refant.caracal_refant`. The schema help now says "auto: the first of CARACal's choice"
  (core_config.py, `selfcal.refant`).
- **Fix (D):** change line 173 to say that only `complex` self-calibration terms are refused, and add
  the NEW-03 entry.

## NEW-03: Item 27's behaviour changes are not in the CHANGELOG

- **Class:** should-fix (the release notes are incomplete; results change for users on the defaults).
- **Evidence:** in commit f11fdd1 (core_config.py, core_pipeline.py, cal_refant.py):
  1. An unset `calibrate.refant` used to be refused ("required for K, G, B, F, Gpol and Df
     (calibrate.refant)", removed from `_chain_refusals`). It now means CARACal's auto, or antenna 0
     when no antenna qualifies (`cal_refant.default_choice`, cal_refant.py:193).
  2. The default selfcal refant changed from antenna 0 to that same choice (core_pipeline
     `_selfcal_refant`). The selfcal stage hash does not cover `calibrate`
     (`STAGE_SECTIONS["selfcal"] = ("fields", "data", "image", "selfcal")`, core_config.py:628), so
     a resumed run notices neither this change nor a later edit of `calibrate.refant`.
  3. The `image.niter` default went from 100000 to 1000000 (core_config.py, `image.niter`;
     docs/cli.md:310 is updated).

  `grep -n "niter\|1,000,000\|Item 27" CHANGELOG.md` finds none of these in Unreleased.
- **Fix (D):** a "Changed:" entry for all three.

## NEW-04: the tutorial says receipts are version 4; the code writes version 5

- **Class:** should-fix (the notebook states something false; the user can see the real version in
  the printed output).
- **Evidence:** notebooks/00-ms-to-image.ipynb, section 4.6 markdown: "(schema `rang.receipt`,
  version 4)". The code has `RECEIPT_VERSION = 5` (python/rang/core_cli.py:85), and docs/cli.md:44
  and the CHANGELOG both say 5. The module docstring at core_cli.py:28 and the comment at
  core_cli.py:573 still say "version 3".
- **Fix (D, plus core_cli.py docstrings, which are not protected):** "version 5" in the notebook and
  in both core_cli.py places.

## NEW-05: a flow-style or misspelt Tricolour strategy gives a bare KeyError traceback

- **Class:** should-fix (a clear message is missing). The MS is safe: the flags are unchanged and
  a rerun recovers.
- **Evidence:** `core_flag.parse_strategy` (python/rang/core_flag.py:91-130) is a hand-written
  line parser. It does not understand flow mappings, so `encode_steps` (core_flag.py:154,156) does
  `strategy["task"]` and `TASK_CODES[task]` on whatever it produced. Nothing checks the strategy's
  contents before the flag stage runs: `config check` neither reads nor parses the file.
- **Minimal reproducer** (confirmed). `strategy.yaml`:
  ```yaml
  strategies:
    - {name: x, task: flag_autos}
  ```
  `parse_strategy` returns `[{'kwargs': {}, '{name': 'x, task: flag_autos}'}]`, then
  `encode_steps` raises `KeyError: 'task'`. With the tutorial config pointing at it,
  `rang-core config check c_flow_item.yaml t.ms` says "valid for flag, calibrate, apply, image" and
  `rang-core flag c_flow_item.yaml t.ms` gives the traceback, exit 1. By then the flag version
  `rang_flag_<time>` has been saved and the journal `rang-writeback.json` records the error. A rerun
  with a good strategy recovers ("running (was failed)", `rang_rerun_<time>` saved, done), so no
  data is lost. Variants:
  - `task: sumthreshold` (a typo) gives `KeyError: 'sumthreshold'`.
  - a strategy with no `task:` line gives `KeyError: 'task'`.
  - `kwargs: {outlier_nsigma: 5}` gives `ValueError: dictionary update sequence element #0 has length 1; 2 is required`.
  - `strategies: [{name: x, task: flag_autos}]` gives `ValueError: unexpected line outside a strategy`.
  - a `#` inside a quoted value is cut as a comment (core_flag.py:103).
- **Fix (P: core_flag.py, core_pipeline.py/core_config.py):** read the strategy with
  `yaml.safe_load`, since CARACal's files are plain YAML. Check each entry: a mapping with `name`,
  `task` in `TASK_CODES` ("unknown task 'sumthreshold'; known: ...") and `kwargs` a mapping. Run
  that check in `config check` and in the run's preflight, so the error comes as a refusal (exit 2)
  before any flag version is saved.

## NEW-06: config check passes a missing strategy file, a directory as strategy, a directory as mask

- **Class:** should-fix. The tutorial says config check "validates the whole file against the
  schema and the MS before anything is written".
- **Evidence (`fuzz2.out`):** these all exit 0 with "valid for flag, calibrate, apply, image":
  - `flag.strategy: nope.yaml`
  - `flag.strategy: .`
  - `image.fits_mask: .` (`_missing_masks` tests `.exists()`, core_pipeline.py `_missing_masks`)

  At run time, `stage_flag` raises `StageFailed("flag.strategy: ... not found")`
  (core_pipeline.py `stage_flag`). That happens before the stage writes, so the data is safe, but
  it surfaces as a stage failure rather than a refusal from config check. A directory given as
  `fits_mask` would reach gemclean.
- **Fix (P: core_pipeline.py / core_config.py):** in config check and the run preflight, require
  `flag.strategy` (and each A term's `strategy`) to be a file, parse it (NEW-05), and require masks
  with `is_file()`.

## NEW-07: an unknown `calibrate.refant` passes config check; calibrate gives a traceback

- **Class:** should-fix.
- **Evidence:** in the tutorial config, `refant: m999` makes `config check c.yaml a1-small.ms` exit 0
  ("valid"), even though the MS is given. Then `rang-core calibrate c_ref.yaml t.ms` gives
  `ValueError: list.index(x): x not in list` at python/rang/cal_delay.py:284
  (`names.index(r) ...`), exit 1, after 2 s.
- **Fix (P: core_config.py/core_pipeline.py, or cal_delay.py):** when an MS is given, resolve every
  refant (calibrate, terms, selfcal) against ANTENNA.NAME and its row count. The message should say
  "calibrate.refant: no antenna m999 (antennas: m000 ... m015)".

## NEW-08: a non-UTF-8 config file gives a UnicodeDecodeError traceback

- **Class:** should-fix (a Latin-1 comment such as "café" is enough to trigger it).
- **Evidence:** `core_config.load` catches only `OSError` around `path.read_text(encoding="utf-8")`
  (python/rang/core_config.py:645-649). Reproducer: put byte `\xff` in a comment and run
  `rang-core config check nonutf8.yaml`, or `rang-core run nonutf8.yaml ms`. Both give
  `UnicodeDecodeError: 'utf-8' codec can't decode byte 0xff in position 20`, exit 1. The strategy
  files are read the same way (core_pipeline.py `stage_flag`, `read_text(encoding="utf-8")`).
- **Fix (P: core_config.py, core_pipeline.py):** catch `UnicodeDecodeError` and raise
  `ConfigError([("", f"not UTF-8 text: byte {exc.start}")])`.

## NEW-09: an empty strategy runs flag with zero steps

- **Class:** note.
- **Evidence:** a strategy file with only a comment gives `parse_strategy` returning `[]` and
  `encode_steps` returning a (0, W) table. On a copy with 1/3 of FLAG set, `rang-core flag` exits 0
  ("done in 1.6 s"), saves a flag version, and leaves FLAG at 0.333. The data is safe (it did not
  wipe FLAG under `write: replace`), but the user is not told that nothing ran.
- **Fix (P: core_flag.py/core_pipeline.py):** refuse a strategy with no steps.

## NEW-10: `calibrate.average_freq` with a complex term is not refused

- **Class:** note.
- **Evidence:** I made a complex-only config: default terms (`[{type: complex}]`), no refant, no
  uvrange, `run.stages: [calibrate]`.
  - With `calibrate.average_freq: true`, `config check cx_freq.yaml a1-small.ms` gives "valid for
    calibrate", exit 0.
  - With `average_time: true` it is refused, exit 2 ("the complex solve has no time
    pre-averaging: set false").
  - `average_freq` is read only in `stage_calibrate_chain` (core_pipeline.py:1700). The complex
    route (`stage_calibrate` when `uses_chain` is false, core_pipeline.py:1758) never reads it, so
    the key is silently ignored there.
  - The CHANGELOG documents average_time's refusal and says nothing about average_freq.
- **Fix (P: core_config.py):** add the same refusal for average_freq, or document that it is
  ignored there.

## NEW-11: `reader_slice` and the Rust slice differ from NumPy at the edges

- **Class:** note. No user path reaches these cases: `cal_chunks.load` passes chunk slices that lie
  within nchan and slices only columns with a channel axis (`_has_channels`).
- **Evidence (a1-small, 64 channels):**
  - `getcol("DATA", 0, 50, chans=slice(60, 70))` raises `OSError: DATA: slice 60+10 of axis 1 is outside a cell of 64`, where NumPy gives (50, 4, 4).
  - `slice(64, None)` raises "slice 64+0 ... outside", where NumPy gives (50, 0, 4).
  - `slice(70, None)` raises "slice 70+-6", a negative length in the message.
  - `getcol("WEIGHT", 0, 3, chans=slice(1, 2))` returns (3, 1): it cuts the correlation axis without
    a warning.
  - These match NumPy: `slice(63, 64)`, `slice(5, 5)`, `slice(-4, None)`, step 2, `slice(None)` and
    `getcol_rows` in any row order. A row past the end gives a clear error.
- **Fix (P: core_ms.py, core_ms_write.py):** in `reader_slice`, clip `stop` to the cell (or fall
  back to NumPy with `False`) and refuse `chans` on columns whose cells have fewer than 2 axes.

## NEW-12: the sliced MS read is not in the CHANGELOG

- **Class:** note.
- **Evidence:** merge 2899c23 ("channel-sliced MS reads (2.1-2.2x on the pol sets, bit-identical on
  19 frozen comparisons)"). `grep -n -i "slice" CHANGELOG.md` finds nothing in Unreleased.
  `research/sliced-read.md` exists.
- **Fix (D):** one "Changed:" line.

## NEW-13: `simtruth_ms.git_facts` crashes without git and can record the wrong repo

- **Class:** should-fix. The intro notebooks I4-I8 generate A1 from a wheel
  (docs/tutorials/index.md: "From a pip install, I1-I4, I8 and I9 run as they are").
- **Evidence:** `ROOT = Path(__file__).resolve().parents[2]` (python/rang/simtruth_ms.py:39). In a
  wheel install that is the directory above `site-packages`. `git_facts` (simtruth_ms.py:245-254)
  calls `subprocess.run(["git", ...])` with no handling, so:
  - (a) on a machine without git it raises `FileNotFoundError` at simtruth_ms.py:517, after the MS
    is written but before the provenance file;
  - (b) a venv inside a user's git repo records that repo's commit and dirty state as A1's
    provenance.

  simtruth.py was fixed to find the antenna table beside the module; simtruth_ms.py still carries
  the checkout assumption. Confirmed: with `os.environ["PATH"] = ""`,
  `rang.simtruth_ms.git_facts()` raises `FileNotFoundError [WinError 2]`. This contradicts
  docs/tutorials/index.md ("From a pip install, I1-I4, I8 and I9 run as they are") on a machine
  without git.
- **Fix (D: simtruth_ms.py, not protected):** catch `OSError`. Record git facts only when
  `ROOT / "pyproject.toml"` names rang-core (or `ROOT / ".git"` exists); otherwise record
  `rang.__version__`.

## NEW-14: small tutorial wording mismatches

- **Class:** note (D).
- **Evidence:** in notebooks/00-ms-to-image.ipynb:
  - Section 4.1 says "Each writing stage then saves one more [flag version]". Since E5-43, image and
    selfcal (MODEL_DATA) save none; the notebook's own state table shows "– (writes no flags)".
    Say "each stage that writes flags".
  - Section 2 says config check "validates the whole file ... before anything is written". That is
    not true for strategy files and refant names until NEW-05 to NEW-07 are fixed.
  - Section 2's `apply` text lists `parang`, and the `selfcal` text lists Sp, Sa and Sd. Every key
    the notebook names exists in `config defaults` (checked: data.weights, scans, memory_limit_gb,
    flag.write, model sources, fields.xcal, apply.applymode, apply.parang).
  - The config runs Stokes I without selfcal and the section 6 E2 placeholders remain; both are
    expected.

## NEW-15: `rang-core --version` prints 0.1.0

- **Class:** note (D: pyproject.toml at release time).
- **Evidence:** `rang-core -V` prints "rang-core 0.1.0". The tutorial's receipt also records 0.1.0.

---

## Item-by-item record

1. **New config keys.** `bool` is strict (core_config.py `_check_value`: `isinstance(value, bool)`).
   - These were refused with clear messages, exit 2: `-1`, `0`, `'yes'`, `[true]`, `'60s'`, `4`, and
     `1` for selfcal.
   - `average_time: yes` is YAML true and accepted.
   - `selfcal.average_freq` is refused as an unknown key, listing the known ones.
   - `selfcal.average_time` with Sd is refused with a clear message, and so is `average_time` with a
     complex term.
   - All three keys are in `rang-core config defaults` (lines 42, 43, 117) and in docs/cli.md (the
     gen check passes). The CHANGELOG describes them, and its text matches the code
     (cal_chain.py:178 and 215-218: G-type only for average_freq; K, B, KCROSS, Xf and Df are
     unchanged).
   - Off by default really is unchanged:
     - `HASH_DEFAULTS` drops the keys from `stage_hash` at their defaults.
     - `cal_chain.run` adds them to `common` only when true.
     - `_solve_gain_field` takes the `avg is None` branch, which calls the same
       `cal_chunks.load` as before.
     - `frequency_averaged` runs only under `if average_freq`.
     - `_PolField.chunks` goes through `cal_chunks.load` when `average` is false.
     - `chain_chunk_plans` builds an `Average` only when the key is true.

     The off path does change in one way, through the sliced read (`load` now reads only a
     chunk's channels and takes `row_w` from `whole_row_weights`). That is the sliced-read change,
     claimed bit-identical on 19 comparisons; I did not re-measure it. `_ROW_WEIGHTS` is keyed per
     `_Field`/`_PolField` object and row set, and those objects are built per solve, so a stale
     memo was not found.
   - Bad combinations not caught: NEW-10.
2. **Sliced read.** NEW-11 covers the edge cases. In ms.rs, `resolve_slice` checks
   `start < 0 || n < 1 || start + n > size`, and the Tsm path reads only the tiles that intersect
   the slice (`t_lo..=t_hi`). Rows with different cell shapes still give the old "rows of X differ
   in shape" error, which the user cannot act on, but such MSs are refused by `inspect_ms` first
   (w4-unsupported). The non-tiled managers read whole cells and cut them with `cut_cells`.
   `read_rows` checks rows past the end. A 0-row `getcol` gives "nrow must be positive"; that
   message predates this change.
3. **flagversions / writeback / ms_write / pipeline / cli.**
   - `flagversions.save` lists an orphan final version only when no partial exists and it reads back
     equal to the flags. That is sound, and it otherwise refuses.
   - `WriteBack.read_rows` calls `_require()` first.
   - `_version_lost` logs a warning and records `restore_missing`.
   - The CLI exit codes, all verified:
     - `--bogus`, `-x`, a bare `--receipt` and an unknown command give exit 2 on stderr with the
       usage;
     - `--version` works after `--no-pin-threads` and after `--receipt x.json`;
     - `run --force selfcal` outside `run.stages` is refused, exit 2;
     - `--force bogus` is an argparse error, exit 2;
     - a missing MS is refused, exit 2.
4. **simtruth_ms.** Generates A1 small in 5.7 s from the package data (`rang/data/meerkat.itrf.txt`).
   `examples/a1_simtruth.py` is a re-export of the module's `main`. Problem found: NEW-13.
5. **Docs.** `python docs/gen_cli.py --check` gives rc 0. docs/index.md, docs/tutorials/index.md,
   docs/api/index.md and docs/concepts/imaging.md were read with no finding beyond NEW-04 and
   NEW-14. Every config key the tutorial names exists and means what the text says. Problems
   found: NEW-02, NEW-03, NEW-04, NEW-12, NEW-14.
6. **The strategy KeyError.** Confirmed: NEW-05, with the minimal reproducer.
7. **Malformed configs.** 46 cases in `fuzz.py`, results in `fuzz2.out`:
   - Clear refusals, exit 2: wrong types; unknown keys and sections (the known keys are listed); an
     empty or comment-only file ("version: required (default 1)"); a YAML list or scalar ("must be
     a mapping"); duplicate keys at the top level and nested (with line numbers); bad YAML; tabs;
     version 2; a section that is a list or scalar; bad `run.stages`; `strategy: null`; a missing
     `fits_mask` file; an integer key; a merge-anchor top-level key (refused as unknown); memory 0
     or negative; `chunk_rows: 0`; `refant: []`; `refant: true`.
   - Problems found: NEW-06, NEW-07, NEW-08.

## Context and limits of this review

- **Same code.** The sliced-read worktree I ran from differs from b6e8b52 by SPDX lines only:
  `git diff --stat a664fdf b6e8b52 -- core src` shows 2 files with +2 lines, and `-- python` 1 line.
- **The windowed pre-apply was read.** This is the path the default chunked B/Xf/Df solve now takes.
  In core/src/cal/apply.rs each term's table is resampled over the whole window (`nband`) and
  indexed at `first + c`; `check` requires `first_chan + nchan <= freq.len()`. In
  python/rang/cal_apply.py, `channels.indices()` must be unit-step and match `data.shape[1]`. No
  finding.
- **Prior decisions.** The E5 pre-review covers related items:
  - E5-10 (superseded CHANGELOG statements, open until E6): NEW-02.
  - E5-21 (the stage hash covers strategy files by path only, open until after E2): related to
    NEW-05/06, but a different defect.
  - E5-31 (ship a strategy): the tutorial's strategy.yaml.

  I found no pre-review entry for NEW-05, 06, 07 or 08 (grep for strategy, refant, config check and
  utf in research/e5-prereview.md). In the code they predate 353e620 apart from what the new keys
  touch, so they are pre-existing defects, found now.
- **Not reviewed** (in scope, not opened, or only skimmed):
  - python/rang/check.py (+316), .github/workflows/docs.yml, docs/execute_notebooks.py, docs/conf.py
    and pyproject.toml beyond the package-data lines;
  - core/py/src/lib.rs (the real FFI of the sliced read; only its Python callers were exercised),
    core/src/ms_write.rs, python/rang/cal_selfcal.py, cal_refant.py beyond `default_choice`, and
    cal_delay.py's averaged branch;
  - the intro notebooks i1-i9 (a grep of i5-i8 found no receipt version and no average_* key; the
    keys they set are exercised by the nightly docs run, which would fail on a config error) and
    docs/_extra/interferometer;
  - E2/E3 results (excluded by the brief).

## For the coordinator

- Act now: NEW-01. Rebuild the main checkout's extension (`maturin develop --release`) before
  anything else uses `~\Github\rang\.venv`, and check which venv the running acceptance
  test uses.
- No new release-blocker unless E6's CHANGELOG rewrite (E5-10) slips. In that case NEW-02 is one,
  a one-line fix. Fold NEW-03 and NEW-12 into the same edit.
- Docs/unprotected should-fixes that can be done now: NEW-04 (notebook and core_cli.py docstrings),
  NEW-13 (simtruth_ms.py), NEW-14.
- Protected, list for after the acceptance test: NEW-05, 06, 07, 08 (all "a clear message is
  missing"; no data lost), and NEW-09, 10, 11.
