# Big plan task W4-6: portability hygiene

Branch `w4-6-encoding` from `main` `6beec0a`. Fix task W4-6 of the
[final review](w4-review.md), findings W4R-11 (text encodings) and W4R-12 (CRLF),
and the 17 example scripts [W4-2](w4-2-boundaries.md) left.

**Status: implemented and measured.** Text files in `python/rang` name UTF-8,
except three verbatim P11 sites that stay as frozen. Tracked files are LF outside
`research/results/` and `history/`. `python -m rang.check` passes on native
Windows with UTF-8 mode off and `core.autocrlf=true`. The new CI cell has not run
on GitHub; its local equivalent passes.

## What changed

| Item | Change |
| --- | --- |
| `python/rang` (25 files) | 65 `read_text`, 24 `write_text` and 1 text `.open` gain `encoding="utf-8"`; every write also gains `newline="\n"`. An AST diff against `6beec0a` differs by nothing but those keywords. |
| `tests/test_w4_6_portability.py` | New. An AST check of `python/rang`, a self-test of that check, and a sky model read with UTF-8 mode off. |
| `.gitattributes` | New, as specified. 11 files renormalised: `git diff --ignore-cr-at-eol` is empty for them. |
| 19 example scripts | `str(x).startswith("outputs...")` becomes `x.as_posix().startswith(...)`. Every `x` is a `Path`. |
| `.github/workflows/wheels.yml` | The `windows-x86_64` py3.14 test cell sets `PYTHONUTF8=0`; the other cells keep `1`. |

The renormalised files are `docs/execute_notebooks.py`, the 7 `docs/logo/*.svg`,
`research/d3-science-notebooks.md`, `tests/test_core_imaging.py` and
`tests/test_d3_notebooks.py`. None is in a `CODE_FILES` list or a P11 extract
hash, and no SHA256 of their old bytes appears in `research`, `tests`, `python`,
`history` or `examples`.

## Measured acceptance

| Criterion | Result | Evidence |
| --- | --- | --- |
| No `i/crlf` outside `research/results/` and `history/` | 0; the one `i/crlf` left is `research/results/p11-extract/closure.py` | `git ls-files --eol` |
| Identity suite, same tree before and after (Linux) | `identical`, all 20 cases, with the known failures unchanged (`trend-frozen`, `campaign-check`, `backends`) | `outputs/w4-6-20261102-01/base-head-diff.txt` |
| `test_pc1_preconditions`, `test_p11_extract`, `test_core_backends`, before and after | 37 passed each, no skips, so the replays did run | `base-pytest.log`, `head-pytest.log` in the same directory |
| Native Windows `python -m rang.check` | `overall: PASS`, 812 passed, 78 skipped; `utf8_mode 0`, cp1252, `core.autocrlf=true`, working files `w/lf` except `closure.py` | `outputs/w4-6-20261102-02/windows-check.log`, `mode.txt` |
| WSL `bash tools/check-all.sh` at `c658ec6`, the last code commit | `overall: PASS`, 879 passed, 11 skipped | `outputs/w4-6-20261102-check-all-c658ec6.log` |
| WSL `bash tools/check-all.sh` at `7fb4299`, this note added, index line not yet added | `overall: FAIL`, 878 passed, 11 skipped, 1 failed: `test_every_note_is_in_the_research_index` only. Expected, see "For the coordinator". `test_w4_8_docs.py` passes (12) with a temporary index line. | `outputs/w4-6-20261102-check-all-7fb4299.log` |
| Windows wheel test, py3.14, `PYTHONUTF8=0`, with the fixture | `overall: PASS`, 51 passed, 5 skipped | `outputs/w4-6-20261102-02/wheel-test.log` |
| actionlint on `wheels.yml`, `docs.yml` | clean | run through `actionlint-py` |
| The sky-model test detects the fault | With the `6beec0a` `sky.py`, it fails on Linux (`LC_ALL=C`) and on Windows (cp1252) | `windows-portability-basereader.log` |

The Windows runs are at `c658ec6`. Only this note follows that commit.

## Deviations

- **Three calls are not edited**, because they sit in verbatim P11 extracts:
  `core_state.py` `write_json`, `core_response.py` `json` and
  `core_trend_run.py` (`metrics.json`). `core_state.py` is in the task's owner
  list, but `test_extract_is_verbatim_copy_of_history` compares these segments
  with `history/python` text for text. The test lists them by file. They handle
  JSON from `json.dump(s)`, which is ASCII, so the code page changes no character.
  On Windows the two writers still end lines with CRLF.
- **19 scripts, not 17:** `diagnose_solver_study.py` and `run_l5_solver_study.py`
  use the same pattern with `outputs/l5-solver-`.
- **`code_sha256` values change for new runs.** `core_campaign*.py`, `core_fetch.py`
  and `examples/prototype_section6.py` are `CODE_FILES` members and were edited, as
  the task's owner list requires. No comparator was found to compare these values
  with an archive: `core_compare` lists `code_sha256` and `module_sha256` as
  ignored, `check_section6.py` tests only that the key exists, and
  `archive_luno_campaign.py` copies it. The identity suite shows no difference.
- **The identity reference** is this worktree before any edit. The branch does not
  touch Rust, and the archived `before/` predates later merges. Only the script
  form ran, because the suite's `cli` forms name the old `rangtoy` package.

Not changed: `subprocess.run(text=True)`, which is outside the task's list; the
CI step `git config --global core.autocrlf false`, now redundant but harmless;
`PYTHONUTF8` in `docs.yml` and `docs/gen_cli.py`. The MemAvailable print W4-2 noted
was not checked.

## Timings

| Date | Step | Host | Wall | Note |
| --- | --- | --- | ---: | --- |
| 2026-11-02 | uv venv + editable install | WSL | 90 s | |
| 2026-11-02 | identity suite, before / after | WSL | 8 s / 7 s | 20 cases |
| 2026-11-02 | pc1, p11 and backends tests, before / after | WSL | 23 s / 21 s | 37 passed |
| 2026-11-02 | `bash tools/check-all.sh` at `c658ec6` | WSL | 742 s | PASS; includes any lock wait; pytest 332 s |
| 2026-11-02 | `bash tools/check-all.sh` at `7fb4299` | WSL | 872 s | FAIL on the index test only; includes any lock wait; pytest 220 s |
| 2026-11-02 | uv venv + editable install | Windows | 190 s | includes the extension build |
| 2026-11-02 | `python -m rang.check` | Windows | 874 s | PASS with UTF-8 mode off; pytest 206 s |
| 2026-11-02 | `tools/wheel/build.py` / `test.py` | Windows | 136 s / 31 s | `PYTHONUTF8=0` |
| 2026-11-02 | actionlint | WSL | 0.9 s | |

## For the coordinator

**Merge order.** `tests/test_w4_8_docs.py` requires every note in the index, and
`research/README.md` is yours. So this branch's head prints `overall: FAIL` on
that one test until the index line below is added, and a check-all after your
index edit is still to run. `overall: PASS` is measured at `c658ec6`, the commit
before this note.

**Index line** (`research/README.md`, with the portability or release theme):

```
- [W4-6 portability hygiene](w4-6-portability.md): UTF-8 on every text read and write in the package, LF by `.gitattributes`, one Windows CI cell with UTF-8 mode off.
```

**STATE paragraph** (under `## Log (newest first)`):

> W4-6, portability hygiene (big plan wave 4), 2026-11-02 (implemented; measured).
> `python/rang` names UTF-8 on 90 text reads and writes and LF on every write;
> three verbatim P11 sites stay as frozen and are listed in the new AST test.
> `.gitattributes` makes the tree LF outside `research/results/` and `history/`
> (11 files renormalised, none hashed; `closure.py` keeps its CRLF). 19 example
> scripts use `as_posix()`. The identity suite is identical before and after, and
> `python -m rang.check` passes on native Windows with UTF-8 mode off and
> `core.autocrlf=true`. The Windows py3.14 CI cell now sets `PYTHONUTF8=0`; it has
> not run on GitHub yet, and its local equivalent passes.
> [Note](w4-6-portability.md).

**tool-timings rows:** the table under "Timings".

**Ignored outputs:** `outputs/w4-6-20261102-01` (identity suite and test logs),
`outputs/w4-6-20261102-02` (Windows logs), `outputs/w4-6-20261102-check-all-c658ec6.log`,
`outputs/w4-6-20261102-check-all-7fb4299.log`.
