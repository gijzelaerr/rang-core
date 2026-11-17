# E5 final: recheck of the pre-review findings on current code

Read-only recheck, 2026-11-12. Code: worktree `.claude/worktrees/e5-final-early-b94bc5` at `b6e8b52` (= main `2899c23` plus three
SPDX lines). Commands run with the main checkout's venv (`~\Github\rang\.venv`, rang 0.1.0, same code). No file in
either checkout edited; no build. E3 results not opened. Line numbers are at `b6e8b52`.

Commands run: `rang-core -h`, `rang-core --no-receipt --version` (exit 0), `python -m rang.core_cli config defaults` (154 lines,
saved in scratchpad `defaults.txt`), `gemclean -h` (stderr, exit 2), `gh api repos/gijzelaerr/rang-core/environments/pypi`,
`pytest tests/test_spdx_headers.py tests/test_w4_5_release.py` (18 passed, 1 skipped).

"Protected" = a fix would touch core_config.py, core_pipeline.py, cal_*.py, core_ms*.py, core_flag*.py, core_writeback.py or Rust
(code paths of the running acceptance test: list only, do not fix now).

## 1. Findings

| ID | State today | Evidence | Protected? |
| --- | --- | --- | --- |
| E5-01 (spot) | fixed | `core_pipeline.py:2617` counts `core_writeback.flag_writes()` before the stage; `:2638-2649` pops later stages' `flag_version` only when `restored_before` or FLAG writes changed | - |
| E5-02 | **open (Rust part)**; Python part fixed | Python: `core_writeback.py:391-394` raises "DATA is never written"; `core_config.py:993`, `:1105` refuse the keys. Rust: `core/src/gemclean/cli.rs:485` `"-model-column" => a.model_column = value(&mut i)?` with no check; `predict.rs:444-463` `write_model_column` opens a `TableWriter` and writes any existing column. Since gemclean writes the model column after imaging by default (CHANGELOG.md:205), `gemclean -model-column DATA ms` overwrites DATA with no explicit predict. No `"DATA"` refusal anywhere in `core/src/gemclean/` | yes (Rust, rebuild) |
| E5-03 (spot) | fixed | `core_pipeline.py:855-883` `restore_before` saves `rang_rerun_<UTC>` via `backup_flags` and records `saved_before_restore` before `restore_flags` | - |
| E5-06 | fixed | README.md:25-27 "The wheel installs it as the command `gemclean`"; docs/index.md:37-40 same | no |
| E5-07 | fixed | README.md:93 one row: flag, calibrate (K, G, B, A, F, polarisation, `complex`), apply, image, selfcal, run; docs/index.md:41-45 | no |
| E5-08 | **partly** | Fixed: imaging.md:52 "GeMClean is rang's deconvolver". Still false: `docs/concepts/imaging.md:33-35` "It is not yet bound in the extension: on first use it builds a standalone library with `cargo`", and `docs/concepts/index.md:4-5` "in the extension `rang._core` except the exact wgridder"; the code says otherwise (`python/rang/core_wgridder.py:26` "Since DF2b ... the extension `rang._core` binds the" gridder) | no |
| E5-09 | **open** | `grep -i "known limit"` over README.md, CHANGELOG.md, docs/: no hit. CHANGELOG has `## Unreleased` (:10) and `## 0.1.0` (:452) only. See section 2 for each limit | no |
| E5-10 | **open** | CHANGELOG.md is 518 lines, Unreleased still the per-task log (:10-451). Stale statements still in it: :289 K, G, B... "are not chunked yet"; :388 "Polarised `manual` models are refused until C7a"; :134 "`image.gemclean: auto` finds `core/target/...`" against :91 "the search of ... `core/target` is gone"; :237-238 "`extendflags: true` (not ported, no owner) are configuration errors" against :188 (E0 runs it); :306 "`data.weights: uniform` for imaging is still refused". No Breaking/New/Changed/Fixed summary | no |
| E5-12 | **open** | `core/src/grid.rs:1-12`, `core/src/wgridder.rs:1-14`: name "André Offringa and contributors" / "Martin Reinecke (Max-Planck-Society...)" but no upstream `Copyright (C)` line; `core/src/weights.rs:4` carries only "Copyright (C) 2026 Gijs Molenaar". The claims are unchanged: README.md:147 "Ported code keeps its upstream notices"; docs/licence.md:10 "ported code keeps its upstream copyright notices" | yes if fixed in the Rust headers (comments only); no if the sentences are softened |
| E5-13 (spot) | fixed | `core_pipeline.py:749-762` msvcrt `LK_NBLCK` on the first byte, `LK_UNLCK` on release | - |
| E5-14 (spot) | fixed | `core_config.py:729-742` `_check` replaces a refused value with the key's default once the error is recorded | - |
| E5-16 | **partly** | Fixed: `wheels.yml:361` `publish: needs: [wheel, sdist, test, release]`. Open: `test_w4_5_release.py` is not run in the release job (`wheels.yml:280-357` checks tag = file names = pyproject version and the CHANGELOG section only; CITATION.cff and the three Cargo.toml are not checked on the tag). New since: `tests.yml:120-122` runs the full pytest (so `test_w4_5_release`) on `pull_request` and dispatch only, not on pushes to main or tags | no (workflow) |
| E5-17 | **open (residual)** | `docs/installation.md:113` `# rang-core 0.1.0` hard-coded; `tests/test_w4_5_release.py` has no reference to installation.md; installation.md:123-126 claims "this site follow[s]" the pyproject version | no |
| E5-19 | **open** (and receipt version now 5) | `core_pipeline.py:137` `UNSUPPORTED = "(unsupported data, task W4: research/w4-unsupported.md)"`; `config defaults` output names tasks: line 35 "(task E2)", 42, 43, 117 "(task E2)", 57 "C6's provisional owner decision 1", 83 "task G7", 109 "task G6", 112 "owner decision 1 of C1", 154 "(C2e) ... (C6w) ... (C5)"; `docs/cli.md:10` "naming the task that adds it"; `apply` help `core_cli.py:1010` and `docs/cli.md:72,135` "apply the complex solutions"; receipt docstrings `core_cli.py:28`, `:573`, `core_receipts.py:13` say version 3, code `core_cli.py:85` `RECEIPT_VERSION = 5`; `core_config.py:43` `TASKS`, `core_pipeline.py:2491` `_refused_stage` still present | yes (core_config.py, core_pipeline.py; also core_cli.py, docs/cli.md) |
| E5-21 | **open** | `core_config.py:1851-1867` `stage_hash` = sha256 of the config sections' JSON; strategy, lsm and mask files by path only. (Strategy text is hashed into the stage *summary*, `core_pipeline.py:1112`, `:1508`, but not into the skip decision `:2558`) | yes (core_config.py; every stage hash changes once) |
| E5-22 | **open** | `core_writeback.py:246-258` refuses on any prior `open`/`failed` journal regardless of what was written; `:292-307` journal written (`state: open`) before `open_table`; `:405` `_mark("written")` only after `putcol` and flush; `core_pipeline.py:864-871` refusal still advises `restore_flags(ms, journal['flag_backup'])`; `InterruptedWriteBack` not caught in `core_cli.py` (grep: no hit) | yes (core_writeback.py, core_pipeline.py) |
| E5-23 | **open** | `core_writeback.py:246-247` carries `initialising` only for `open`/`failed`; `restore_flags` `:593` sets `restored`, so the next `begin` starts with `dirty = []` and `ensure_column` `:532-533` returns False without re-initialising | yes (core_writeback.py) |
| E5-24 | **open** | no `os.access`/`W_OK` in core_writeback.py, core_pipeline.py, core_cli.py, core_ms_write.py; `begin` saves the backup (`:270-276`) and writes the journal (`:302`) before `open_table` (`:303`) | yes (core_writeback.py) |
| E5-25 | **open** | `rang-core -h`: commands flag, calibrate, apply, image, selfcal, run, config, research, check, formats; no restore verb. `docs/cli.md` has no restore section (only gemclean's `-no-restore`, :925); `restore_flags` and `flagmanager` appear in no docs page | no (core_cli.py + docs; wraps `restore_flags` unchanged) |
| E5-26 | **open** | no `winerror` / "another program" handling in python/rang (grep: no hit) | yes (core_ms_write.py) |
| E5-27 | **open** | `TARGET_KEYS` `core_config.py:614-619` (field, tables, gainfield, interp); `config defaults` line 65 shows only `targets: []  # what is applied to which fields ...`; the entry keys appear nowhere in docs/ (the `gainfield`/`interp` at docs/cli.md:373-374 are the calibrate term's pre-apply keys) | yes if done in `config defaults` (core_config.py); no for a docs paragraph |
| E5-29 | **partly** | Fixed: `docs/cli.md:861` `## gemclean`. Open: no `## formats` section (only the overview line :81), `config check` only as a line of `config -h` (:216-229), no `config check -h` | no (docs/gen_cli.py) |
| E5-30 | **open** | `core/src/gemclean/cli.rs:362` `"-h" \| "-help" \| "--help" => return Err(USAGE.into())`; ran `gemclean -h`: usage on stderr, exit 2 | yes (Rust) |
| E5-31 | **partly** | `python/rang/data/` holds two static masks, TRICOLOUR-LICENSE, observatories JSON, meerkat.itrf.txt: no strategy YAML, no example config; no `config example` command (`rang-core config -h`: defaults, check). The tutorial notebook writes its own `strategy.yaml` (notebooks/00-ms-to-image.ipynb), so the tutorial path works; a user's own MS has no shipped strategy | no (package data, core_cli.py) |
| E5-32 | **open** | `docs/concepts/ingest.md:18-19` "Creating new tables still needs python-casacore." | no |
| E5-33 (residual) | open (external) | `docs/licence.md:31` "follow-up: ask the CARACal authors to confirm GPL-2.0-or-later" | no |
| E5-34 (residual) | open (stated) | `python/rang/data/README.md:26` "casacore-data's own licence was not checked" | no |
| E5-35 | **open** | README.md:23-24 "w-stacking gridder (CPU and GPU)", README.md:43-44 "carries every kernel"; docs/index.md:35 "(CPU and GPU)". Wheels build without `gpu`: `core/py/Cargo.toml:19-21` feature `gpu` not default; `wheels.yml:112` `args: --release --locked --out dist` (no `--features`). No sentence that GPU needs a source build | no |
| E5-36 | **open (owner)** | `gh api repos/gijzelaerr/rang-core/environments/pypi`: `"protection_rules":[]`, `"deployment_branch_policy":null`, `"can_admins_bypass":true` | no (GitHub settings) |
| E5-39 (residual) | open (later) | empty OBSERVATION gives no warning (as recorded; not rechecked by run) | yes (core_pipeline.py) |
| E5-41 (residual) | open = E5-21 | mask files hashed by path in `stage_hash` | yes (core_config.py) |
| E5-42 WB-14 | **open** | `core_writeback.py:585-596` `restore_flags` writes the journal only after `flagversions.restore` has finished, and only when `open`/`failed`; no `restoring` state; the four journal checks `core_pipeline.py:864`, `:892`, `:912`, `:931` test `("open", "failed")` only | yes (core_writeback.py, core_pipeline.py) |
| E5-44 | **open (later)** | `core/src/ms_write.rs:57` lock `#[cfg(target_os = "linux")]`, `:105` no-op otherwise; limit stated in docs/concepts/ingest.md:14-16 | yes (Rust) |
| E5-45 (residual) | fixed | `tests/test_spdx_headers.py:17` `PENDING: set[str] = set()`; ms.rs, ffi_ms.rs, core_ms.py line 1 SPDX; test passes. (`.lua` strategies and `core/py/src` outside the policy, as recorded) | - |
| E5-46 | **open (later)** | `pyproject.toml:58` `meerkat = ["katdal==0.23", "katsdptelstate[rdb]==1.0.0"]`; installation.md:61 and README.md:52 say nothing of a C compiler or Python 3.14 | no |
| E5-47 | **open** (owner at E6) | `pyproject.toml:16` `Development Status :: 3 - Alpha`; README.md has 22 `blob/main`/`tree/main` links | no |
| E5-48 | **open (later)** | `pyproject.toml:11` `license-files = ["LICENSE", "THIRD-PARTY-NOTICES.txt"]` (no Rust dependency licence texts); no flagger weights bundled | no |
| E5-49 DOC-17 | **open** | `docs/installation.md:96-101` From source gives only the POSIX form (`.venv/bin/python`), no Windows form; recipe selfcal, carta command, meerkat compiler note not added | no |
| E5-50 | **open (internal)** | no string-array (`POLARIZATION_TYPE`) support found in core/src/ms.rs, core/src/tiled.rs, core_ms.py, cal_pol.py | yes (Rust/core_ms) |
| E5-51 | **open (later)** | `core_cli.py:700-718`: a path that exists only after the command is recorded with `content=True` (full tree sha256, `:601-625`) | no (core_cli.py) |
| E5-52 | **open: not stated** | grep README, CHANGELOG, docs for "across platforms", "byte-identical across", "Windows and Linux", "differ between": no hit | no (a sentence) |

Counts over the 41 rows: fixed 7 (E5-01, 03, 06, 07, 13, 14, 45 residual), partly 4 (E5-08, 16, 29, 31), open 30 (incl. E5-02's
Rust half, owner, external and later items), changed 0 (E5-19 grew: the receipt docstrings say 3, the code writes 5).

## 2. Section 3: is there a sentence a user reads?

Searched README.md, CHANGELOG.md and docs/ (excluding docs/research/, the research index). "CHANGELOG" means only inside the
per-task Unreleased log, which E5-10 rewrites; nothing is in a Known-limits list.

| Item | Statement needed | Where found today |
| --- | --- | --- |
| 1, 2 | finish line with polarisation; multiscale in | partly: README.md:93 (polarisation terms run); CHANGELOG.md:151 (`-multiscale`). No scope sentence |
| 3, 30 | coarse gridding default, revertible; one-quadrant beam fit | CHANGELOG.md:94-99 (1e-4 single precision; `-wgridder-accuracy 1e-6` reverts); CHANGELOG.md:101-104 (quadrant) |
| 4, 31 | confirm `gemclean` name; x86-64 baseline in installation docs; `auto` runs installed extension only | name: owner confirm, no statement. Baseline: docs/installation.md:38 "built for the platform's baseline CPU" (does not say x86-64, nor that source builds use x86-64-v3, see NEW-1). `auto`: CHANGELOG.md:89-92 |
| 5 | selfcal phase then amplitude; Tricolour replaces tfcrop; K FFT then Gauss-Newton | CHANGELOG.md:167, docs/cli.md:346 (`config defaults`); CHANGELOG.md:256-257 "(CARACal runs tfcrop there)"; CHANGELOG.md:363 |
| 6 | "not yet tested on native MeerKAT data" | **absent** |
| 7 | C4a 1-2 ulp; CASA's Df substitution | ulp: **absent**; substitution: CHANGELOG.md:432 "substitutes bad leakages" (0.1.0 section) |
| 8, 16 | parallactic-angle frame CASA's, provisional | docs/cli.md:291 (`frame: casa ... provisional`); CHANGELOG.md:239, :243 |
| 9 | solution TIME reported not gated; combine='scan' estimator; SIGMA weights with pre-applied tables | TIME: **absent**; combine: **absent** (only CHANGELOG.md:359 lists `combine='scan'` as a setting); SIGMA: CHANGELOG.md:365 |
| 10 | general-Jones flag rule; gains never transferred to a target; models on primary fields | partly: docs/cli.md:259 (models on the primary fields); flag rule and no-transfer **absent** as statements |
| 11 | a K table applied alone lacks the offsets; delay error low by 1.5-2 | offsets: CHANGELOG.md:353-355 ("The `K Jones` table holds the delays only; ... G absorbs them"); delay error: **absent** |
| 12 | uniform weights as gemclean option; WEIGHT fallback; autocorrelations out of the solve | CHANGELOG.md:215-219; docs/cli.md:246, :902; CHANGELOG.md:303 |
| 15 | refused with no owner: solnorm, calmode a, gainfield on pre-applied, complex mixed with K..F | CHANGELOG.md:262 (solnorm, calmode a); the rest only as refusal messages (`config check`), no list |
| 17, 22 | 8 GiB default memory limit; slow channel chunks | limit: docs/cli.md (defaults, `memory_limit_gb: 8.0`), CHANGELOG.md:29; slowness: **absent** |
| 19 | FEED not rewritten; CASA with parang=True applies a different P | CHANGELOG.md:235-236 "FEED is not rewritten"; docs/cli.md:292; the CASA consequence **absent** |
| 20, 24, 26 | gemclean's refused options | CHANGELOG.md:148 (XY/YX/circular, `-link-polarizations`), :329-330 (log-pol, squared joining); Q/U/V model writing and selfcal refusals not found |
| 21 | refant by name as CARACal; stop when no antenna qualifies | CHANGELOG.md:188-193. Note docs/cli.md:269 / `config defaults` line 35: `refant: null` = auto "or antenna 0 when no antenna qualifies" (the null default falls back; explicit `auto` stops); consistent but easy to misread |
| 23 | gemclean writes the model column by default; `image.write_model` false | CHANGELOG.md:205, :211; docs/cli.md:343 |
| 25, 29 | selfcal model-absorption limit | **absent** as a statement; only CHANGELOG.md:116 "do not lift C5's model-absorption limit" in passing |
| 26, 28 | which G9 record; images not byte-identical across platforms; Högbom mask finishing early; WSCNVIS | G9 record: owner confirm, none; platforms: **absent** (E5-52); Högbom: **absent**; WSCNVIS: **absent** |
| 27 | E1's outcome | CHANGELOG.md:118-122 |
| 32 | no learned flagger in `rang-core flag` | CHANGELOG.md:75-76 "not wired into `rang-core flag`"; README.md:111 |
| 33 | refant leakage limit; 530 flag cells; `average_time` off by default, differs from CubiCal | leakage limit: **absent**; 530: **absent**; average_time: CHANGELOG.md:24-34 (now on main; default false, "Not CubiCal's estimator") |
| E5-09 extras | 40-60x thermal floor; L band only; no direction-dependent calibration; no novelty claim | floor **absent**; L band only **absent**; DD calibration **absent**; no novelty: README.md:9-11, docs/index.md:16-18 |

Absent today: items 6, 7 (ulp), 9 (TIME, combine), 10 (flag rule, no transfer), 11 (delay error), 17/22 (slowness), 19 (CASA
consequence), 25/29, 26/28 (platforms, Högbom, WSCNVIS), 33 (leakage, 530), thermal floor, L band only, no DD calibration. Owner
confirmations still unanswered as far as the user-facing text shows: 4 (name), 7, 8/16, 9, 10, 11 (delay error), 19, 26/28 (G9 record).

## 3. New

- **NEW-1 (should-fix, docs only).** A build from a git checkout targets x86-64-v3: `.cargo/config.toml:6-7`
  `rustflags = ["-C", "target-cpu=x86-64-v3"]` for every x86_64 host. The sdist excludes it (`pyproject.toml` comment and
  `{ path = ".cargo/**/*" }`), but README.md:56-62 and docs/installation.md:88-101 ("From source") say nothing; an extension built
  that way on a pre-AVX2 x86-64 CPU dies with an illegal instruction. One sentence (and `RUSTFLAGS="-C target-cpu=x86-64"` for
  older CPUs) closes it. Not protected.
- **NEW-2 (later).** Upstream licence of WSClean recorded three ways: docs/licence.md:16 "GPL-3.0", core/src/grid.rs:8 "GPL-3.0",
  core/src/weights.rs:7 "GPL-3.0-or-later". Pick one (WSClean's own headers decide). Docs part not protected; Rust comment protected.
- **NEW-3 (later).** `rang-core -h` does not show `--version` (usage line: `[--receipt PATH | --no-receipt] [--no-pin-threads]`);
  `rang-core --no-receipt --version` works (exit 0). core_cli.py, not protected.
- E5-02 severity note (not new, sharper): gemclean updates the model column after imaging by default, so `-model-column DATA`
  on an ordinary imaging call overwrites DATA; only FLAG has a backup.

## 4. For the coordinator

Still release-blocking (rule of section 2: wrong result/data loss, a false statement, or legally wrong):
1. **E5-02** gemclean `-model-column DATA` (Rust; protected; needs a rebuild).
2. **E5-08** imaging.md:33-35 and concepts/index.md:4-5 say the wgridder is not in the extension (docs only).
3. **E5-09** no Known-limits list anywhere (docs/CHANGELOG; after E2/E3).
4. **E5-10** CHANGELOG Unreleased still the per-task log with contradicted statements (editorial, E6).
5. **E5-12** "ported code keeps its upstream copyright notices" is false for grid.rs, weights.rs, wgridder.rs (soften two sentences,
   or add the upstream lines to Rust comments).
Should-fix still open and not protected (can be fixed now): E5-16 residual, E5-17, E5-25, E5-29, E5-31, E5-32, E5-35, NEW-1;
owner: E5-36 (environment still unprotected). Should-fix open and protected (list only): E5-19, E5-21, E5-22, E5-23, E5-24, E5-26,
E5-27 (or docs-only), E5-30, E5-42 WB-14.
