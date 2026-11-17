# v0.3.0 pre-release review (E5 method)

Status, 2026-11-17: **done on origin/main `9b4542cb`** (`git log v0.2.0..origin/main`, 336 commits); small
safe fixes on branch `v030-ready`, the rest listed for the coordinator. The four results still running
(E2-N, E3-A, the selfcal-defaults grid, the E2-A 3b K follow-up) are not reviewed here; they need a delta pass
when they merge. Tracker: [v030-readiness.md](v030-readiness.md).

**Update, 2026-11-17 (branch `v030-fix`, section 5):** B-01 and B-02 have their notices, read in the upstream
sources; B-02 found radler LGPL-3.0-only, which leaves an owner decision (5.1). R-02, B-11, B-12, B-13, B-16,
E5-22, E5-23 and E5-24 are fixed with tests; E5-21 stays a known limitation (5.3).

## 1. Method

As [e5-final.md](e5-final.md) section 1, in brief:
- **Agent A** (read only): every finding e5-final and [e5-prereview.md](e5-prereview.md) left open, in part,
  protected or for the coordinator, re-verified on today's code by quoting it or running it; and every
  docs statement that main's state has made false.
- **Agent B** (read only): the code and docs new since v0.2.0 (MSv4 reader, chunk tasks, `lightcurve`, the
  MCP server, `bandpass_model_divided`, `casa_phase_weights`, GeMClean `-reorder`, memory, the theoretic-beam
  fix, `-stop-tolerance`, the multiscale options), new keys against the stage hash, `RANG_*` against
  `rang.core.ENVIRONMENT`, CHANGELOG completeness, `docs/cli.md`, licence notices.
- **By hand:** the MCP chain on the public fixture as an agent would drive it (`tests/test_mcp_chain.py`),
  which found R-01 and R-02; the quick check; each fix here reproduced first.
- Classes as in e5-final: **release-blocking** (a user following the docs gets a wrong result or loses data,
  the release states something false, or it is legally wrong), **should-fix** (wrong but recoverable, or a
  clear message missing), **note**. IDs: R- by hand, A- and B- from the agents, E5-/NEW- kept from earlier
  passes.
- **Rule for fixes here:** docs, messages, tests and one I/O retry; nothing that changes a number, a stage
  hash or a default while E2-N, E3-A and the grids run from their own venvs.
- Both agents ran from the main checkout's venv, whose `_core` is from 2026-11-13 (older than the
  `-stop-tolerance`, `-reorder` and multiscale merges), so their Rust readings are from source only. Rebuild
  it before using it as origin/main.

## 2. Fixed on this branch

| ID | Class | Finding | Fix |
| --- | --- | --- | --- |
| R-01 | should-fix | On Windows, polling `run_status` through `rang-core mcp` (or any reader of `state.json`) made the run's `os.replace` of `state.json` fail with PermissionError, so the run failed after a finished stage. Found by the chain test (its first run failed). The job-file form was #30 | `core_pipeline._write_json` retries the replace for up to 10 s on Windows; test `test_run_state_survives_a_polling_reader` (fails without the fix, passes with it) |
| A-1 to A-4 | release-blocking (false statements) | `docs/limits.md`, `docs/index.md`, `docs/howto/index.md` and the tutorial (section 6) said E2 had not reported | Replaced with what E2-B, E2-A and E3-B reported and what still runs |
| A-5 | should-fix | `limits.md`: the floor "for a reason not found" | floor-3 and floor-4's attribution, the 8.6 × remainder |
| A-6 | should-fix | Memory figures gave only Stokes I (2.0-2.4 ×) | Joined IQUV 4.7-6.9 ×, `-reorder` (limits.md) |
| A-7 | should-fix | `rang-core flagdata -h` listed tfcrop among the modes; it is refused | Help says tfcrop is refused until parity; `docs/cli.md` regenerated |
| A-8, B-04 to B-09, B-24 | should-fix | Unreleased missed `lightcurve`, `-stop-tolerance`, the multiscale options, FLAG_ROW out of the weight grid (a WSClean difference), MSv2 R1-R3, heavy-lock changes; nothing told users a 0.2.0 run directory resumes without the new angles and weights | CHANGELOG entries; known limitations; `--force all` line |
| E5-10 | release-blocking (editorial) | Unreleased had no known limitations | "Known limitations" and "Issues" sections drafted |
| A-9, B-18 (part) | should-fix | No `mcp` or `msv4` row in the extras tables | README and `docs/installation.md` rows |
| A-10 | note | `howto/calibrate.md` gave E2-B's −90 receptor angle as the example without the LUNO finding | Per-product note after chi-offset decision 11.1 |
| B-14 | should-fix | `lightcurve --scale foo` ended in a traceback | `LightcurveError`, exit 2; positive and finite; test |
| B-15 | should-fix | A `--positions` CSV without `ra_deg` refused with only `'ra_deg'`; non-numbers gave a traceback; Dec unchecked | Names the missing columns, the line, the Dec range; test |
| B-17 | note | `docs/gen_cli.py`: "one point per 8 s integration" (the default is one integration of any length) | "per integration" |
| B-19 | note | `rang.msv4.open_processing_set` without the extra raised a bare ModuleNotFoundError | Names `rang-core[msv4]` and Python 3.11+; test |
| B-20 | note | Two new GeMClean refusals carried a run of 14 spaces mid-sentence | Fixed (messages only) |
| #22 docs | note | `pol-join-squared.md` and `u5-upstream.md` said radler !238 was open | Dated pointers: merged 2026-11-16, unreleased |

## 3. For the coordinator: release-blocking, not fixed here

| ID | Finding | Evidence | Suggested fix |
| --- | --- | --- | --- |
| B-01 | `cal_pol.parallactic_angle_casa` (720c8de9) follows casacore's measures source (`MCDirection.cc`, `MeasMath.cc`, `MeasTable.cc`), which `THIRD-PARTY-NOTICES.txt` and `docs/licence.md` do not list | `e2b-misses.md` 9.15-9.16 ("as read in its source"); notices list casacore `LSQFit.cc` only | Add casacore measures (LGPL-2.0-or-later, AUI notice read from the files) to the notices, `licence.md` and the `cal_pol.py` header |
| B-02 | GeMClean files say "read in radler 76fe447" / WSClean 3.7 (`mask.rs`, `joined.rs`, `multiscale.rs`, `stokes.rs`; new since 0.2.0: the joined auto-mask, `-no-negative`, the bias reference, the !1068 beam fix); radler is in neither the notices nor `licence.md` | `grep -i radler THIRD-PARTY-NOTICES.txt docs/licence.md`: no hits | Add radler 76fe447 and WSClean 3.7 with ASTRON's notice, read from the sources |

Both need the upstream headers read verbatim (not on this host's Windows checkout), so they are not
drafted here. **Both done on branch `v030-fix` (section 5.1).**

## 4. For the coordinator: should-fix and notes

| ID | Class | Finding | Small and safe? |
| --- | --- | --- | --- |
| R-02 | should-fix | A calibrate solve with every solution flagged ends `rang-core run` in a Python traceback (`RuntimeError: gaincal wrote no solutions for field 0`), not a stage failure message; seen on the fixture with refant m000, whose baselines the example strategy flags entirely | message (`core_pipeline` stage error handling) |
| B-03 | should-fix | `SolveDataBuffer.cc`'s notice does not list `cal_gain.py` (`phase_only`, A3) | notices only |
| B-11 | should-fix | `-temp-dir` does not move the `-dirty-<n>.spill` files (beside `-name`) | message or paths |
| B-12 | should-fix | `-reorder` silently skipped with `-channel-range` / `-average-channels > 1` and with one polarisation; `-temp-dir` alone accepted silently | help text |
| B-13 | should-fix | `lightcurve.json` can hold bare `NaN` (fully flagged interval) | output format: decide on purpose |
| B-16 | should-fix | `lightcurve` images DATA_DESC_ID 0 only, silently | refusal |
| B-18 (rest) | should-fix | `rang.msv4`, `rang.lightcurve`, `rang.core_tasks` missing from `docs/api/index.md` | docs |
| B-21 | note | A run ended by `-stop-tolerance` reports StopReason::Threshold | changes `-report.json` |
| B-22 | note | With `data.processes > 1` the parent's in-flight partials are outside `memory_limit_gb` | docs |
| B-23 | note | The spawn pool is not tested through the Windows `rang-core.exe` launcher | CI smoke |
| B-25 | note | The MCP gemclean allowlist lacks `-reorder`, `-temp-dir` and the new multiscale options | allowlist |
| B-26 | note | `-reorder` temporary files (about 28 GB) survive a kill | help line |
| E5-16 | should-fix | The release job does not run `test_w4_5_release.py` | workflow |
| E5-19 | should-fix | Refusals still print task IDs ("(task W4: ...)", "(task G9)"); docstrings say receipt version 3, the code writes 5 | messages and tests |
| E5-21, NEW-03 | should-fix (stage hash) | Strategy, sky-model and mask files enter the stage hash by path, not content; selfcal's hash omits the `calibrate.refant` it falls back to | no: changes every hash once |
| E5-22, E5-23, E5-24, E5-26, WB-14 | should-fix | Write-back journal before the lock; restore loses `initialising`; no writability check or clear "Access is denied"; no `restoring` state | write-back logic |
| E5-25, E5-27, E5-31 | should-fix | No `flags restore` command; `config defaults` omits apply target keys; no packaged example config | features |
| E5-30 | should-fix | `gemclean -h` exits 2 on stderr | Rust plus `gen_cli` |
| NEW-05 to NEW-10 | should-fix / note | `config check` passes a flow-style or misspelt strategy, a missing or directory strategy, an unknown explicit refant; Latin-1 config gives a traceback; empty strategy accepted; `average_freq` with `complex` not refused | messages, preflight |
| E5-36 | owner | The `pypi` environment has no protection rule | settings |
| E5-47 | owner | "Development Status :: 3 - Alpha"; README image links on `main` | at E6 |
| E5-33, E5-34, E5-44, E5-46, E5-48, E5-49, E5-51, E5-52, NEW-2, NEW-3, NEW-11, NEW-14 | note | As e5-final; still open | later |

Checked, no finding: new keys stay out of the stage hash at their defaults (`data.executor`, `processes`,
`threads` in `RESOURCE_KEYS`; `casa_phase_weights`, `bandpass_model_divided` in `HASH_DEFAULTS`, each with a
test); every `RANG_*` variable in the registry's scope is registered; `docs/cli.md` matches the source.
Flaky test #30: closed by `61767423`; `test_confirmed_gemclean` passed 20 of 20 repeats here, so no further
cause was found for it, but its run-state form was R-01.

## 5. Fixed on branch `v030-fix` (2026-11-17)

Branched from the merge of `v030-ready`. Nothing here changes a number, a default, a stage hash or an
archived output: the fixes are notices, messages, a refusal, the JSON spelling of non-finite values, the
location of GeMClean's temporary files and write-back bookkeeping. Proof (section 5.4): `python
tools/check_all.py --quick` PASS on `b572c7be`, with the gain-hash gate PASS, and again after the audit
additions (5.5).

### 5.1 Licence notices (B-01, B-02), read in the upstream sources

Sources fetched read only into `~/Build/tmp/20261117-v030fix-upstream` (removed after): git clones of
casacore and of WSClean with its submodules, Debian's `debian/copyright` of wsclean 3.7-3, and the
astropy-iers-data sdist. Nothing in them was built or run.

- **B-01, casacore measures.** `parallactic_angle_casa` translates casacore's route and constants: the
  J2000 → APP → TOPO → HADEC route (`MCDirection.cc`), `MeasMath::applyTOPOtoHADEC` and
  `deapplyPolarMotion` (`MeasMath.cc`), `MeasTable::calcUTtoST` (the coefficients 1.002737909350795,
  +5.9006e-11, −5.9e-15), `diurnalAber` and `polarMotion` (`MeasTable.cc`), and `MSDerivedValues::parAngle`.
  Read at casacore master `3c16927b` (2026-11-15 16:17 +0100), inferred from e2b-misses 9.13's "master at
  2026-11-15", which records no commit. All four files: GNU Library General Public License, version 2 or
  any later version, Associated Universities, Inc.; compatible with GPL-3.0-or-later, as the CASA ports are
  (e5-final F-05).
  - **Data**: no casacore data is read. The Earth orientation (UT1 − UTC, polar motion x, y) is
    `astropy.utils.iers.earth_orientation_table` with `auto_download = False`, that is astropy-iers-data's
    bundled IERS tables (`eopc04.1962-now`, `finals2000A.all`, `Leap_Second.dat`; the package is
    BSD-3-Clause, Astropy Developers), plus erfa (`pnm80`, `pnm06a`, `gst94`). Both are dependencies, not
    redistributed; the wheel ships no IERS or measures table (`python/rang/data` holds two static masks,
    `TRICOLOUR-LICENSE`, `casacore_observatories.json`, `meerkat.itrf.txt` and `README.md`).
  - `tests/data/pa_casacore.json` (in the sdist through `tests/`) holds casacore's computed angles from
    CASA 6.7.6.14 (`research/results/e2b-misses/p1_fixture_casa.py`): numbers computed by casacore, no
    table or code copied.
  - `casacore_observatories.json` (E5-34, casacore-data 20250826-160001-5) is not used by this function;
    its licence stays unchecked (the version is not a Debian one, and no `debian/copyright` was found for
    it).
  - Added: the four notices verbatim in `THIRD-PARTY-NOTICES.txt`, a `docs/licence.md` row and the
    `cal_pol.py` header; test `test_w4_5_release.py` (the notices and the header).
- **B-02, WSClean 3.7 and radler.** WSClean v3.7 is `4f395b28` (2026-02-14); it pins radler `76fe4474`,
  aocommon `aa4d6a47` and schaapcommon `b553fd25`. The !1068 fix GeMClean follows is master `53e25d59`
  (2026-11-13, "Fix an issue in CalculateMsLimits"); `multiscale.rs` cited `ca23d835`, the merge request's
  commit, and now names both. Headers read:
  - **radler: `// SPDX-License-Identifier: LGPL-3.0-only`** in every file GeMClean cites (`radler.cc`,
    `generic_clean.cc`, `deconvolution_algorithm.cc`, `subminor_loop.cc`, `multiscale_algorithm.cc`,
    `multiscale_transforms.h`, `image_set.h`, `image_set.cc`, `gain_calculations.h`), with no copyright
    line; README "Radler is released under the LGPL version 3."; `LICENSE` (GPL-3.0) and `LICENSE.LESSER`
    (LGPL-3.0); pyproject authors Andre Offringa, Maik Nijhuis, Jakob Maljaars, Tammo Jan Dijkema.
  - WSClean's own sources: no notice in any file GeMClean cites; README "WSClean is released under the
    GPL license version 3"; Debian's wsclean 3.7-3 `debian/copyright` says GPL-3.0+ ("taken from the web
    page") with the same three copyright lines as 3.6-1.
  - aocommon: `polarization.h` and `image.h` carry no notice; `LICENSE` is GPL-3.0; `uvector.h` says
    "distributed under the GPL license version 3"; its AVX headers say GPL-3.0-or-later (ASTRON).
  - schaapcommon: `gaussianfitter.cc`, `spectralfitter.cc` (Copyright (C) 2022 ASTRON) and
    `reordering.cc` (2024 ASTRON), each GPL-3.0-or-later.
  - **Compatibility.** LGPL-3.0 section 2(b) lets a modified version be conveyed "under the GNU GPL, with
    none of the additional permissions of this License applicable to that copy", and section 0 defines
    the GNU GPL as version 3. So radler-derived code may be distributed with rang-core under GPL version 3.
    It is not the incompatible case (GPL-2.0-only would be), so nothing is withheld; but those parts
    cannot be offered under "any later version". `mask.rs`, `joined.rs`, `multiscale.rs` and `stokes.rs`
    now carry `GPL-3.0-or-later AND LGPL-3.0-only` and a line naming radler (as `predict.rs` names its BSD
    source; test `test_spdx_headers.py`), and the notices say that the extension, while it contains them,
    is GPL version 3 only.
  - **Owner decision (not taken here):** `LICENSE` and `pyproject.toml`'s `license = "GPL-3.0-or-later"`
    are unchanged. Options: state the package expression as `GPL-3.0-or-later AND LGPL-3.0-only` (or the
    wheel as GPL-3.0-only); ask radler's authors for "or later"; or reimplement the radler-derived parts
    from documentation only. The same question applies, more weakly, to WSClean's own README ("version
    3", where Debian records 3+; e5-final NEW-2) and to aocommon; the existing 3.6 ports (`grid.rs`,
    `weights.rs`) rest on Debian's GPL-3.0+.

### 5.2 Should-fix items fixed, each with a test (`tests/test_v030_fix.py` unless named)

| ID | Fix | Test |
| --- | --- | --- |
| R-02 | `rang.cal_gain.NoSolutions` (a RuntimeError) from every "wrote no solutions" (G, K, B, KCROSS, Xf, Df); `core_pipeline.execute` turns it into `StageFailed` with a hint (refant, minblperant, minsnr, flags), so `rang-core run` prints `failed: calibrate: ...` and exits 1 | `test_fully_flagged_gaincal_ends_run_with_a_stage_failure` (the public fixture with refant m000, as the chain test found it); `test_no_solutions_is_a_runtime_error_and_pickles` |
| B-11 | `-temp-dir` also takes the joined runs' `<name>-dirty-<n>.spill` files | `cli.rs` `spill_files_go_to_temp_dir_when_given`; `gemclean_memory.rs` still finds `-temp-dir` empty after `-reorder` |
| B-12 | Warnings (stdout, before the run) and help lines: `-reorder` with one polarisation (ignored), with `-channel-range` or `-average-channels > 1` (each polarisation read whole first), `-temp-dir` where it has no effect; `docs/cli.md` regenerated | `cli.rs` `reorder_and_temp_dir_warn_where_they_do_not_act` |
| B-13 | `lightcurve.json` is strict JSON: non-finite values are `null` (documented in `rang.lightcurve` and the command's help); the returned dict and `lightcurve.csv` (`nan`) are unchanged; the TS-P1 scorers read through `np.array(..., float64)`, which turns null into NaN | `test_lightcurve_json_writes_null_for_values_that_are_not_finite` |
| B-16 | `light_curves` refuses a field with rows on any DATA_DESC_ID other than 0, naming them | `test_lightcurve_refuses_a_field_on_two_data_descriptions` |
| E5-22 | A column is recorded as written before its first put; `core_writeback.flags_unfinished(journal)` (open or failed, and FLAG or FLAG_ROW possibly written, or no record) decides the refusal in `WriteBack.begin` and in the pipeline's four journal checks, so a session that wrote no flags no longer blocks the next | `test_a_session_that_wrote_no_flags_is_not_refused`; `test_w1_writeback.py`'s during-init kill now expects no refusal |
| E5-23 | `WriteBack.begin` carries the journal's `initialising` columns in every state, `restored` included | `test_a_half_initialised_column_is_initialised_again_after_a_restore` |
| E5-24 | `begin` refuses an MS whose directory, `table.dat` or `table.lock` is not writable, before the flag backup; the writer is opened (and locked) before the journal is written, and a PermissionError there names the remedy | `test_a_read_only_ms_is_refused_before_anything_is_written` |

### 5.3 Left as known limitations

- **E5-21 (and NEW-03's stage-hash part).** Hashing the strategy, sky-model and mask files' contents, and
  selfcal's fallback refant, changes every stage hash once: every 0.2.0 and 0.3.0 run directory would
  report "configuration changed" (or need `--force`) with nothing of its own changed, and the archived
  run directories' hashes would stop matching. The brief forbids changing a stage hash unless the review
  says it must, and the review says "no: changes every hash once". Stated in CHANGELOG Known limitations
  (rerun with `--force` after editing a referenced file in place).
- E5-26 (a file held open by another program on Windows) and WB-14 (a `restoring` state) were not in
  this brief; E5-24's PermissionError message covers the first in part.

### 5.4 Proof that nothing else changed

`python tools/check_all.py --quick` (ruff, ruff format, cargo fmt, clippy with warnings as errors, the root and core
Rust tests, the extension build, pytest on the touched test files, the gain-hash gate against the archive)
passed on the branch before the push (log `outputs/check/20261117T093557Z-quick.log` in the worktree: 293 core
tests, 768 pytest passed, gain-hash gate PASS); the oracle gates (CASA, WSClean) are left to the
coordinator's full merge check.

### 5.5 The MIT audit's notice gaps (coordinator, 2026-11-17)

From [mit-relicense-audit.md](mit-relicense-audit.md) section 3.2 (branch `mit-audit`) and its
`files.csv`, fixed under the current GPL. Each upstream was read in its source, read only, into
`~/Build/tmp/20261117-v030fix-upstream`: c-blosc tag v1.21.6 (`616f4b73`), the PyPI sdists of katdal 0.23,
msutils 1.2.0, astro-tigger-lsm 1.8.0 and losoto 2.7.1, netlib's fdlibm `k_sin.c`, `k_cos.c`,
`e_rem_pio2.c`, casacore v3.8.1 (`5420b48e`) and v3.7.1, the casa6 mirror at `9269a52`, WSClean v3.6
(`5fdad9bf`) and CARACal `8f7bb363`. killMS 3.3.0 has no sdist on PyPI; its PyPI metadata gives the GPL-2.0
text, and only its file layout is used.

| Gap | Fix |
| --- | --- |
| c-blosc 1.21.6 in `core/src/blosc.rs` | SPDX `GPL-3.0-or-later AND BSD-3-Clause`, header names it; `LICENSE.txt` verbatim in the notices |
| katdal 0.23's BSD text (`meerkat.py`) | header line; `LICENSE.txt` verbatim in the notices |
| Tricolour in `core_flag.py` | SPDX `AND BSD-3-Clause`, header; the Tricolour notice names the file |
| fdlibm constants in `gpu/shader.rs` | SPDX `AND SunPro`; Sun's notice kept in the file, as it requires, and in the notices |
| Tigger and codex-africanus in `formats/sky.py` | SPDX `AND BSD-3-Clause`; Tigger 1.8.0's notice (MeqTree Foundation and ASTRON, GPL-2.0-or-later, used under GPL-3.0-or-later) and the two regexes named |
| `gemclean/input.rs` (`stokes_cell`) | header line; schaapcommon's notice names it |
| `calmodels.py` | CASA `Imager.cc` (GPL-2.0-or-later), `SpectralIndex.cc`, `SkyCompRep.cc`, `Flux.tcc` (LGPL-2.0-or-later): header and notices |
| `apply.rs`, `flag_extend.py` | casacore `Interpolate1D.tcc` (3.7.1), `MSIter.cc`, `BaseTabIter.cc`; CASA `CTTimeInterp1.cc`, `FlagDataHandler.cc`, `FlagMSHandler.cc` (LGPL-2.1-or-later, AUI and ESO): headers and notices |
| killMS, losoto (and Crystalball, DDFacet) | headers of `killms.py`, `h5parm.py`; a "formats only, no code" entry in the notices and `licence.md` |
| msutils | `flag_stats.py` has no notice; `LICENSE` is the GPL-2.0 text, PyPI metadata "GNU GPL v2", `setup.py` "version 3 of the License, or (at your option) any later version" (Copyright (c) 2016 SKA South Africa). No file says "version 2 only", so GPL-2.0 section 9 (any version) or `setup.py` (3 or later) gives GPL-3.0-or-later: **compatible**; about 20 lines of `wgs84_to_ecef`, a textbook formula the function attributes to the HiSPARC note. `licence.md`'s "licence not checked" replaced |
| WSClean 3.6 `wstackinggridder.h` | verbatim "published under the GPL 3 license." in the notices and `licence.md` (version 3, no "or later"; Debian records 3+); the notices' "its source files carry no notice" corrected |
| CARACal's strategy YAMLs under `research/results/` | 20 copies of `mk_rfi_flagging_calibrator_fields_firstpass.yaml` (2 byte copies of `8f7bb363`'s, 18 with trailing spaces removed); the upstream file has no notice. [results/CARACAL-NOTICE.md](results/CARACAL-NOTICE.md) lists them with CARACal's licence, and [results/CARACAL-LICENSE.txt](results/CARACAL-LICENSE.txt) is CARACal's `LICENSE` (GPL-2.0). The archived files are unchanged; `research/` ships in neither the sdist nor the wheels |
| `ism.rs`, `ms_write.rs`, `tiled.rs` said "nothing is copied"; `multifile.rs` said nothing | headers now say they translate casacore 3.8.1's storage managers (`ISMBucket::getSplit`'s loop kept in `split` and `get_split`); fifteen casacore files' notices verbatim (all LGPL-2.0-or-later, AUI) |
| `bandpass.rs`, `fluxscale.rs`, `reference.rs` said "CASA is not copied" | headers now say translated (`fillChanGapArray`; `fluxscale`; `applyRefAnt`, `verifyConstraints`); their CASA notices were already listed |

Tests: `test_spdx_headers.py` (the new SPDX expressions), `test_w4_5_release.py` (each holder in the notices
and the file, each casacore and CASA file named in both, no "nothing is copied" / "CASA is not copied" left,
WSClean's "GPL 3" line). Only comments, notices and docs change.
