# E5 pre-review: documentation and help against the code

Checkout `<worktree>`, main at 3eab67c, 2026-11-11. Read-only.
Python: `<main checkout>\.venv\Scripts\python.exe` (3.14), `PYTHONPATH=<checkout>\python`.
Scratch: `<scratch>\e5-docs`
(`cli.generated.md`, `gemclean-help.txt`, `links.py`).

Classes: **RB** release-blocking (a user following the docs fails or is told something false),
**SF** should-fix, **L** later. "E4" = belongs to the tutorial / reference / landing-page task.

## Checks that passed (no finding)

- `docs/gen_cli.py` builds the page from the argparse help in subprocesses; `gen_cli.page()` written
  to scratch is byte-identical to `docs/cli.md` (`diff` empty, 8 s). `tests/test_d1_docs.py:33` asserts
  `page == gen_cli.page()`. The hand-written INTRO of gen_cli.py checked against code: receipt schema
  `rang.receipt` version 4 (`core_cli.py:70,79`), `<ms>.rang-run` (`core_pipeline.py:129`), `rang_original` and
  `rang_<stage>_<UTC>` flag versions (`core_pipeline.py:19,794`): all agree.
- Documented config keys in prose: 38 distinct backticked `section.key` names in README, CHANGELOG, docs/**/*.md,
  gen_cli.py INTRO and research/w2-commands.md all exist in `SCHEMA`/`TERM_KEYS`/`TARGET_KEYS` (checker
  `scratchpad/e5-docs/keys.py`, verified on a planted `image.nonsense`). No documented key has been removed.
- `rang-core config defaults` in cli.md is generated from `core_config.SCHEMA`, so every key and
  default printed there matches the code by construction. gemclean-related defaults
  (`gain` 0.1, `nmiter` 20, `threads` all cores, `auto_mask_nmiter` 2, `wgridder_accuracy` 1e-4) agree
  with `gemclean -help` and with `core/src/gemclean/cli.rs:295` (`epsilon: 1e-4`) and `:720`
  (`single = precision.unwrap_or(epsilon >= 1e-5)`). CHANGELOG Unreleased G7 entry agrees.
- `rang-core --version` -> `rang-core 0.1.0`; `rang.core.backend_name()` -> `extension`.
- Internal links: of 169 `{gh}`/`{ghdir}`/`{doc}`/markdown links in README, CHANGELOG, CONTRIBUTING and
  docs/**/*.md, every local one resolves (external URLs other than the repo's own GitHub paths were not fetched;
  checker verified on a planted broken link: 3/3 caught); the logo files and `.github/workflows/{docs,wheels}.yml`
  that README's badges and picture name exist; every
  `https://github.com/gijzelaerr/rang-core/blob|tree/main/<path>` in README exists in the checkout;
  backticked repo paths in cli.md, CHANGELOG, docs exist (one old CHANGELOG rename note excepted, correct as history).
- README research `rang-core research ...` stages all exist in `core_cli.STAGES`.
- Quick start API: `download_fixture(cache_dir)`, `load_fixture(source, cache_dir=)`, `summary()["dataset"|"antennas"|"channels"]`,
  `gains.solve(ds)["metrics"]["tv"|"losses"]["test"]` all exist. **Printed numbers not re-run**: the fixture is
  not on this host and downloading it needs permission.
- Configs in the repo: `research/results/e1-chain-scripts/e1_config.yaml` valid for every stage;
  `tests/data/w2/e2b.yaml` valid for its run.stages; `tests/data/w2/e2a.yaml` fails
  (`image.auto_mask` needs `mgain`), which `tests/test_w2_commands.py:730` asserts on purpose: not a finding.

## Findings

### DOC-01 RB: README and docs/index say gemclean is not in the wheels
- Files: `README.md:26-27`, `docs/index.md:39-40`.
- Wrong: "It is not in the wheels: cargo build ... --bin gemclean". Since G8 the wheel has the console script
  (`pyproject.toml:77` `gemclean = "rang.gemclean:main"`; CHANGELOG Unreleased "New: `gemclean` is in the wheel";
  `python -m rang.gemclean -version` -> `gemclean 0.1.0`), and `image.gemclean: auto` uses the extension only.
- Fix: "`gemclean` (also `python -m rang.gemclean`) ships in the wheel; `gemclean -help` lists its options.
  A source binary: `cargo build --manifest-path core/Cargo.toml --profile gemclean --bin gemclean`."
- Small, unambiguous. E4 (landing pages).

### DOC-02 RB: README command table says calibrate is `complex` only and omits apply and selfcal
- File: `README.md:91` (also `docs/index.md:41-42` lists only flag, calibrate, image, run).
- Wrong: "solve (`complex` only so far)". Code runs K, G, B, A, F (C2e), Gpol, KCROSS, Xf, Df (C6w)
  (`config defaults` footer, `core_pipeline.py:1321`); `apply` and `selfcal` are user commands (`core_cli.py:999-1006`).
- Fix: row "`flag`, `calibrate`, `apply`, `image`, `selfcal`, `run` `config.yaml my.ms` | flag (Tricolour port);
  solve CARACal's K, G, B, A, F and polcal terms or `complex`; apply; image with `gemclean`; self-calibrate; resume".
  Same list in docs/index.md:41.
- Small, unambiguous. E4.

### DOC-03 RB: concepts/imaging says the wgridder is not in the extension and builds with cargo
- File: `docs/concepts/imaging.md:33-35`; same claim `docs/concepts/index.md:4-5` ("in the extension `rang._core`
  except the exact wgridder").
- Wrong: "It is not yet bound in the extension: on first use it builds a standalone library with `cargo`".
  `python/rang/core_wgridder.py:25` ("Since DF2b ... the extension `rang._core` binds the" gridder); `RANG_DF1_LIB`
  is `retired` (W4-3 removed the fallback, cli.md env table); `docs/installation.md:19-21` says no kernel runs Cargo.
- Fix: delete the sentence in imaging.md; in index.md drop "except the exact wgridder ({doc}`../installation`)".
- Small, unambiguous. E5 (or E4 if it owns concept pages).

### DOC-04 RB: concepts/imaging says rang has no production deconvolver
- File: `docs/concepts/imaging.md:52-54` ("## Deconvolution ... rang has no production deconvolver").
- Wrong: GeMClean is the imager of `rang-core image` and `selfcal` (multiscale, masks, channels, Stokes,
  MODEL_DATA). The concepts index table (`docs/concepts/index.md:9-18`) and line 30 ("the command line replays the
  archived campaigns") also predate W2: no calibrate terms, apply, GeMClean, selfcal, config.
- Fix: replace the section with a GeMClean paragraph (exact image-domain value per minor step, WSClean 3.7 as the
  oracle, defaults 1e-4 single precision, link research/gemclean.md, g7-defaults.md); add rows for
  calibrate (`rang.cal_chain`, CASA 6.7.6 / CARACal), apply (`rang.cal_apply`), image (gemclean, WSClean 3.7),
  selfcal (`rang.cal_selfcal`, QuartiCal); line 30: "and runs flag, calibrate, apply, image and selfcal on your MS".
- Not small (needs prose). E4 (concept/landing pages).

### DOC-05 RB: v0.2.0 scope statements are missing everywhere a user reads
- Files: `README.md:9-17` status box, `docs/index.md:15-28`, `CHANGELOG.md` Unreleased.
- Required by `research/finish-plan.md` section 7: item 6 ("v0.2.0 states that native data is not yet tested");
  items 25/29 (selfcal model-absorption limit accepted for v0.2.0; only a passing mention in CHANGELOG:53);
  item 33 (refant leakage limit of CARACal's strategy 1; 530 flag cells against Tricolour; time pre-averaging
  differs from CubiCal); item 19 (`feed_angle_rotation` in memory only, so CASA reading the MS applies a different P);
  item 11 (K offsets not in the K table, G absorbs them; "to be stated wherever a K table is applied alone");
  section 1 exclusions (L-band only, no UHF/S, no direction-dependent calibration, no GPU in GeMClean).
  `grep -i` over README, docs/*.md, docs/*/*.md, CHANGELOG: no statement that native data is untested (the only
  "native data" is `docs/tutorials/index.md:34`, about reopening the flagging question), no "direction-dependent",
  no UHF/S statement; "absorption" only CHANGELOG:53. No novelty claim is present (README:10, docs/index.md:17): OK.
- Fix: a "Scope and limits of v0.2.0" section in README and docs/index (or a docs/limits.md linked from both) and in the
  0.2.0 CHANGELOG section: tested on processed LUNO data, ESO137 and simulation, not on native SARAO data; L-band;
  selfcal can absorb unmodelled flux into gains (masks do not lift it); polarisation rests on LUNO plus simulation,
  refant leakage drift; FEED not rewritten; a short list of refused options (C2e item 15: `solnorm: true`, `calmode: a`,
  `gainfield` on pre-applied tables, complex mixed with CASA terms; G3/G9/G5 gemclean refusals; selfcal with pol other
  than I) with a pointer to `rang-core config check CONFIG --all` for a given configuration (it prints only that
  configuration's errors: on e1_config.yaml "valid for flag, calibrate, apply, image, selfcal"); no novelty claim.
  The status box should also say the MS commands exist (it lists only research verdicts).
- Not small (text depends on E2/E3 outcomes). E4 for the landing text, E5 to check it at release.

### DOC-06 SF: `apply` help says "apply the complex solutions"
- Source: `python/rang/core_cli.py:1002` (`USER_COMMANDS["apply"]`), shown in `docs/cli.md:60` and `:120-124`.
- Wrong: apply also applies the CASA tables (K, G, B, F, polcal) and P (`core_pipeline.py:1750-1810`, `:1804`
  `format == "casa"`); cli.md's own intro says so. `apply.targets` doc agrees ("every complex term" only for the empty default).
- Fix: `"CONFIG MS: apply the calibration solutions (CASA tables or complex), writing CORRECTED_DATA"`, then
  `python docs/gen_cli.py`.
- Small, unambiguous. E5 (code string).

### DOC-07 SF: apply.targets entry keys are documented nowhere a user reads
- Source: `python/rang/core_config.py:577-582` (`TARGET_KEYS`: `field`, `tables` required; `gainfield`, `interp`),
  `defaults_yaml()` at `:1770` prints only TERM_KEYS. cli.md shows `targets: []  # what is applied to which fields`.
- Wrong: README:87 says `config defaults` "lists every configuration key"; the four target keys are not listed.
- Fix: in `defaults_yaml()` add a block after the term block:
  `# An apply target (apply.targets):` then `#   field: null  # required: fields corrected`, `#   tables: null  # required: terms applied, by name, in order`, `#   gainfield: []  # ...`, `#   interp: []  # ...`
  (emit from TARGET_KEYS as the term block does); regenerate cli.md.
- Small, unambiguous. E5.

### DOC-08 SF: default `run.stages` leaves out apply and selfcal
- Source: `python/rang/core_config.py:481-486` (default `["flag", "calibrate", "image"]`); `research/w2-commands.md:130`.
- Wrong/against the finish line: finish-plan section 1 item 1 is "`rang-core run config.yaml my.ms` flags, calibrates,
  applies, images and self-calibrates". With the default and `image.column: auto` ("CORRECTED_DATA once this run's
  apply has finished, else DATA"), `run` images uncalibrated DATA. The docs are accurate about the default, but a user
  following the finish-line promise gets an uncalibrated image.
- Fix: either default to `[flag, calibrate, apply, image, selfcal]` (a code decision, stage-hash note) or state in
  cli.md intro / tutorial that `run.stages` must list apply (and selfcal). E4's tutorial config must set it explicitly.
- Small but needs a decision. E5 decision; E4 for the tutorial.

### DOC-09 SF: CLI reference lacks `formats`, `config check` and `gemclean`
- Source: `docs/gen_cli.py:104` loops `USER_COMMANDS` only, adds `config -h` and `research`, `check`; `formats`
  (in `TOP_LEVEL`, `core_cli.py:1012`) has no section; `config check -h` (`--stage`, `--all`, the optional MS) has none;
  `gemclean` (a shipped console script, 119 lines of help) has none. `grep -n formats docs/cli.md` -> only the overview line 69.
- Fix: in `page()` add `_block("`config check`", ..., _help("config","check"))`, `_block("`formats`", ..., _help("formats"))`
  plus `formats check -h` / `formats convert -h`, and a `gemclean` section from `python -m rang.gemclean -help`
  (needs DOC-10 or reading stderr). Regenerate.
- Small. E4 (command reference) if E4 owns the reference; else E5.

### DOC-10 SF: `gemclean -h`, `-help`, `--help` exit 2 and print to stderr
- Source: `core/src/gemclean/cli.rs:362` (`"-h" | "-help" | "--help" => return Err(USAGE.into())`).
- Evidence: `python -m rang.gemclean -help 2>/dev/null` prints nothing; exit 2 for all three; text starts
  `gemclean: usage:`; `gemclean -help | less` shows nothing, and a script checking the exit code sees an error.
- Fix: return a help variant that prints USAGE to stdout and exits 0 (`-version` already does).
- Small, unambiguous. E5 (code).

### DOC-11 SF: no user example configuration and no strategy file shipped
- Evidence: no `rang-config` YAML under `examples/` or `recipes/` (`grep -l rang-config` over all YAML outside history:
  only research/results/e1-chain-scripts/e1_config.yaml and tests/data/w2/*). `flag.strategy` is required for flag
  (`config defaults` header) but `python/rang/data/` ships only the static masks, no Tricolour strategy YAML; the docs
  only say "such as CARACal's mk_rfi_flagging_calibrator_fields_firstpass.yaml".
- Fix: E4's tutorial ships `examples/config-meerkat-lband.yaml` (validated by a test with `config check --stage ...`)
  and says where to get CARACal's strategy (URL and commit) or ships one with its licence.
- Not small. E4.

### DOC-12 SF: concepts/ingest says creating tables needs python-casacore
- File: `docs/concepts/ingest.md:16-17`.
- Wrong: `rang.core_ms_write.create_table` (`python/rang/core_ms_write.py:675`, extension `ms_create_table`) creates
  tables; flag versions use it (`formats/flagversions.py:97`); python-casacore is not a dependency.
- Fix: "`rang.core_ms_write.create_table` creates tables (research/e6-table-writer-final.md lists the refused managers)."
- Small. E4 or E5.

### DOC-13 SF: installation page pins the version in a comment
- File: `docs/installation.md:113` (`rang-core --version  # rang-core 0.1.0`).
- Wrong at release: `tests/test_w4_5_release.py:82-86` checks only docs/conf.py, so this goes stale at 0.2.0 silently.
- Fix: `# rang-core <version>` or drop the comment; also `:85` "since 0.1.0" is fine.
- Small, unambiguous. E5 release step.

### DOC-14 L: tutorials page says "once released"
- File: `docs/tutorials/index.md:63` ("rang-core[notebook,imaging] once released").
- Wrong: 0.1.0 is released (CHANGELOG:389, installation.md:10 "is on PyPI"). Not verified against PyPI (no network query made).
- Fix: `pip install 'rang-core[notebook,imaging]'   # or -e '.[notebook,imaging]' from a checkout`.
- Small. E4.

### DOC-15 L: no tutorial or page for the user chain; API index omits the chain modules
- Evidence: `docs/tutorials/index.md` lists notebooks 1-7, none runs `rang-core flag ... run` on an MS (finish line item 5:
  "A tutorial goes from a Measurement Set to an image"); `docs/api/index.md:7-18` lists no `core_config`, `core_pipeline`,
  `cal_*`, `calmodels`, `gemclean`, `formats` (autosummary still generates them). No user page lists what is refused
  (research/w4-unsupported.md only).
- Fix: E4's tutorial; add rows for those modules; link `rang-core config check --all` and w4-unsupported.md.
- Not small. E4.

### DOC-16 L: research/gemclean.md predates G7 and G8
- File: `research/gemclean.md:3-8` (status 2026-11-02, code `core/src/bin/gemclean.rs`), `:247` ("Optional, not default:
  `-single` ... 1e-4"), `:302` ("gemclean default (`f64`, ε 1e-6)").
- Wrong now: G7 made 1e-4 single the default; G8 moved the CLI to `rang_core::gemclean::cli`. README links this report as "GeMClean".
- Fix: a dated line under the status: "Since G7 the default is 1e-4 in single precision (g7-defaults.md); since G8 the
  command line is `rang_core::gemclean::cli` and ships in the wheel (g8-wheel.md). Tables below are as measured then."
- Small. E5.

### DOC-17 L: README from-source and recipe gaps
- `README.md:60-61` and `docs/installation.md:99-101` use `.venv/bin/python` only; native Windows is a supported
  platform (Scripts\python.exe). Fix: add the Windows form or `uv venv` + `uv pip`.
- `recipes/rang-chain.yaml` runs flag, calibrate, apply, image, no selfcal; `recipes/rang-cabs.yaml` has no selfcal cab
  while cli.md's intro describes it accurately. Fix: add a `rang-selfcal` cab and step, or say so in the recipe header.
- `docs/installation.md:63`: the `carta` extra row says "with CARTA's wrapper from its pinned commit" but gives no command;
  the command is only in a `pyproject.toml` comment (`pip install 'carta @ git+https://github.com/CARTAvis/carta-python@989af8e...'`).
- `pyproject.toml` comment on `meerkat`: python-lzf and rdbtools are sdist-only and cityhash has no cp314 wheel, so the extra
  needs a C compiler (on 3.14 at least); installation.md:61 does not say so (not re-tested here).
- Small each. E4 (installation/landing) except the cab (E5).

### DOC-18 L: `image.uvrange` documented as "not read" but setting it is an error
- Source: `core_config.py` image section; `docs/cli.md` `uvrange: ""  # not read: use minuv_l, ...`.
- Evidence: a config with `image: {uvrange: ">150"}` -> `config check --stage image` exit 2, "image.uvrange: a CASA-style
  range is not read for imaging: use minuv_l, maxuv_l (wavelengths), minuvw_m and maxuvw_m (metres)". The error is clear;
  the defaults comment reads as if the key were silently ignored.
- Fix: comment "refused: use minuv_l, maxuv_l, minuvw_m and maxuvw_m"; regenerate cli.md.
- Small, unambiguous. E5.

## Counts

RB 5 (DOC-01..05), SF 8 (DOC-06..13), L 5 (DOC-14..18).
E4-owned or shared: DOC-01, 02, 04, 05, 09, 11, 14, 15, 17 (and 03, 12 if E4 owns concepts).
Open for whoever merges E2: `calibrate.average_time` / `selfcal.average_time` (finish-plan item 33) are not in the schema
on main; cli.md regenerates them automatically, but the 0.2.0 limits text (DOC-05) must mention them.
