# E5 pre-review: the v0.2.0 release review, started early

Status, 2026-11-11: **review done on current main; 11 findings fixed in 12 commits on branch `e5-prereview`; the rest proposed or for the owner.**
Finish-plan task E5 ([finish-plan.md](finish-plan.md) section 3, E) reviews the release as [w4-review.md](w4-review.md) did for 0.1.0.
It was started before E2, E3 and E4 finished, so that findings can be fixed while E2 runs. It is not the final E5: that one reruns on the
release candidate, after E2, E3 and E4, and needs no release-blocking finding left.

Base: local `main` at `3eab67c`, which is ahead of `origin/main` (`c2fe7cc`) by research-only commits; the code is the same.
CI (wheels run 43004680641 at `c2fe7cc`) is green on all five wheels, the sdist and ten test cells.

**Counts:** 52 findings, numbered once (E5-01 to E5-52).
- **Release-blocking:** 12. Fixed here: 5, E5-02 in part (gemclean's `-model-column DATA` open). Open: 7 (E4: 3; editorial after E2/E3: 2; owner: 1; proposed: 1).
- **Should-fix:** 26. Fixed here: 6. Open: 20, of which 4 need the owner.
- **Later:** 14 groups.

One rule for the classes. **Release-blocking:** a user following the docs gets a wrong result or loses data, the release states something false, or it is legally wrong.
**Should-fix:** wrong but recoverable, or a clear message missing. **Later:** everything else.
Pending work is not counted as a finding: the 0.1.0 version, the Alpha classifier, E2-E4 not finished. Those are in the release checklist (section 5).

## 1. Method

Four read-only review agents (CLI and configuration; write-back safety; packaging and licence; docs against code), each told to verify
every claim by running it or quoting the code. Their notes, with evidence and file:line for every item including the later ones, are
archived in [results/e5-prereview-notes/](results/e5-prereview-notes/) (`e5-cli.md`, `e5-writeback.md`, `e5-packaging.md`,
`e5-docs.md`, about 1,290 lines; local paths replaced by `<scratch>`, `<worktree>` and `~`). Each item fixed here was reproduced first.
Each fix's test fails without the fix and passes with it, except two: `bbb2a9d`'s test fails at `25e1809` (it guards against that
commit's over-broad rule) and passes on main; `045f629`'s is a guard on files that agree on main.

Two checks were run by hand:
- **The installed wheel, outside any checkout.** CI's `rang_core-0.1.0-cp310-abi3-win_amd64.whl` (run 43004680641), installed in a fresh
  uv venv (Python 3.14.10) in a scratch folder. `rang-core --version` and `gemclean -version` print 0.1.0. `rang-core run` (flag, calibrate,
  image with the wheel's gemclean) on W2's 240-row MS exits 0 in 1.2 s. The receipt records `commit: null`, `checkout: null`, the
  distribution version, the extension's sha256 and every `RANG_*` variable. W4R-01 and W4R-02 stay fixed.
- **A hard kill mid-write, on Windows.** The suite's kill test is POSIX-only. With the wheel, `rang-core flag` was terminated
  (TerminateProcess, exit 15) after its second FLAG chunk. The rerun says `running (was running)` and restores the flags saved before the
  stage. FLAG and `rang_original` then equal an uninterrupted run's.

Not run: the full `tools/check-all.sh`, which waits for the heavy lock (E2 holds it). Targeted suites were run for each fix (section 4).
No wheel was built locally: release builds are heavy.

## 2. Findings

`Fixed` names the commit on `e5-prereview`. Agent IDs in brackets.

### 2.1 Release-blocking (12)

| ID | Finding | Where | Fix | State |
| --- | --- | --- | --- | --- |
| E5-01 | `rang-core run b.yaml ms --force flag` (the hint the refusal prints) reruns flag, then the stale apply restores the flags saved before its *earlier* attempt, the old flag output. 5,232 flagged cells against 3,387 from a fresh run with b, every stage `done`, exit 0. The new flags are kept nowhere [CLI-01] | `core_pipeline.py` `execute` | Drop later stages' saved flag versions when a stage changes FLAG. The first form also dropped them after a complex calibrate, which writes no flags [WB-02], so the rule is: when the stage restored earlier flags or wrote FLAG (a process-wide count of FLAG writes in `WriteBack._put`) | Fixed `25e1809`, `bbb2a9d` |
| E5-02 | DATA can be overwritten: `apply.column: DATA`, `selfcal.model_column: DATA` and a copy into `selfcal.input_column: DATA` were accepted, and `WriteBack.write("DATA")` succeeded. Only FLAG is backed up; `w1-writeback.md` says DATA is never written [WB-01] | `core_writeback.py` `_put`; `core_config.py` `_selfcal_errors`, `resolve`; `core_pipeline.py` `_selfcal_input` | `WriteBack` refuses DATA; the two keys are configuration errors; `input_column: DATA` stays valid when nothing is copied into it (C5's checks use it, read-only) and is refused when this run's apply would be copied in | Fixed `ef4f9bf` (Python). Open: `gemclean -model-column DATA` (`core/src/gemclean/cli.rs` ~484): refuse it there too; needs a rebuild |
| E5-03 | A rerun's restore writes the stage's earlier flags over FLAG without saving what is there; flags set by hand (CASA `flagdata`) since the last attempt are lost, no version holds them [WB-06] | `core_pipeline.py` `restore_before` | Save the replaced flags first as `rang_rerun_<UTC>` (recorded as `saved_before_restore`). One FLAG-size copy per rerun, the size of the backup each stage already takes. Comparing first would always differ, since FLAG holds the stage's own output | Fixed `62d25c9` |
| E5-04 | `core_writeback` and `docs/concepts/ingest.md` promise casacore's table lock; it holds on Linux only (`core/src/ms_write.rs` ~104-113). A second writer went through on Windows [WB-03] | as named | Correct both sentences. A real lock off Linux is later (E5-44) | Fixed `fc27092` |
| E5-05 | The wheels carry no MIT or BSD notice except Tricolour's masks' licence. QuartiCal's MIT notice (four translated files) and codex-africanus's BSD-3 notice live only in `.rs` comments, which the wheel does not contain; both licences require the notice with binary copies [PK-06] | `pyproject.toml` `license-files` | `THIRD-PARTY-NOTICES.txt`, the notices copied from the source headers, in `license-files`. `maturin sdist` lists it as `License-File`; not checked in a built wheel | Fixed `7fe286b` |
| E5-06 | README and `docs/index.md` say gemclean "is not in the wheels" and give a cargo command. It is a console script since G8, and the README is the PyPI page [DOC-01, PK-01, CLI-02] | `README.md` 25-27; `docs/index.md` 38-40 | Say it ships as `gemclean`; keep the cargo line for a standalone binary | Open: E4 (landing pages) |
| E5-07 | README's command table: calibrate "`complex` only so far", no `apply` or `selfcal`. K, G, B, A, F and the polarisation terms run [DOC-02, PK-02] | `README.md` 89-95; `docs/index.md` 41 | One row with all six commands and what they run | Open: E4 |
| E5-08 | `docs/concepts/imaging.md`: the wgridder "is not yet bound in the extension" and builds with cargo; "rang has no production deconvolver". Both false since DF2 and G8; `concepts/index.md` repeats the first [DOC-03, DOC-04] | `imaging.md` 33-35, 52-54 | Rewrite both paragraphs (gridder in the extension; GeMClean is the imager) | Open: E4 |
| E5-09 | No known-limits statement anywhere a user reads (README, docs, CHANGELOG): native data untested (item 6), the selfcal model-absorption limit (25, 29), the refant leakage limit, the 530 flag cells and `average_time` (33), FEED not rewritten (19), the 40-60× thermal floor, L band only, no direction-dependent calibration, no novelty claim [DOC-05, PK-04] | `CHANGELOG.md` Unreleased; `README.md` 11-19 | A `### Known limits` list in the 0.2.0 section and the README status block, with report links; filled after E2 and E3. Section 3 is the list | Open: after E2/E3 |
| E5-10 | `CHANGELOG.md` Unreleased (294 commits) becomes the GitHub release notes verbatim, and states behaviour later entries undo, for example: `refant: auto` and `extendflags` "refused" (E0 ported them), K, G, B, A, F "not chunked" (W3b chunked them), `image.gemclean: auto` searching `core/target` (G8 removed it), polarised models "refused until C7a". Breaking changes (stage-hash `--force` steps, gridding defaults) are scattered [PK-03, PK-13] | `CHANGELOG.md` 10-388; `wheels.yml` 259-279 | Rewrite into a 0.2.0 summary: Breaking, New, Changed, Fixed, Known limits; the per-task log moves to a link. Then check every remaining "refused" against `rang-core config check` | Open: editorial, at E6 |
| E5-11 | `data/*.itrf.txt` come from simms, which is GPL-2.0-only (its `pyproject.toml` at `e715505`); `meerkat.itrf.txt` is compiled in (`core/src/gemclean/sim.rs:41`) and all four ship in the sdist under GPL-3.0-or-later. `docs/licence.md` lists simms as "GPL-2.0" and itself says GPL-2.0-only cannot be combined with GPL-3 [PK-05] | as named | Owner decision: (a) treat coordinates as uncopyrightable facts and say so in `licence.md`; (b) gate `sim` behind a feature and keep `data/` out of the sdist; (c) take positions from a permissive source (katpoint, an observation's ANTENNA table). In every case drop the three unused `.itrf` files from the sdist | **Answered 2026-11-11** ("Facts, not code"): fixed in `5a0ac94` |
| E5-12 | README says ported code keeps its upstream copyright notices; the GPL ports (`grid.rs`, `weights.rs`, `wgridder.rs`) name WSClean and ducc0 but carry no upstream copyright line [PK-07] | `README.md` 145; `docs/licence.md` 10 | Copy the upstream copyright lines from WSClean 3.6 and ducc0 0.42.0 headers verbatim with a "translated to Rust" note, or soften the sentence | Open: proposed (needs the exact upstream lines) |

### 2.2 Should-fix (26)

| ID | Finding | Where | Fix | State |
| --- | --- | --- | --- | --- |
| E5-13 | No run-directory lock on Windows (the owner's main platform since 2026-11-09): two `rang-core` commands on one MS both wrote | `core_pipeline.py` `RunDir.locked` | msvcrt's byte lock, released explicitly | Fixed `2bac745` |
| E5-14 | Malformed values (`terms:` with nothing after it, a scalar `selfcal.clean_cutoff: 3`, a list as a term name) end in a TypeError traceback, exit 1; 11 distinct crashes over every schema key [CLI-06] | `core_config.py` `_check` | A refused value is replaced by its default once the error is recorded; 0 crashes over the same sweep, which is now a test | Fixed `47e5520` |
| E5-15 | The changed-configuration refusal says "pass --force flag", which `rang-core flag` rejects (it takes a bare `--force`) [CLI-05] | `core_pipeline.py` `execute` | Name both forms | Fixed `1c8a617` |
| E5-16 | `publish` (PyPI) ran beside `release`, so a missing CHANGELOG section failed the release only after PyPI had accepted the upload, which cannot be undone [PK-10] | `wheels.yml` 285-287 | `needs: [..., release]`; asserted in `test_w4_5_release.py` | Fixed `c9ee936`. Open: run `test_w4_5_release.py` in the release job (it runs only locally) |
| E5-17 | `CITATION.cff` is outside the version test; the version regex allows a/b/rc, which the owner does not release [PK-11, PK-17] | `tests/test_w4_5_release.py` | Both checked | Fixed `045f629`. Open: `docs/installation.md` 113 hard-codes `0.1.0` (E4) |
| E5-18 | The missing-model-column refusal says MODEL_DATA from the imager "is task G6"; `image.write_model: true` exists [CLI-07, part] | `core_pipeline.py` 483 | Name the option | Fixed `686cca3` |
| E5-19 | Other user-facing messages name task IDs and research notes a wheel user does not have: every data refusal ends "(unsupported data, task W4: research/w4-unsupported.md)"; key docs in `rang-core config defaults` cite G7, C6, C2e, C6w, C5; `docs/cli.md` 10 promises refusals "naming the task"; `apply`'s help says "the complex solutions" though it applies CASA tables; receipt docstrings say version 3 (the code writes 4); dead `TASKS` and `_refused_stage` [CLI-07, DOC-06] | `core_pipeline.py` 135, 304, 474, 1902; `core_config.py` 13, 270, 353, 1795; `core_cli.py` 27, 567, 1002 | Strip the IDs, point to the docs page of unsupported data, regenerate `docs/cli.md`, update the tests matching "W4". Touches `core_config.py` and `docs/cli.md`, which E2's branches also change, so after E2 merges | Open: after E2 |
| E5-20 | Each receipt re-reads and sha256s the whole MS after every command that wrote to it, failures included: minutes to tens of minutes per command at E2's 36-180 GB [CLI-03] | `core_cli.py` 702-715 | Record the MS by its listing hash (size and mtime) and rely on the stage summaries' hashes of what was written (`flag_sha256`, gain and image hashes). Provenance against I/O, so the owner's call | **Answered 2026-11-11** ("Listing hash"): fixed in `25b0f10` |
| E5-21 | The stage hash covers strategy, sky-model and mask files by path only; after editing `strategy.yaml` in place, `rang-core flag` says "done, skipped" and FLAG keeps the old strategy [CLI-04] | `core_config.py` `stage_hash` | Hash the referenced files' contents. Every stage hash changes once (`--force`), so not during E2 | Open: after E2 |
| E5-22 | The journal turns "open" when FLAG was never written (model-only predicts, a read-only MS, a shape refusal), and the refusal then says to `restore_flags(ms, 'rang_original')`: following it took a demo MS from 9,600 flags to 915 while `state.json` still said flag, calibrate and apply were done [WB-04] | `core_writeback.py` begin and journal; `core_pipeline.py` refusal text | Mark FLAG written only at its first put; do not refuse when FLAG was never written; take the lock before the journal | Open: proposed |
| E5-23 | A column left half-initialised by an interrupted run is not re-initialised after a restore (96 of 150 MODEL_DATA rows set in the demo) [WB-05] | `core_writeback.py` `ensure_column`, `restore_flags` | Keep `initialising` across a restore, or re-initialise when the journal names the column | Open: proposed |
| E5-24 | A read-only MS fails with a raw "table.lock: Access is denied", after the backup and journal are written [WB-07] | `core_writeback.py` begin | Check writability first and refuse clearly | Open: proposed |
| E5-25 | No command or doc for restoring flags; after a CASA `flagmanager` restore, rang keeps refusing [WB-08] | `core_cli.py`; docs | `rang-core flags restore MS VERSION` wrapping `restore_flags`, and a docs section | Open: proposed (E4 for the docs) |
| E5-26 | On Windows a file held open by another program gives a raw "Access is denied"; the MS stays recoverable [WB-09] | `core_writeback.py` | Catch and name the file and the remedy | Open: proposed |
| E5-27 | `apply.targets` entry keys appear nowhere a user reads, not even `rang-core config defaults` [DOC-07] | `core_config.py`; docs | List `TARGET_KEYS` with their docs in `config defaults` | Open: proposed |
| E5-28 | The default `run.stages` is flag, calibrate, image; with `image.column: auto`, `rang-core run` then images uncalibrated DATA, against finish line item 1 [DOC-08] | `core_config.py` 481 | Default to all six stages, or the tutorial's config lists them | **Answered 2026-11-11** ("All six stages"): fixed in `b58c0d0` |
| E5-29 | `docs/cli.md` has no section for `formats`, `config check` or `gemclean` [DOC-09] | `docs/gen_cli.py` | Generate them | Open: E4 |
| E5-30 | `gemclean -h`, `-help`, `--help` print to stderr and exit 2 [DOC-10] | `core/src/gemclean/cli.rs` 362 | Help to stdout, exit 0 (WSClean's behaviour) | Open: proposed (Rust, rebuild) |
| E5-31 | No user example configuration ships and no Tricolour strategy YAML, though `flag.strategy` is required [DOC-11] | `examples/`; package data | Ship CARACal's MeerKAT strategy and one example config in the package; `rang-core config example` | Open: E4 |
| E5-32 | `docs/concepts/ingest.md` says creating tables needs python-casacore; `rang.core_ms_write.create_table` creates them (flag versions use it) [DOC-12] | `ingest.md` 16-17 | Correct it | Open: E4 |
| E5-33 | The licence table misses codex-africanus, katdal's test helpers, CARACal (`get_refant` followed "operation by operation"), msutils, CASA semantics, casacore-data; CARACal's GPL-2.0 (only or later is ambiguous) matters as for E5-11 [PK-08] | `docs/licence.md` 14-23 | Add the rows; the owner decides whether CARACal and msutils code was translated or only behaviour reimplemented | **Answered 2026-11-11** ("Reimplemented"): fixed in `5622ee5`; open: ask the CARACal authors to confirm GPL-2.0-or-later |
| E5-34 | `casacore_observatories.json` (shipped) has no documented source or licence [PK-09] | `python/rang/data/README.md` | Add source, sha256 and licence | Fixed in `6ad381f`; casacore-data's licence not checked |
| E5-35 | README says the wheel "carries every kernel" and lists a GPU gridder; the wheels are built without the `gpu` feature [PK-12] | `README.md` 24, 57-58 | Say the GPU paths need a source build | Open: E4 |
| E5-36 | The GitHub environment `pypi` has no protection rule, so any `v*` tag from anyone with write access publishes [PK-14] | repository settings | A required reviewer (the owner) on `pypi` | **Owner** (settings): the owner sets it in GitHub, no change here |

The owner decisions among them, E5-20, E5-28, E5-33 and E5-36, were answered on 2026-11-11 (section 3). Two more, proposed:

| ID | Finding | Where | Fix | State |
| --- | --- | --- | --- | --- |
| E5-37 | CONTRIBUTING and a pyproject comment say the sdist carries only the crates, `python/`, `tests/` and `tools/wheel/`; it also carries `data/`, `CITATION.cff` and four dev-only `tools/` files [PK-15] | `CONTRIBUTING.md` 90-92; `pyproject.toml` 84-87 | Exclude the four tools files, then list what ships | Fixed in `44f22a5`, also `.claude/` and `tools/e2e/` |
| E5-38 | `pip install 'rang-core[recipes]'` fails on Python 3.14 (stimela 2.1.4 requires < 3.14) [PK-16] | `pyproject.toml` 52 | Environment marker | Fixed in `f76d658` |

### 2.3 Later (14 groups)

- **E5-39** Data from other telescopes is neither refused nor warned about (MeerKAT first, `research/meerkat-scope.md`) [CLI-08].
- **E5-40** Small CLI inconsistencies: `--version` and `--receipt` placement, exit codes [CLI-09]; duplicate YAML keys accepted silently [CLI-13]; help overstates validation [CLI-12]; refusal wording [CLI-11].
- **E5-41** Mask paths resolve against the working directory, strategy and sky-model paths against the config file [CLI-10].
- **E5-42** A kill between a flag version's rename and its list line leaves an unlisted version [WB-10]; a missing recorded version is skipped silently [WB-12]; an interrupted manual restore leaves no record [WB-14].
- **E5-43** No kill test on Windows in the suite (run by hand here, section 1) [WB-11]; "before each stage writes" does not hold for model-only writes [WB-13].
- **E5-44** A real MS lock off Linux (E5-04 states the limit).
- **E5-45** No SPDX headers and no header policy: python/rang 110 of 110 files, core/src 28 of 81, src 7 of 7, tools 73 of 73 carry no GPL notice; core/py/src has them all [PK-18].
- **E5-46** The `meerkat` extra needs a C compiler and has no cp314 wheel [PK-19].
- **E5-47** Development Status classifier (Alpha) is the owner's choice at E6 [PK-20]; README links point at the moving `main` [PK-21].
- **E5-48** Rust dependency licences not shipped as text (an SBOM ships) [PK-22]; sdist tests that cannot run from it [PK-23]; flagger weights: nothing is bundled yet (F3 decision 2 allows LUNO-derived weights; their notice when they ship) [PK-24].
- **E5-49** Docs: tutorials page says "once released" [DOC-14]; no page for the user chain and the API index omits the chain modules [DOC-15]; `research/gemclean.md` predates G7 and G8 [DOC-16]; from-source and recipe gaps [DOC-17]; `image.uvrange` documented as "not read" though setting it is an error [DOC-18].
- **E5-50** rang's table reader cannot read FEED's string-array `POLARIZATION_TYPE` (finish plan item 14). No user path reads it: `cal_pol` reads only `RECEPTOR_ANGLE`, and circular feeds are refused from `CORR_TYPE`.
- **E5-51** Receipts hash any modified directory in full; see E5-20 for the MS. Small run directories are fine. Since `25b0f10` (E5-20) a modified directory is listed by its listing hash; a new one is still hashed in full.
- **E5-52** Image hashes differ between native Windows and Linux builds in every file (G4 decision 1, not investigated); the release states it, see section 3.


## 3. Owner decisions the release must state

From `finish-plan.md` section 7, item by item. **State** means a sentence in the release notes or docs; **confirm** means a coordinator choice
the owner has not answered; **internal** means nothing a user sees.

| Item | Decision | Verdict |
| --- | --- | --- |
| 1, 2 | Finish line with polarisation; multiscale in | state (scope) |
| 3, 30 | Coarse gridding default (1e-4, single precision), revertible; one-quadrant beam fit copied from WSClean | state (CHANGELOG has it) |
| 4, 31 | Name `gemclean` kept (G8's clash check, "recommended"); x86-64 baseline; `image.gemclean: auto` runs only the installed extension | **confirm** the name before it ships as a console script; state the baseline in installation docs |
| 5 | Self-calibration phase then amplitude; Tricolour replaces tfcrop; K by FFT then Gauss-Newton | state (methods) |
| 6 | Split legs E1 + E2-A + E2-B; native data (E2-N) untested; polarisation claim on processed LUNO plus simulation | **state**: "not yet tested on native MeerKAT data" |
| 7 | C4a: 1-2 ulp residual on random-phase B tables; CASA's Df substitution copied | confirm; state the substitution |
| 8, 16 | Parallactic-angle frame: CASA's (provisional) | confirm; state |
| 9 | C2a: solution TIME reported, not gated; `combine='scan'` keeps QuartiCal's estimator; SIGMA weights with pre-applied tables | confirm; state the TIME difference |
| 10 | C4b: general-Jones flag rule; complex gains never transferred to a target; models on primary fields only | confirm; the refusals are stated by the config reference |
| 11 | K as `delay_and_offset`; K offsets not in the K table (G absorbs them); delay error low by 1.5-2 (open) | **state**: a K table applied alone lacks the offsets; confirm the delay error |
| 12 | W4: uniform imaging weights as a gemclean option; WEIGHT fallback; autocorrelations left out of the solve | state |
| 13 | C2d: fit-error gate reported only; no spectral index on one window | internal |
| 14 | Taylor & Legodi table (open); RM referenced to λ = 0 in `rang.simtruth`; FEED string array unreadable | internal (E5-50) unless the table ships |
| 15 | Options refused with no owner: `solnorm: true`, `calmode: a`, `gainfield` on pre-applied tables, complex terms mixed with K, G, B, A, F | state (refusal list) |
| 17, 22 | 8 GiB default memory limit; chunk keys outside the stage hash; slow channel chunks (30-52 min arms) | state the limit and the slowness |
| 18 | Research recipes kept in `recipes/` | internal |
| 19 | `feed_angle_rotation` used in memory, FEED not rewritten: CASA reading a rang-calibrated MS whose FEED holds 0 applies a different P with `parang=True` ([c6w-polwire.md](c6w-polwire.md) section 7 item 5) | **state** wherever CORRECTED_DATA is handed to CASA; confirm |
| 20, 24, 26 | G3, G5, G9 refusals (log-pol fit, squared joining, XY/YX/circular, `-link-polarizations`, model writing and selfcal for Q, U, V) | state (gemclean's refused options) |
| 21 | E0: refant by name as CARACal's code; stop when no antenna qualifies | state |
| 23 | gemclean writes the model column by default (as WSClean); `image.write_model` false in rang-core | state |
| 25, 29 | Selfcal model-absorption limit accepted for v0.2.0 | **state** |
| 26, 28 | Frozen G9 C/D or post-hoc C′/D′ as the record; Windows and Linux image hashes differ (not investigated); Högbom automatic mask finishing early; MFS `WSCNVIS` convention | **confirm** which G9 record the release cites; **state** that images are not byte-identical across platforms (no tolerance was measured across them) |
| 27 | E1: refant `auto` default, `image.niter` raised, CASA arm, scorer fixed | answered; state E1's outcome |
| 32 | F3/F4: no learned flagger in `rang-core flag` | state |
| 33 | CARACal strategy 1 and its refant leakage limit (X-Y drift 13-22° rms for refants other than m000 on A1); 530 flag cells against Tricolour; `average_time` off by default, differs from CubiCal's estimator | **state**. `average_time` is not on main yet (only on E2's branches) |

New decisions from this review: E5-11 (simms licence), E5-20 (receipt hashing), E5-28 (default stages), E5-33 (CARACal and msutils
classification), E5-36 (PyPI environment protection). **Answered 2026-11-11** (owner, through the coordinator; `finish-plan.md`
section 7 item 35): E5-11 "Facts, not code": keep `data/*.itrf.txt`, state in `docs/licence.md` that the antenna coordinates are
uncopyrightable facts taken from simms, drop the three unused `.itrf` files from the sdist. E5-20 "Listing hash": receipts record the
MS by a listing hash (file sizes and mtimes), not a full sha256; provenance of what was written comes from the stage hashes. E5-28
"All six stages": the default `run.stages` is the full chain (the five stages flag, calibrate, apply, image, selfcal; there is no
sixth yet). E5-33 "Reimplemented": CARACal and msutils are behaviour reimplemented from source and docs, listed in `licence.md`
with codex-africanus, katdal's test helpers, CASA semantics and casacore-data; follow-up: ask the CARACal authors to confirm
GPL-2.0-or-later. E5-36: the owner sets the `pypi` environment protection in GitHub settings. Section 4.1 lists the commits. Two rules chosen here, provisional and open to the owner: E5-03 saves the
replaced flags on every rerun (one FLAG-size copy each, about 22 GB on E2-A's 180 GB MS) rather than comparing first; E5-02 keeps
`selfcal.input_column: DATA` valid when nothing is copied into it.

## 4. Fixes on `e5-prereview`

One commit per fix, each with a test (section 1 says which fail on `3eab67c`):

| Commit | ID | Test |
| --- | --- | --- |
| `2bac745` | E5-13 | `test_w2_commands.py::test_a_second_command_on_a_locked_run_directory_is_refused` |
| `25e1809`, `bbb2a9d` | E5-01 | `test_a_stale_stage_reruns_on_the_new_upstream_flags`, `test_a_stage_that_wrote_no_flags_leaves_the_later_restore_in_place` |
| `47e5520` | E5-14 | `test_e5_prereview.py::test_malformed_values_give_the_error_report_not_a_traceback` and two forms |
| `1c8a617` | E5-15 | `test_a_changed_configuration_is_refused_and_force_restores_first` (the hint) |
| `c9ee936` | E5-16 | `test_w4_5_release.py::test_release_jobs_check_the_tag` |
| `045f629` | E5-17 | `test_w4_5_release.py::test_versions_agree` |
| `7fe286b` | E5-05 | `test_w4_5_release.py::test_pyproject_metadata` |
| `ef4f9bf` | E5-02 | `test_e5_prereview.py`: three DATA tests |
| `62d25c9` | E5-03 | `test_a_rerun_saves_the_flags_its_restore_replaces` (and the flag-version count, 3 to 4) |
| `fc27092` | E5-04 | none (two sentences) |
| `686cca3` | E5-18 | `test_the_missing_model_column_refusal_names_the_imager_option` |

**Behaviour changes a user sees:**
- A forced or resumed rerun adds one flag version, `rang_rerun_<UTC>`.
- `apply.column: DATA` and `selfcal.model_column: DATA` are now configuration errors.
- `selfcal.input_column: DATA` is refused when this run's apply would be copied into it.
- No stage hash changes.

Files touched that E2's branches (`fp-e2-acceptance`, `fp-e2-averaging`) also change: `core_config.py`, in `_check` and `_selfcal_errors`
and one line in `resolve`; E2's hunks are in `SCHEMA` and the refusals. Also `core_pipeline.py` in `RunDir`, `restore_before`,
`_selfcal_input` and `execute`; E2's hunk is in `stage_image`. They do not overlap; a merge should be clean.

**Checks run:** check-all's light steps (`ruff check` and `ruff format --check` on python, examples and tests with ruff 0.17.3,
`git diff --check main..HEAD`) pass. The Windows kill-and-resume of section 1, rerun on the branch's code: FLAG and `rang_original`
equal the reference, and the rerun added `rang_rerun_<UTC>`. Also every other light test file that imports a changed module
(`test_calmodels`, `test_core_cli`, `test_d1_docs` including `test_cli_page_matches_help`, `test_g7_defaults`, `test_g8_gemclean`,
`test_p12_rename`, `test_w3_chunking`, `test_w3b_chainchunks`, `test_w4_1_receipts`, `test_w5_recipes`): 105 passed, 1 skipped. Targeted pytest on Windows (Python 3.14.10, the main checkout's
`_core.pyd`): `test_w2_commands`, `test_c5_selfcal`, `test_c5b_selfcal_masks`, `test_e0_refant_extend`, `test_c2e_calibrate`,
`test_c6w_polwire`, `test_w1_writeback`, `test_c4b_applycal`, `test_w4_unsupported`, `test_g6_model`, `test_w4_5_release` and
`test_e5_prereview`: 109 passed, 12 skipped (the POSIX-only ones) at `62d25c9`; then 41 passed, 3 skipped on the three files the last
commit touched. **Not run:** the full `tools/check-all.sh` (heavy lock busy; the coordinator runs it at merge), and every POSIX-only
test (the 12 skips, among them the suite's SIGKILL and resume tests): they need Linux or macOS.

### 4.1 Owner decisions and proposed fixes on `e5-decisions`

Cut from main `92f71ec` (which has `e5-prereview` merged); one commit per decision, each with a test:

| Commit | ID | Change | Test |
| --- | --- | --- | --- |
| `25b0f10` | E5-20 | A modified MS is listed by `listing_sha256`; receipt version 5; `docs/cli.md` | `test_w2_commands.py::test_flag_writes_the_port_flags_with_backups_and_a_receipt` |
| `b58c0d0` | E5-28 | Default `run.stages` = `STAGES`; `docs/cli.md`, `docs/agents/image-a-meerkat-ms.md` (the E4 tutorial config lists its stages and needed no change) | `test_w2_commands.py::test_config_check_and_defaults` |
| `5a0ac94` | E5-11 | `licence.md` and `data/README.md`: facts, not code; sdist excludes `kat7`, `vla-c`, `wsrt` | `test_w4_5_release.py::test_sdist_excludes_the_research_tree`, `::test_the_antenna_tables_are_recorded_as_facts` |
| `5622ee5` | E5-33 | `licence.md`: two ported rows, a reimplemented table, the CARACal follow-up | `test_w4_5_release.py::test_the_licence_table_lists_every_upstream` |
| `6ad381f` | E5-34 | `rang/data/README.md`: source, SHA256, licence not checked | `test_e5_decisions.py::test_the_observatory_table_has_its_source_and_hash` |
| `44f22a5` | E5-37 | sdist excludes `.claude/`, `tools/a1_*.sh`, `tools/e2e/`, `tools/gain_hash_gate.py`, `tools/heavy_lock.py`; CONTRIBUTING lists what ships | `test_w4_5_release.py::test_sdist_excludes_the_research_tree` |
| `f76d658` | E5-38 | `recipes = ["stimela==2.1.4; python_version < '3.14'"]`; README | `test_w4_5_release.py::test_the_recipes_extra_resolves_on_every_declared_python` |

A built sdist (`maturin sdist`, Windows) holds `.gitattributes`, CHANGELOG, `CITATION.cff`, `Cargo.*`, LICENSE, README,
`THIRD-PARTY-NOTICES.txt`, `pyproject.toml`, `core/`, `src/`, `python/`, `tests/`, `tools/wheel/` and `data/` with `README.md` and
`meerkat.itrf.txt` only; no wheel was built from it here. Checks: targeted pytest with `PYTHONPATH` set to the worktree's `python/` (`test_d1_docs` runs the CLI in a subprocess, which otherwise
imports the main checkout's package): `test_core_cli`, `test_w2_commands`, `test_d1_docs`, `test_w4_unsupported`, `test_w4_5_release`,
`test_e5_prereview`, `test_e5_decisions`, `test_w4_1_receipts`, `test_w1_writeback`: 119 passed, 12 skipped; `docs/gen_cli.py --check`,
ruff check and format, `git diff --check`.
Not run: `tools/check-all.sh` (the coordinator runs it at merge) and the POSIX-only tests.

## 5. Release checklist (not findings)

At E6, after E2, E3 and E4: bump 0.1.0 to 0.2.0 in `pyproject.toml`, the three `Cargo.toml`, the three `Cargo.lock`, `CITATION.cff` and
`docs/installation.md` 113 (the list is in the packaging notes); `## 0.2.0` in CHANGELOG with Known limits (E5-09, E5-10); the classifier
(E5-47); rerun this review on the candidate, wheel installed, with `tools/check-all.sh` green and no release-blocking finding open.
