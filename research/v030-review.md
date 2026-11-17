# v0.3.0 pre-release review (E5 method)

Status, 2026-11-17: **done on origin/main `9b4542cb`** (`git log v0.2.0..origin/main`, 336 commits); small
safe fixes on branch `v030-ready`, the rest listed for the coordinator. The four results still running
(E2-N, E3-A, the selfcal-defaults grid, the E2-A 3b K follow-up) are not reviewed here; they need a delta pass
when they merge. Tracker: [v030-readiness.md](v030-readiness.md).

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
drafted here.

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
