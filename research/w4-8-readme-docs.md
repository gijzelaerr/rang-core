# W4-8: the documentation pass

Status: **implemented and checked; documentation only, no numerical code or
result changed.** check-all: `overall: PASS` (816 passed, 13 skipped).

The owner's instruction: the README "has become a bit of a mess"; clean it up
and restructure it. The wave 4 pass and the "Documentation drift" table of
[w4-review.md](w4-review.md) are in scope too.

## What changed

| File | Before → after lines | Change |
| --- | ---: | --- |
| `README.md` | 253 → 151 | Whole file. Logo (dark-mode variant through `<picture>`), tagline, status box, What it is, Install, Quick start, Documentation, Research results, Repository guide, Names, Contributing, Licence and data acknowledgements, Citation. |
| `research/README.md` | 556 → about 330 | Whole file. Start here, the rename note, then one section per theme, newest first, one line per report; a compact Timeline. The evidence table, pilot findings, checkpoints and resume notes are kept. The history the README dropped is here: the beam-width table, the 7.26× surrogate, chromatic gains, scope and limitations. |
| `research/STATE.md` | 2632 → 1674 | A "Current status" block and a "Log (newest first)" heading; no paragraph edited. A new paragraph now goes directly under the log heading. |
| `research/STATE-history.md` | new, 980 | Every entry before 2026-10-29, unedited. |
| `AGENTS.md` | 41 → 55 | Both questions closed; a Layout section. Every rule stays. |
| `CONTRIBUTING.md` | 96 → 97 | Docs URL, the full-check extras, the platform paragraph. |
| `docs/index.md` | 66 → 59 | The README's tagline and status box; the verdict's detail is left to the research story. |
| `docs/installation.md` | 123 → 127 | The extras table gains `meerkat`, `formats`, `carta` and `casacure`. |
| `.github/workflows/docs.yml` | 107 → 133 | The conditional deploy job. |
| `pyproject.toml` | one line | `Documentation = "https://pythonic.nl/rang-core/"` (coordinator's update). |
| `CITATION.cff` | new, 12 | Owner's name, repository, version 0.1.0; no ORCID in the repository. |
| `core/src/ffi.rs`, `core/py/src/lib.rs` | comments only | See "For the coordinator". |
| `tests/test_w4_8_docs.py` | new | Length and section order, links resolve, every note indexed, no dated stack, STATE's structure, CITATION's version, the deploy gate including its shell with a fake `curl`. |

The deploy job's first step queries `GET /repos/{repo}/pages` with the workflow
token. On 200 it deploys. On 404 it prints a `::warning::` with both ways to
enable Pages and skips the two deploy steps, so the job succeeds. Any other status
fails the job rather than hiding an API fault. Pages is now enabled on the
repository, so the 404 path has been exercised only by the fake-`curl` test, not
on GitHub. The job stays useful on forks.

### Drift table

| Row | Outcome |
| --- | --- |
| `AGENTS.md:6-7`, no layout section | Fixed here. |
| README: active flagging, next decision, wheels, masks, "nothing runs Cargo" | Fixed by the rewrite. |
| `docs/installation.md` Cargo statement and macOS jobs | Already fixed by W4-3 and W4-5; the text was checked and left. |
| `CONTRIBUTING.md:45-55`, `:10` | Fixed here. |
| `core/py/src/lib.rs:10-11` | Fixed here: W4-2 now refuses arrays that are not C-contiguous, and the docstring says so. |
| `core/src/ffi.rs:1-5` | Fixed here. |
| `core_closure.py`, `fluxstd.py` | Already fixed by W4-3. |
| `research/README.md`: eight unreachable notes, `tool-timings.md` | Fixed here: all 21 notes the index did not link directly are linked. |
| `research/STATE.md` | Fixed here. |

## Checks

- **Nothing lost, by script.** STATE: title + kept + moved bodies equal the old
  file byte for byte. Index: every link target of the old index is in the new one.
  README: every old target is in the new README or the index (the one false
  positive, CHANGELOG, is an HTML link). Moved numbers grepped: 6.33–9.19,
  0.79–1.10, 0.73–1.07, 7.26×, 168, 2.89 %.
- **Rendering, structure only** (no browser was available; nobody has looked at
  it on GitHub or PyPI). `readme_renderer` with comrak, `cmarkgfm` and
  `markdown-it-py` (`gfm-like`) each give 4 tables, 10 `h2`, 4 `pre`, 1 blockquote,
  1 `picture`, 1 `img`. The PyPI renderer drops `<source>` and keeps the light logo,
  and all 50 of its URLs are absolute.
- **Quick start.** The README's block, extracted and run from a directory outside
  the checkout, prints exactly the README's text in about 2 s. The download itself
  was not run: the cache was seeded with the local verified copy.
- **Workflow and citation.** actionlint clean on `docs.yml`; `cffconvert --validate` passes.
- **Site.** `sphinx -W` passes without executing notebooks; the five pages the
  README links exist. The links to `pythonic.nl` were not fetched.
- **First check-all failed** (`test_site_builds_without_warnings`): the new text
  broke "not an operational calibrator" across two lines of the HTML. Reflowed.

## Deviations

- **`main` merged into the branch three times** (`9813608`, `f376d4b`, `378b66b`), because each new
  note would fail the every-note test and main's top paragraphs conflict with the new
  STATE structure. Entries added for E6, W4-2/W4-7, the CLEAN major cycles, DF5-O and B1-3,
  rewritten from main's stack paragraphs; main's STATE paragraphs sit under the log heading.
- **Documentation URL** is `https://pythonic.nl/rang-core/`, the coordinator's
  update; the brief's `github.io` URL redirects there.
- **`CHANGELOG.md:53`** still has the old URL, as it is not a file of this task.
  Its 0.1.0 section becomes the release notes, so the hunk is below.
- **"What it is" uses bullets**, as briefed; the extras are one table, platforms one sentence.
- **Historical research notes** keep the old URL (`d1-docs.md`, `w4-5-release.md`, `w4-review.md`).
- **B1-3 closed null** while this task ran: the coordinator's update replaced the briefed
  status ("B1-2 positive, B1-3 running") in the README, the docs index, AGENTS.md, STATE and the
  index. `docs/research/index.md` said "B1-2 and B1-3 are proposed", so it was updated too,
  though it is not on this task's file list.
- **Check-all log**: copied to `outputs/w4-8-20261102-check-all.log` as briefed.

## Open items

- `docs/tutorials/index.md` and notebook 7 still describe "B1-2 and B1-3 as proposed";
  the notebook needs its own edit and rerun.
- `research/meerkat-scope.md` still calls gain-TV flagging the "current active
  experiment"; AGENTS.md points to it for scope. It was outside this task's files.
- STATE's status block goes stale unless the merge routine updates it.
- Index entries for newly merged notes now go in the themed sections, or
  `tests/test_w4_8_docs.py` fails.

## Timings

| Run | Wall | Notes |
| --- | ---: | --- |
| `uv venv` + editable install, all extras in the brief | 325 s | shared host |
| `rang-core -h`, renderer install | seconds | |
| Quick start | 1.9 s | excluding the download |
| `actionlint` (uv tool) | 1.9 s | clean |
| `cffconvert --validate` (uv tool) | 6.1 s | valid |
| `sphinx -W`, without executing notebooks | 58 s | passes |
| `bash tools/check-all.sh`, first run | 3,023 s | FAIL, one test (above); most of it lock wait; pytest 377.6 s |
| `bash tools/check-all.sh`, second run | 2031 s | `overall: PASS`, pytest 816 passed, 13 skipped in 212.2 s; includes lock wait |

## For the coordinator

**Coordinator files on the branch.**

- `README.md`, `research/README.md`: whole file (structure above).
- `research/STATE.md`: the block and heading only; old body otherwise unchanged. **Insert new paragraphs under `## Log (newest first)`.**
- `AGENTS.md`: replaces "The active experiment is MeerKAT L-band gain-TV-guided flagging; older pointing reports are separate history." with "Gain-TV-guided flagging (`research/flagging-verdict.md`) and beam and pointing (`research/b1-3-pointing-selfcal.md`) are both closed as null."; adds `## Layout`; "The current experiment is specified in" becomes "The scope is specified in".
- `core/src/ffi.rs`: header becomes "C ABI of the core, for C consumers and benches. The Python layer reaches these functions through the PyO3 extension `rang._core` (`core/py`); ctypes is gone since task P7 (`research/p7-architecture.md`). Every pointer is described by an explicit length in the structs."
- `core/py/src/lib.rs`: "non-contiguous arrays and read-only outputs are refused" becomes "arrays that are not C-contiguous and read-only outputs are refused, task W4-2".

**CHANGELOG hunk.** `CHANGELOG.md:53`: replace `https://gijzelaerr.github.io/rang-core/` with `https://pythonic.nl/rang-core/`.

**STATE paragraph** (under the log heading).

> W4-8, the documentation pass (big plan wave 4), 2026-11-02 (implemented; checked;
> [w4-8-readme-docs.md](w4-8-readme-docs.md)). The README is a 151-line landing page
> and the research index is by theme with every note linked. STATE has a status
> block and a log heading, and its entries before 2026-10-29 moved unedited to
> [STATE-history.md](STATE-history.md). AGENTS.md matches the layout. The docs deploy
> job warns and skips without GitHub Pages. The canonical site is
> <https://pythonic.nl/rang-core/>. No numerical code or result changed.

**Research index entry.** Already on the branch, under "Cross-platform, wheel, docs and release".

**Big-plan line.** Wave 4: "W4-8 documentation pass done 2026-11-02 (`w4-8-readme-docs.md`)." User items: the Pages item is resolved, as the owner enabled it (served at <https://pythonic.nl/rang-core/>); remove it.

**tool-timings rows.** The Timings table above.

**Ignored output directories.** None, only the log `outputs/w4-8-20261102-check-all.log`.
